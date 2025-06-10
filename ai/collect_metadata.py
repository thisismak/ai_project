import json
import random
import sqlite3
import os

FILE_TYPES = ['jpg', 'png', 'pdf', 'docx', 'txt']
TAGS = ['report', 'image', 'document', 'photo', 'note', 'anime', 'gundam', 'robot']

def init_database():
    """初始化 SQLite 數據庫"""
    conn = sqlite3.connect('cloud_storage.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            filename TEXT,
            filepath TEXT,
            metadata TEXT,
            upload_date TEXT
        )
    ''')
    conn.commit()
    return conn, cursor

def generate_metadata(user_id, count):
    """生成模擬元數據"""
    metadata_list = []
    if user_id == '1':
        metadata_list.append({
            'user_id': user_id,
            'filename': 'G Gundam.jpg',
            'filepath': f'Uploads/users/{user_id}/G Gundam.jpg',
            'metadata': json.dumps({'tags': ['gundam', 'image', 'anime']}),
            'upload_date': '2025-06-10T12:00:00Z'
        })
    for i in range(count):
        filename = f"file_{user_id}_{i}.{random.choice(FILE_TYPES)}"
        tags = random.sample(TAGS, k=random.randint(1, 3))
        metadata = {'tags': tags}
        filepath = f"Uploads/users/{user_id}/{filename}"
        metadata_list.append({
            'user_id': user_id,
            'filename': filename,
            'filepath': filepath,
            'metadata': json.dumps(metadata),
            'upload_date': '2025-06-10T12:00:00Z'
        })
    return metadata_list

def save_metadata(metadata_list):
    """儲存元數據到數據庫"""
    conn, cursor = init_database()
    for metadata in metadata_list:
        cursor.execute('''
            INSERT OR REPLACE INTO files (user_id, filename, filepath, metadata, upload_date)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            metadata['user_id'],
            metadata['filename'],
            metadata['filepath'],
            metadata['metadata'],
            metadata['upload_date']
        ))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    os.makedirs('Uploads/users/1', exist_ok=True)
    metadata = generate_metadata('1', 10)
    save_metadata(metadata)
    print("元數據生成並儲存完成")