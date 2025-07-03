
# run.py
import uvicorn
# ถ้า app/main.py ของคุณมี app = FastAPI() อยู่แล้ว:
from app.main import app

if __name__ == '__main__':
    uvicorn.run("app.main:app", host='0.0.0.0', port=5000, reload=True)
    # "app.main:app" หมายถึง ให้หา Object ชื่อ app ในไฟล์ app/main.py