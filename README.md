cd backend

npm init -y

npm install express jsonwebtoken bcrypt multer sqlite3 sqlite axios

npm install -D @types/express @types/jsonwebtoken @types/bcrypt @types/multer @types/node

npm install -D typescript

npx tsc --init

npm install -D ts-node

npx ts-node src/server.ts