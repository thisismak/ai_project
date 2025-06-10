import sqlite3
import logging
import random
import json

# 配置日誌
logging.basicConfig(filename='metadata_collection.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 配置常量
DB_NAME = "cloud_storage.db"
TARGET_METADATA_COUNT = 1000
FILE_TYPES = ['pdf', 'txt', 'jpg', 'docx']
TAGS = ['report', 'image', 'document', 'data', 'personal', 'work']

def init_database():
    """初始化 SQLite 數據庫"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            filename TEXT,
            filepath TEXT,
            metadata TEXT,
            upload_date TEXT
        )
    ''')
    conn.commit()
    return conn, cursor

def generate_metadata(user_id, count):
    """生成模擬文件元數據"""
    metadata_list = []
    for i in range(count):
        filename = f"file_{user_id}_{i}.{random.choice(FILE_TYPES)}"
        tags = random.sample(TAGS, k=random.randint(1, 3))
        metadata = {'tags': tags}
        filepath = f"uploads/users/{user_id}/{filename}"
        metadata_list.append({
            'user_id': user_id,
            'filename': filename,
            'filepath': filepath,
            'metadata': json.dumps(metadata),
            'upload_date': '2025-06-10T12:00:00Z'
        })
    return metadata_list

def main():
    """主函數：生成並儲存模擬元數據"""
    conn, cursor = init_database()
    try:
        # 模擬 10 個用戶，每人 100 個文件元數據
        for user_id in range(1, 11):
            metadata_list = generate_metadata(user_id, TARGET_METADATA_COUNT // 10)
            for metadata in metadata_list:
                cursor.execute(
                    'INSERT OR IGNORE INTO files (user_id, filename, filepath, metadata, upload_date) VALUES (?, ?, ?, ?, ?)',
                    (metadata['user_id'], metadata['filename'], metadata['filepath'], metadata['metadata'], metadata['upload_date'])
                )
            conn.commit()
            logging.info(f"已為用戶 {user_id} 生成 {len(metadata_list)} 條元數據")
        cursor.execute('SELECT COUNT(*) FROM files')
        count = cursor.fetchone()[0]
        logging.info(f"總共生成 {count} 條元數據")
        print(f"總共生成 {count} 條元數據")
    except Exception as e:
        logging.error(f"生成元數據失敗: {str(e)}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()