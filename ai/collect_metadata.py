import sqlite3

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
    conn.close()

if __name__ == "__main__":
    init_database()
    print("資料庫初始化完成")