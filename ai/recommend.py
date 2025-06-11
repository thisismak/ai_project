from transformers import AutoTokenizer, AutoModel
import sqlite3
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from flask import Flask, request, jsonify
import nltk
from nltk.corpus import stopwords
import logging
import json
from flask_cors import CORS
from dotenv import load_dotenv
import os

# 加載環境變量
load_dotenv()

# 配置日誌
logging.basicConfig(
    filename='recommendation.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

app = Flask(__name__)
CORS(app)  # 啟用 CORS

# 初始化 BERT
try:
    tokenizer = AutoTokenizer.from_pretrained("bert-base-uncased")
    model = AutoModel.from_pretrained("bert-base-uncased")
except Exception as e:
    logging.error(f"初始化 BERT 模型失敗: {str(e)}")
    raise

# 初始化停用詞
nltk.download('stopwords')
stop_words = set(stopwords.words('english'))

# 爬蟲配置（目前禁用）
MAX_IMAGES_PER_QUERY = 3
NAVIGATION_TIMEOUT = 30000  # 30秒
LOAD_STATE_TIMEOUT = 20000  # 20秒

def init_database():
    """初始化 SQLite 數據庫"""
    try:
        conn = sqlite3.connect('cloud_storage.db')
        cursor = conn.cursor()
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
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS search_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                query TEXT,
                timestamp TEXT
            )
        ''')
        conn.commit()
        return conn, cursor
    except Exception as e:
        logging.error(f"初始化資料庫失敗: {str(e)}")
        raise

def clean_metadata(tags):
    """清理元數據標籤"""
    try:
        return [tag.lower() for tag in tags if tag.lower() not in stop_words and len(tag) > 2]
    except Exception as e:
        logging.error(f"清理元數據失敗: {str(e)}")
        return []

def get_embedding(text):
    """獲取文本嵌入"""
    try:
        if not text.strip():
            logging.warning("空的文本輸入，無法生成嵌入")
            return np.zeros((1, 768))  # 返回零向量
        inputs = tokenizer(text, return_tensors="pt", padding=True, truncation=True)
        outputs = model(**inputs)
        return outputs.last_hidden_state.mean(dim=1).detach().numpy()
    except Exception as e:
        logging.error(f"生成嵌入失敗: {str(e)}")
        return np.zeros((1, 768))  # 返回零向量以避免崩潰

def get_user_preferred_tags(user_id):
    """獲取用戶偏好標籤"""
    try:
        conn, cursor = init_database()
        cursor.execute("SELECT query FROM search_history WHERE user_id = ? ORDER BY timestamp DESC LIMIT 10", (user_id,))
        queries = [row[0] for row in cursor.fetchall()]
        conn.close()
        tags = []
        for query in queries:
            tags.extend(clean_metadata(query.split()))
        return list(set(tags))
    except Exception as e:
        logging.error(f"獲取用戶偏好標籤失敗: {str(e)}")
        return []

def get_external_images(query, user_id):
    """從快取獲取圖片，暫時禁用 Google 爬蟲"""
    try:
        logging.info(f"跳過外部圖片搜尋: {query}")
        conn, cursor = init_database()
        cursor.execute("SELECT url, alt_text, source, title FROM external_images WHERE query = ? ORDER BY timestamp DESC LIMIT 3", (query,))
        cached_images = [
            {"url": row[0], "alt": row[1], "source": row[2], "title": row[3]}
            for row in cursor.fetchall()
        ]
        conn.close()
        if cached_images:
            logging.info(f"從快取返回 {len(cached_images)} 張圖片 for {query}")
        return cached_images
    except Exception as e:
        logging.error(f"獲取外部圖片失敗: {str(e)}")
        return []

    # 若需恢復爬蟲，取消以下註釋並確保 Playwright 環境正確
    """
    try:
        conn, cursor = init_database()
        cursor.execute("SELECT url, alt_text, source, title FROM external_images WHERE query = ? ORDER BY timestamp DESC LIMIT 3", (query,))
        cached_images = [
            {"url": row[0], "alt": row[1], "source": row[2], "title": row[3]}
            for row in cursor.fetchall()
        ]
        if cached_images:
            logging.info(f"從快取返回 {len(cached_images)} 張圖片 for {query}")
            conn.close()
            return cached_images
        
        preferred_tags = get_user_preferred_tags(user_id)
        enhanced_query = f"{query} {' '.join(preferred_tags[:3])}" if preferred_tags else query
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            )
            page = context.new_page()
            try:
                logging.info(f"Google 搜尋 {enhanced_query}")
                page.goto(f"https://www.google.com/search?tbm=isch&q={enhanced_query}", timeout=NAVIGATION_TIMEOUT)
                page.wait_for_load_state("networkidle", timeout=LOAD_STATE_TIMEOUT)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(1000)
                image_elements = page.query_selector_all("img[src^='http']")
                images = []
                for img in image_elements:
                    src = img.get_attribute("src")
                    alt = img.get_attribute("alt") or "No alt text"
                    if src and alt.strip():
                        images.append({"url": src, "alt": alt, "source": "Google", "title": alt})
                logging.info(f"Google 搜尋 {enhanced_query} 收集 {len(images)} 張圖片")
            except Exception as e:
                logging.error(f"Google 搜尋 {enhanced_query} 失敗: {str(e)}")
                images = []
            context.close()
            browser.close()
        
        if images:
            for img in images:
                cursor.execute(
                    "INSERT OR IGNORE INTO external_images (query, url, alt_text, source, title, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                    (query, img["url"], img["alt"], img["source"], img["title"], "2025-06-11T16:50:00Z")
                )
            conn.commit()
        
        conn.close()
        return images[:MAX_IMAGES_PER_QUERY]
    except Exception as e:
        logging.error(f"獲取外部圖片失敗: {str(e)}")
        return []
    """

@app.route('/recommend', methods=['POST'])
def recommend():
    """推薦文件及外部圖片"""
    try:
        data = request.json
        if not data:
            logging.error("請求缺少 JSON 數據")
            return jsonify({"error": "缺少請求數據"}), 400
        
        query = data.get('query', '')
        user_id = data.get('userId', '')
        
        if not query or not user_id:
            logging.error(f"缺少必要參數: query={query}, userId={user_id}")
            return jsonify({"error": "缺少查詢或用戶ID"}), 400
        
        logging.info(f"處理搜尋查詢: {query} 用戶 ID: {user_id}")
        
        # 獲取用戶文件
        conn, cursor = init_database()
        cursor.execute("SELECT filename, metadata FROM files WHERE user_id = ?", (user_id,))
        files = cursor.fetchall()
        
        # 清理查詢
        query_clean = ' '.join(clean_metadata(query.split()))
        if not query_clean:
            logging.warning(f"清理後查詢為空: {query}")
            conn.close()
            return jsonify({"local_files": [], "external_images": []}), 200
        
        query_embedding = get_embedding(query_clean)
        
        # 本地推薦
        local_recommendations = []
        for filename, metadata in files:
            try:
                tags = json.loads(metadata).get('tags', [])
                tags_clean = ' '.join(clean_metadata(tags))
                if not tags_clean:
                    logging.warning(f"文件 {filename} 無有效標籤")
                    continue
                file_embedding = get_embedding(tags_clean)
                similarity = float(cosine_similarity(query_embedding, file_embedding)[0][0])
                local_recommendations.append({"filename": filename, "similarity": similarity})
            except Exception as e:
                logging.error(f"處理文件 {filename} 時出錯: {str(e)}")
                continue
        
        # 按相似度排序
        local_recommendations = sorted(local_recommendations, key=lambda x: x["similarity"], reverse=True)[:5]
        logging.info(f"本地推薦文件: {local_recommendations}")
        
        # 獲取外部圖片
        external_images = get_external_images(query_clean, user_id)
        
        # 合併結果
        response = {
            "local_files": [r["filename"] for r in local_recommendations],
            "external_images": external_images
        }
        
        logging.info(f"推薦結果: {response}")
        conn.close()
        return jsonify(response)
    except Exception as e:
        logging.error(f"推薦端點錯誤: {str(e)}", exc_info=True)
        return jsonify({"error": "搜尋失敗", "details": str(e)}), 500
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    app.run(port=5000, debug=False)