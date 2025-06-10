from transformers import AutoTokenizer, AutoModel
import sqlite3
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from flask import Flask, request, jsonify
import nltk
from nltk.corpus import stopwords
import logging
import json
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from dotenv import load_dotenv
import os
import random

# 加載環境變量
load_dotenv()

# 配置日誌
logging.basicConfig(filename='recommendation.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)

# 初始化 BERT
tokenizer = AutoTokenizer.from_pretrained("bert-base-uncased")
model = AutoModel.from_pretrained("bert-base-uncased")

# 初始化停用詞
nltk.download('stopwords')
stop_words = set(stopwords.words('english'))

# 爬蟲配置
MAX_IMAGES_PER_QUERY = 3
NAVIGATION_TIMEOUT = 15000  # 15秒
LOAD_STATE_TIMEOUT = 10000  # 10秒
RETRY_ATTEMPTS = 2

def init_database():
    """初始化 SQLite 數據庫"""
    conn = sqlite3.connect('cloud_storage.db')
    cursor = conn.cursor()
    # 添加 external_images 表用於快取圖片
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS external_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT,
            url TEXT UNIQUE,
            alt_text TEXT,
            source TEXT,
            title TEXT,
            timestamp TEXT
        )
    ''')
    conn.commit()
    return conn, cursor

def clean_metadata(tags):
    """清理元數據標籤"""
    return [tag.lower() for tag in tags if tag.lower() not in stop_words and len(tag) > 2]

def get_embedding(text):
    """獲取文本嵌入"""
    inputs = tokenizer(text, return_tensors="pt", padding=True, truncation=True)
    outputs = model(**inputs)
    return outputs.last_hidden_state.mean(dim=1).detach().numpy()

def get_user_preferred_tags(user_id):
    """獲取用戶偏好標籤"""
    conn, cursor = init_database()
    cursor.execute("SELECT query FROM search_history WHERE user_id = ? ORDER BY timestamp DESC LIMIT 10", (user_id,))
    queries = [row[0] for row in cursor.fetchall()]
    conn.close()
    tags = []
    for query in queries:
        tags.extend(clean_metadata(query.split()))
    return list(set(tags))

def collect_image_urls_google(page, query, max_images):
    """從 Google 圖片搜尋收集圖片 URL 和 alt 文本"""
    for attempt in range(RETRY_ATTEMPTS):
        images = []
        try:
            logging.info(f"Google 搜尋 {query}，嘗試 {attempt+1}")
            page.goto(f"https://www.google.com/search?tbm=isch&q={query}", timeout=NAVIGATION_TIMEOUT)
            page.wait_for_load_state("networkidle", timeout=LOAD_STATE_TIMEOUT)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(random.uniform(500, 1000))  # 隨機延遲
            image_elements = page.query_selector_all("img")
            for img in image_elements:
                try:
                    src = img.get_attribute("src") or img.get_attribute("data-src")
                    alt = img.get_attribute("alt") or ""
                    if src and src.startswith("http") and alt.strip() and len(alt.strip()) > 3:
                        images.append({"url": src, "alt": alt, "source": "Google", "title": alt})
                except Exception as e:
                    logging.warning(f"Google 圖片屬性錯誤: {str(e)}")
            logging.info(f"Google 搜尋 {query} 收集 {len(images)} 張圖片")
            return images[:max_images]
        except PlaywrightTimeoutError as e:
            logging.error(f"Google 搜尋 {query} 超時: {str(e)}")
            if attempt < RETRY_ATTEMPTS - 1:
                page.reload(timeout=NAVIGATION_TIMEOUT)
                continue
            return []
        except Exception as e:
            logging.error(f"Google 搜尋 {query} 錯誤: {str(e)}")
            return []
    return []

def get_external_images(query, user_id):
    """從快取或 Google 獲取圖片，考慮用戶偏好"""
    conn, cursor = init_database()
    
    # 檢查快取
    cursor.execute("SELECT url, alt_text, source, title FROM external_images WHERE query = ? ORDER BY timestamp DESC LIMIT 3", (query,))
    cached_images = [
        {"url": row[0], "alt": row[1], "source": row[2], "title": row[3]}
        for row in cursor.fetchall()
    ]
    if cached_images:
        logging.info(f"從快取返回 {len(cached_images)} 張圖片 for {query}")
        conn.close()
        return cached_images
    
    # 考慮用戶偏好，增強查詢
    preferred_tags = get_user_preferred_tags(user_id)
    enhanced_query = f"{query} {' '.join(preferred_tags[:3])}" if preferred_tags else query
    
    # Google 爬取
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        images = collect_image_urls_google(page, enhanced_query, MAX_IMAGES_PER_QUERY)
        context.close()
        browser.close()
    
    # 存入快取
    if images:
        for img in images:
            cursor.execute(
                "INSERT OR IGNORE INTO external_images (query, url, alt_text, source, title, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                (query, img["url"], img["alt"], img["source"], img["title"], "2025-06-10T12:00:00Z")
            )
        conn.commit()
    
    conn.close()
    return images[:MAX_IMAGES_PER_QUERY]

@app.route('/recommend', methods=['POST'])
def recommend():
    """推薦文件及外部圖片"""
    try:
        data = request.json
        query = data.get('query', '')
        user_id = data.get('userId', '')
        
        logging.info(f"處理搜尋查詢: {query} 用戶 ID: {user_id}")
        
        # 獲取用戶文件
        conn, cursor = init_database()
        cursor.execute("SELECT filename, metadata FROM files WHERE user_id = ?", (user_id,))
        files = cursor.fetchall()
        
        # 清理查詢
        query_clean = ' '.join(clean_metadata(query.split()))
        query_embedding = get_embedding(query_clean)
        
        # 本地推薦
        local_recommendations = []
        for filename, metadata in files:
            try:
                tags = json.loads(metadata).get('tags', [])
                tags_clean = ' '.join(clean_metadata(tags))
                if not tags_clean:
                    continue
                file_embedding = get_embedding(tags_clean)
                similarity = float(cosine_similarity(query_embedding, file_embedding)[0][0])
                local_recommendations.append({"filename": filename, "similarity": similarity})
            except Exception as e:
                logging.error(f"處理文件 {filename} 時出錯: {str(e)}")
        
        # 按相似度排序
        local_recommendations = sorted(local_recommendations, key=lambda x: x["similarity"], reverse=True)[:5]
        
        # 獲取外部圖片
        external_images = get_external_images(query_clean, user_id)
        
        # 合併結果
        response = {
            "local_files": [r["filename"] for r in local_recommendations],
            "external_images": external_images
        }
        
        logging.info(f"推薦結果: {response}")
        return jsonify(response)
    except Exception as e:
        logging.error(f"推薦端點錯誤: {str(e)}")
        return jsonify({"error": "搜尋失敗"}), 500

if __name__ == "__main__":
    app.run(port=5000)