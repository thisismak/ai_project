# 項目關鍵目標
## 搜尋功能
- 輸入查詢並觸發搜尋
- 顯示本地文件結果
- 顯示外部圖片結果（將來不禁用）
- 用戶偏好增強
- 視覺與交互
- 保存搜尋歷史

# 操作流程
## 終端機01 -後端設置 (操作流程)
打開新終端機
cd backend
npm init -y
npm install express jsonwebtoken bcrypt multer sqlite3 sqlite axios express-fileupload cors dotenv
npm install -D @types/express @types/jsonwebtoken @types/bcrypt @types/multer @types/node @types/express-fileupload @types/cors dotenv
npm install -D typescript
npx tsc --init
npm install -D ts-node
npx ts-node src/server.ts

## 終端機02 - Flask 伺服器設置 (操作流程)
打開新終端機
cd ai
python -m venv venv
source venv/Scripts/activate
pip install -r requirements.txt
playwright install
python recommend.py

## 總終機03 - 資料庫初始化 (操作流程)
打開新終端機
cd ai
python collect_metadata.py

# 重啟服務
cd ai
rm cloud_storage.db
rm -rf Uploads
source venv/Scripts/activate
python recommend.py
cd ai
python collect_metadata.py
cd
cd ../backend
npx ts-node src/server.ts