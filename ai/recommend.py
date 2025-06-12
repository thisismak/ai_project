from transformers import AutoTokenizer, AutoModel
import sqlite3
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
import nltk
from nltk.corpus import stopwords
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os
import json

# 加載環境變數
load_dotenv()

# 配置日誌
logging.basicConfig(
    filename='recommendation.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

app = Flask(__name__)
CORS(app)  # 啟用 CORS

# 初始化 BERT（保留以備後用）
try:
    tokenizer = AutoTokenizer.from_pretrained("bert-base-uncased")
    model = AutoModel.from_pretrained("bert-base-uncased")
except Exception as e:
    logging.error(f"初始化 BERT 模型失敗: {str(e)}")
    raise

# 初始化停用詞
nltk.download('stopwords')
stop_words = set(stopwords.words('english'))

def init_database():
    """初始化 SQLite 資料庫"""
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
        cleaned = [tag.lower() for tag in tags if tag.lower() not in stop_words]
        logging.info(f"清理標籤: 原始={tags}, 清理後={cleaned}")
        return cleaned
    except Exception as e:
        logging.error(f"清理元數據失敗: {str(e)}")
        return []

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

@app.route('/recommend', methods=['POST'])
def recommend():
    """推薦文件及外部圖片"""
    try:
        data = request.json
        if not data:
            logging.error("請求缺少 JSON 數據")
            return jsonify({"error": "缺少請求數據"}), 400
        
        query = data.get('query', '').lower()
        user_id = data.get('userId', '')
        
        if not query or not user_id:
            logging.error(f"缺少必要參數: query={query}, userId={user_id}")
            return jsonify({"error": "缺少查詢或用戶ID"}), 400
        
        logging.info(f"處理搜尋查詢: {query} 用戶 ID: {user_id}")
        
        # 獲取用戶文件
        conn, cursor = init_database()
        cursor.execute("SELECT filename, metadata FROM files WHERE user_id = ?", (user_id,))
        files = cursor.fetchall()
        
        local_recommendations = []
        for filename, metadata in files:
            try:
                tags = json.loads(metadata).get('tags', [])
                logging.info(f"文件: {filename}, 標籤: {tags}")
                if query in [tag.lower() for tag in tags]:
                    local_recommendations.append({"filename": filename, "similarity": 1.0})
            except Exception as e:
                logging.error(f"處理文件 {filename} 時出錯: {str(e)}")
                continue
        
        # 獲取外部圖片
        external_images = get_external_images(query, user_id)
        
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