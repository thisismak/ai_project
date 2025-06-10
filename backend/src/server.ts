import express, { Request, Response, NextFunction } from 'express';
import jwt from 'jsonwebtoken';
import bcrypt from 'bcrypt';
import multer from 'multer';
import sqlite3 from 'sqlite3';
import { open } from 'sqlite';
import axios from 'axios';
import fs from 'fs';
import path from 'path';

// 配置 Express
const app = express();
app.use(express.json());

// 配置 Multer 用於文件上傳
const storage = multer.diskStorage({
  destination: (req, file, cb) => {
    const userId = (req as any).user?.userId;
    const dir = path.join(__dirname, `../uploads/users/${userId}`);
    fs.mkdirSync(dir, { recursive: true });
    cb(null, dir);
  },
  filename: (req, file, cb) => {
    cb(null, file.originalname);
  },
});
const upload = multer({ storage });

// 初始化數據庫
async function initDatabase() {
  const db = await open({
    filename: path.join(__dirname, '../cloud_storage.db'),
    driver: sqlite3.Database,
  });
  await db.exec(`
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      email TEXT UNIQUE,
      password_hash TEXT,
      created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS files (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER,
      filename TEXT,
      filepath TEXT,
      metadata TEXT,
      upload_date TEXT
    );
    CREATE TABLE IF NOT EXISTS search_history (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER,
      query TEXT,
      timestamp TEXT
    );
  `);
  return db;
}

// 中間件：驗證 JWT
const authenticateToken = (req: Request, res: Response, next: NextFunction): void => {
  const token = req.headers.authorization?.split(' ')[1];
  if (!token) {
    res.status(401).json({ error: '未認證' });
    return;
  }
  try {
    const decoded = jwt.verify(token, 'secret');
    (req as any).user = decoded;
    next();
  } catch (error) {
    res.status(403).json({ error: '無效 Token' });
  }
};

// 註冊
app.post('/api/auth/register', async (req: Request, res: Response): Promise<void> => {
  const { email, password } = req.body;
  const db = await initDatabase();
  try {
    const hash = await bcrypt.hash(password, 10);
    await db.run('INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)', [
      email,
      hash,
      new Date().toISOString(),
    ]);
    res.status(201).json({ message: '註冊成功' });
  } catch (error) {
    res.status(400).json({ error: '註冊失敗：電郵已存在或無效' });
  } finally {
    await db.close();
  }
});

// 登入
app.post('/api/auth/login', async (req: Request, res: Response): Promise<void> => {
  const { email, password } = req.body;
  let db; // 声明 db 在 try 块外部
  try {
    db = await initDatabase();
    const user = await db.get('SELECT * FROM users WHERE email = ?', [email]);
    if (!user || !(await bcrypt.compare(password, user.password_hash))) {
      res.status(401).json({ error: '無效憑證' });
      return;
    }
    const token = jwt.sign({ userId: user.id }, 'secret', { expiresIn: '1h' });
    res.json({ token });
  } catch (error) {
    res.status(500).json({ error: '登入失敗' });
  } finally {
    if (db) await db.close(); // 檢查 db 是否存在
  }
});

// 文件上傳
app.post('/api/files/upload', authenticateToken, upload.single('file'), async (req: Request, res: Response): Promise<void> => {
  const file = req.file;
  const userId = (req as any).user.userId;
  if (!file) {
    res.status(400).json({ error: '無文件' });
    return;
  }

  const filepath = path.join('uploads/users', String(userId), file.filename);
  let db; // 声明 db 在 try 块外部
  try {
    db = await initDatabase();
    await db.run(
      'INSERT INTO files (user_id, filename, filepath, metadata, upload_date) VALUES (?, ?, ?, ?, ?)',
      [userId, file.filename, filepath, JSON.stringify({ tags: [] }), new Date().toISOString()]
    );
    res.json({ message: '上傳成功' });
  } catch (error) {
    res.status(500).json({ error: '上傳失敗' });
  } finally {
    if (db) await db.close(); // 檢查 db 是否存在
  }
});

// 文件列表
app.get('/api/files/list', authenticateToken, async (req: Request, res: Response): Promise<void> => {
  const userId = (req as any).user.userId;
  const db = await initDatabase();
  try {
    const files = await db.all('SELECT id, filename, upload_date FROM files WHERE user_id = ?', [userId]);
    res.json(files);
  } catch (error) {
    res.status(500).json({ error: '獲取文件失敗' });
  } finally {
    await db.close();
  }
});

// 文件下載
app.get('/api/files/download/:fileId', authenticateToken, async (req: Request, res: Response): Promise<void> => {
  const fileId = req.params.fileId;
  const userId = (req as any).user.userId;
  const db = await initDatabase();
  try {
    const file = await db.get('SELECT filename, filepath FROM files WHERE id = ? AND user_id = ?', [fileId, userId]);
    if (!file) {
      res.status(404).json({ error: '文件不存在' });
      return;
    }

    const fullPath = path.join(__dirname, '..', file.filepath);
    if (!fs.existsSync(fullPath)) {
      res.status(404).json({ error: '文件不存在於服務器' });
      return;
    }

    res.download(fullPath, file.filename);
  } catch (error) {
    res.status(500).json({ error: '下載失敗' });
  } finally {
    await db.close();
  }
});

// 刪除文件
app.delete('/api/files/delete/:fileId', authenticateToken, async (req: Request, res: Response): Promise<void> => {
  const fileId = req.params.fileId;
  const userId = (req as any).user.userId;
  const db = await initDatabase();
  try {
    const file = await db.get('SELECT filepath FROM files WHERE id = ? AND user_id = ?', [fileId, userId]);
    if (!file) {
      res.status(404).json({ error: '文件不存在' });
      return;
    }

    const fullPath = path.join(__dirname, '..', file.filepath);
    if (fs.existsSync(fullPath)) {
      fs.unlinkSync(fullPath);
    }
    await db.run('DELETE FROM files WHERE id = ?', [fileId]);
    res.json({ message: '刪除成功' });
  } catch (error) {
    res.status(500).json({ error: '刪除失敗' });
  } finally {
    await db.close();
  }
});

// 搜尋（調用 AI 推薦）
app.get('/api/search', authenticateToken, async (req: Request, res: Response): Promise<void> => {
  const query = req.query.q as string;
  const userId = (req as any).user.userId;
  const db = await initDatabase();
  try {
    const response = await axios.post('http://localhost:5000/recommend', { query, userId });
    const recommendations = response.data;
    await db.run('INSERT INTO search_history (user_id, query, timestamp) VALUES (?, ?, ?)', [
      userId,
      query,
      new Date().toISOString(),
    ]);
    res.json(recommendations);
  } catch (error) {
    res.status(500).json({ error: '搜尋失敗' });
  } finally {
    await db.close();
  }
});

app.listen(3000, () => console.log('服務器運行在端口 3000'));