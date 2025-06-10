from transformers import AutoTokenizer, AutoModel
import sqlite3
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from flask import Flask, request, jsonify
import nltk
from nltk.corpus import stopwords
import logging
import json

# 配置日誌
logging.basicConfig(filename='recommendation.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)

# 初始化 BERT
tokenizer = AutoTokenizer.from_pretrained("bert-base-uncased")
model = AutoModel.from_pretrained("bert-base-uncased")

# 初始化停用詞
nltk.download('stopwords')
stop_words = set(stopwords.words('english'))

def init_database():
    """初始化 SQLite 數據庫"""
    conn = sqlite3.connect('cloud_storage.db')
    cursor = conn.cursor()
    return conn, cursor

def clean_metadata(tags):
    """清理元數據標籤"""
    return [tag.lower() for tag in tags if tag.lower() not in stop_words and len(tag) > 2]

def get_embedding(text):
    """獲取文本嵌入"""
    inputs = tokenizer(text, return_tensors="pt", padding=True, truncation=True)
    outputs = model(**inputs)
    return outputs.last_hidden_state.mean(dim=1).detach().numpy()

@app.route('/recommend', methods=['POST'])
def recommend_files():
    """推薦文件"""
    data = request.json
    query = data.get('query', '')
    user_id = data.get('userId', '')
    
    logging.info(f"處理搜尋查詢: {query} 用戶 ID: {user_id}")
    
    # 從數據庫獲取用戶文件
    conn, cursor = init_database()
    cursor.execute("SELECT filename, metadata FROM files WHERE user_id = ?", (user_id,))
    files = cursor.fetchall()
    conn.close()
    
    # 清理查詢
    query_clean = ' '.join(clean_metadata(query.split()))
    query_embedding = get_embedding(query_clean)
    
    recommendations = []
    for filename, metadata in files:
        try:
            tags = json.loads(metadata).get('tags', [])
            tags_clean = ' '.join(clean_metadata(tags))
            if not tags_clean:
                continue
            file_embedding = get_embedding(tags_clean)
            similarity = cosine_similarity(query_embedding, file_embedding)[0][0]
            recommendations.append((filename, similarity))
        except Exception as e:
            logging.error(f"處理文件 {filename} 時出錯: {str(e)}")
    
    # 按相似度排序
    recommendations = sorted(recommendations, key=lambda x: x[1], reverse=True)[:10]
    logging.info(f"推薦結果: {recommendations}")
    
    return jsonify([r[0] for r in recommendations])

if __name__ == "__main__":
    app.run(port=5000)