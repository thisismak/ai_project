import express, { Request, Response, NextFunction } from 'express';
import axios from 'axios';
import sqlite3 from 'sqlite3';
import { open } from 'sqlite';
import jwt from 'jsonwebtoken';
import fileUpload from 'express-fileupload';
import cors from 'cors';
import bcrypt from 'bcrypt';
import fs from 'fs';
import path from 'path';
import dotenv from 'dotenv';

// 加載環境變數
dotenv.config();

// 擴展 Request 類型
declare module 'express-serve-static-core' {
  interface Request {
    user?: { userId: string };
  }
}

const app = express();
app.use(express.json());
app.use(fileUpload());
app.use(cors());

// 提供前端靜態檔案
app.use(express.static(path.join(__dirname, '..', '..', 'frontend')));

const JWT_SECRET = process.env.JWT_SECRET || 'your_jwt_secret';

async function initDatabase() {
  const dbPath = path.join(__dirname, '..', '..', 'ai', 'cloud_storage.db');

  try {
    const db = await open({
      filename: dbPath,
      driver: sqlite3.Database
    });
    // 創建 users 表
    await db.exec(`
      CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE,
        password TEXT
      )
    `);
    // 創建 files 表
    await db.exec(`
      CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        filename TEXT,
        filepath TEXT,
        metadata TEXT,
        upload_date TEXT
      )
    `);
    // 創建 search_history 表
    await db.exec(`
      CREATE TABLE IF NOT EXISTS search_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        query TEXT,
        timestamp TEXT
      )
    `);
    console.log(`資料庫初始化於: ${dbPath}`);
    return db;
  } catch (error) {
    console.error(`初始化資料庫失敗於 ${dbPath}:`, error);
    throw error;
  }
}

// 驗證 JWT
function authenticateToken(req: Request, res: Response, next: NextFunction): void {
  const authHeader = req.headers['authorization'];
  const token = authHeader && authHeader.split(' ')[1];
  if (!token) {
    res.status(401).json({ error: '未授權' });
    return;
  }
  jwt.verify(token, JWT_SECRET, (err, user) => {
    if (err) {
      res.status(403).json({ error: '無效令牌' });
      return;
    }
    if (user && typeof user === 'object' && 'userId' in user) {
      req.user = { userId: (user as any).userId };
      next();
    } else {
      res.status(403).json({ error: '無效用戶數據' });
      return;
    }
  });
}

// 註冊
app.post('/api/auth/register', async (req: Request, res: Response): Promise<void> => {
  const { email, password } = req.body;
  if (!email || !password) {
    res.status(400).json({ error: '缺少電郵或密碼' });
    return;
  }
  try {
    const db = await initDatabase();
    try {
      const hashedPassword = await bcrypt.hash(password, 10);
      await db.run('INSERT INTO users (email, password) VALUES (?, ?)', [email, hashedPassword]);
      res.json({ message: '註冊成功' });
    } finally {
      await db.close();
    }
  } catch (error: any) {
    console.error('註冊錯誤:', error);
    if (error.code === 'SQLITE_CONSTRAINT') {
      res.status(409).json({ error: '電郵已存在' });
    } else {
      res.status(500).json({ error: '註冊失敗: 資料庫錯誤' });
    }
  }
});

// 登錄
app.post('/api/login', async (req: Request, res: Response): Promise<void> => {
  const { email, password } = req.body;
  if (!email || !password) {
    res.status(400).json({ error: '缺少電郵或密碼' });
    return;
  }
  try {
    const db = await initDatabase();
    try {
      const user = await db.get('SELECT * FROM users WHERE email = ?', [email]);
      if (!user) {
        res.status(401).json({ error: '無效憑證' });
        return;
      }
      const match = await bcrypt.compare(password, user.password);
      if (match) {
        const token = jwt.sign({ userId: user.id.toString() }, JWT_SECRET, { expiresIn: '1h' });
        res.json({ token, userId: user.id });
      } else {
        res.status(401).json({ error: '無效憑證' });
      }
    } finally {
      await db.close();
    }
  } catch (error) {
    console.error('登入錯誤:', error);
    res.status(500).json({ error: '登入失敗: 資料庫錯誤' });
  }
});

// 搜尋
app.get('/api/search', authenticateToken, async (req: Request, res: Response): Promise<void> => {
  const query = req.query.q as string;
  const userId = req.user?.userId;
  if (!userId) {
    res.status(401).json({ error: '無效用戶' });
    return;
  }
  if (!query) {
    res.status(400).json({ error: '缺少搜尋查詢' });
    return;
  }
  try {
    const db = await initDatabase();
    try {
      const response = await axios.post('http://localhost:5000/recommend', { query, userId }, {
        timeout: 10000 // 設置 10 秒超時
      });
      const { local_files, external_images } = response.data;
      if (response.data.error) {
        throw new Error(response.data.error);
      }
      await db.run('INSERT INTO search_history (user_id, query, timestamp) VALUES (?, ?, ?)', [
        userId,
        query,
        new Date().toISOString(),
      ]);
      res.json({ local_files, external_images });
    } finally {
      await db.close();
    }
  } catch (error: any) {
    console.error('搜尋錯誤:', {
      message: error.message,
      stack: error.stack,
      response: error.response ? {
        status: error.response.status,
        data: error.response.data
      } : null
    });
    res.status(500).json({
      error: '搜尋失敗',
      details: error.response?.data?.details || error.message
    });
  }
});

// 上傳文件
app.post('/api/upload', authenticateToken, async (req: Request, res: Response): Promise<void> => {
  const userId = req.user?.userId;
  if (!userId) {
    res.status(401).json({ error: '無效用戶' });
    return;
  }
  const file = req.files?.file as fileUpload.UploadedFile;
  const tags = req.body.tags;
  if (!file || !tags) {
    res.status(400).json({ error: '缺少文件或標籤' });
    return;
  }
  const filename = file.name;
  const userDir = path.join(__dirname, 'Uploads', 'users', userId);
  if (!fs.existsSync(userDir)) {
    fs.mkdirSync(userDir, { recursive: true });
  }
  const filepath = path.join(userDir, filename);
  const metadata = JSON.stringify({ tags: tags.split(',').map((tag: string) => tag.trim()) });
  try {
    const db = await initDatabase();
    try {
      await file.mv(filepath);
      await db.run('INSERT INTO files (user_id, filename, filepath, metadata, upload_date) VALUES (?, ?, ?, ?, ?)', [
        userId,
        filename,
        filepath,
        metadata,
        new Date().toISOString()
      ]);
      console.log(`上傳成功: user_id=${userId}, filename=${filename}, metadata=${metadata}`);
      res.json({ message: '上傳成功' });
    } finally {
      await db.close();
    }
  } catch (error) {
    console.error('上傳錯誤:', error);
    res.status(500).json({ error: '上傳失敗' });
  }
});

// 獲取文件列表
app.get('/api/files/list', authenticateToken, async (req: Request, res: Response): Promise<void> => {
  const userId = req.user?.userId;
  if (!userId) {
    res.status(401).json({ error: '無效用戶' });
    return;
  }
  try {
    const db = await initDatabase();
    try {
      const files = await db.all('SELECT id, filename, upload_date FROM files WHERE user_id = ?', [userId]);
      res.json(files);
    } finally {
      await db.close();
    }
  } catch (error) {
    console.error('獲取文件列表錯誤:', error);
    res.status(500).json({ error: '獲取文件列表失敗' });
  }
});

// 刪除文件
app.delete('/api/files/delete/:id', authenticateToken, async (req: Request, res: Response): Promise<void> => {
  const userId = req.user?.userId;
  const fileId = req.params.id;
  if (!userId) {
    res.status(401).json({ error: '無效用戶' });
    return;
  }
  try {
    const db = await initDatabase();
    try {
      const file = await db.get('SELECT filepath FROM files WHERE id = ? AND user_id = ?', [fileId, userId]);
      if (!file) {
        res.status(404).json({ error: '文件不存在' });
        return;
      }
      await db.run('DELETE FROM files WHERE id = ? AND user_id = ?', [fileId, userId]);
      if (fs.existsSync(file.filepath)) {
        fs.unlinkSync(file.filepath);
      }
      res.json({ message: '刪除成功' });
    } finally {
      await db.close();
    }
  } catch (error) {
    console.error('刪除文件錯誤:', error);
    res.status(500).json({ error: '刪除文件失敗' });
  }
});

// 下載文件
app.get('/api/files/download/:id', authenticateToken, async (req: Request, res: Response): Promise<void> => {
  const userId = req.user?.userId;
  const fileId = req.params.id;
  if (!userId) {
    res.status(401).json({ error: '無效用戶' });
    return;
  }
  try {
    const db = await initDatabase();
    try {
      const file = await db.get('SELECT filepath, filename FROM files WHERE id = ? AND user_id = ?', [fileId, userId]);
      if (!file) {
        res.status(404).json({ error: '文件不存在' });
        return;
      }
      res.download(file.filepath, file.filename);
    } finally {
      await db.close();
    }
  } catch (error) {
    console.error('下載錯誤:', error);
    res.status(500).json({ error: '下載失敗' });
  }
});

// 提供 index.html
app.get('/', (req: Request, res: Response): void => {
  res.sendFile(path.join(__dirname, '..', '..', 'frontend', 'index.html'));
});

app.listen(3000, () => console.log('後端運行於 http://localhost:3000'));