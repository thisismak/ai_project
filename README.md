# 操作流程
## 終端機01 -後端設置 (操作流程)

打開新終端機

cd backend

npm init -y

npm install express jsonwebtoken bcrypt multer sqlite3 sqlite axios express-fileupload cors

npm install -D @types/express @types/jsonwebtoken @types/bcrypt @types/multer @types/node @types/express-fileupload @types/cors

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

## 總終機03 - 資料庫填充 (操作流程)

打開新終端機

cd ai

python collect_metadata.py