import express, { Request, Response } from 'express';
import axios from 'axios';
import sqlite3 from 'sqlite3';
import { open } from 'sqlite';
import jwt from 'jsonwebtoken';
import fileUpload from 'express-fileupload';
import cors from 'cors';

const app = express();
app.use(express.json());
app.use(fileUpload());
app.use(cors());

const JWT_SECRET = 'your_jwt_secret'; // 替換為實際密鑰

async function initDatabase() {
  return open({
    filename: '../ai/cloud_storage.db',
    driver: sqlite3.Database
  });
}

// 驗證 JWT
function authenticateToken(req: Request, res: Response, next: Function) {
  const authHeader = req.headers['authorization'];
  const token = authHeader && authHeader.split(' ')[1];
  if (!token) return res.status(401).json({ error: '未授權' });
  jwt.verify(token, JWT_SECRET, (err, user) => {
    if (err) return res.status(403).json({ error: '無效令牌' });
    (req as any).user = user;
    next();
  });
}

// 搜尋
app.get('/api/search', authenticateToken, async (req: Request, res: Response): Promise<void> => {
  const query = req.query.q as string;
  const userId = (req as any).user.userId;
  const db = await initDatabase();
  try {
    const response = await axios.post('http://localhost:5000/recommend', { query, userId });
    const { local_files, external_images } = response.data;
    await db.run('INSERT INTO search_history (user_id, query, timestamp) VALUES (?, ?, ?)', [
      userId,
      query,
      new Date().toISOString(),
    ]);
    res.json({ local_files, external_images });
  } catch (error) {
    res.status(500).json({ error: '搜尋失敗' });
  } finally {
    await db.close();
  }
});

// 上傳文件
app.post('/api/upload', authenticateToken, async (req: Request, res: Response) => {
  const userId = (req as any).user.userId;
  const file = req.files?.file as any;
  const tags = req.body.tags;
  if (!file || !tags) {
    return res.status(400).json({ error: '缺少文件或標籤' });
  }
  const filename = file.name;
  const filepath = `Uploads/users/${userId}/${filename}`;
  const metadata = JSON.stringify({ tags: tags.split(',').map((tag: string) => tag.trim()) });
  const db = await initDatabase();
  try {
    await file.mv(filepath);
    await db.run('INSERT INTO files (user_id, filename, filepath, metadata) VALUES (?, ?, ?, ?)', [
      userId, filename, filepath, metadata
    ]);
    res.json({ message: '上傳成功' });
  } catch (error) {
    res.status(500).json({ error: '上傳失敗' });
  } finally {
    await db.close();
  }
});

// 假設登錄端點
app.post('/api/login', async (req: Request, res: Response) => {
  const { username, password } = req.body;
  // 簡化驗證，實際應檢查數據庫
  if (username === 'test' && password === 'test') {
    const token = jwt.sign({ userId: '1' }, JWT_SECRET, { expiresIn: '1h' });
    res.json({ token, userId: '1' });
  } else {
    res.status(401).json({ error: '無效憑證' });
  }
});

app.listen(3000, () => console.log('後端運行於 http://localhost:3000'));