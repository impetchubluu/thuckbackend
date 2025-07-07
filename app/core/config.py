# app/core/config.py
import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv
from urllib.parse import quote_plus

# --- ส่วนที่ 1: โหลดไฟล์ .env ---
# คำนวณ Path ไปยังไฟล์ .env ที่ Root ของโปรเจกต์
# __file__ คือ Path ของไฟล์ปัจจุบัน (app/core/config.py)
current_file_dir = os.path.dirname(os.path.abspath(__file__)) # Path ของ app/core/
app_dir = os.path.dirname(current_file_dir) # Path ของ app/
project_root = os.path.dirname(app_dir) # Path ของ Root Project
dotenv_path = os.path.join(project_root, '.env')

if os.path.exists(dotenv_path):
    print(f"INFO: Loading .env file from: {dotenv_path}")
    load_dotenv(dotenv_path=dotenv_path, override=True) # override=True ทำให้ค่าใน .env ทับค่าใน Environment ของระบบ (ถ้ามีชื่อซ้ำ)
else:
    print(f"WARNING: .env file not found at: {dotenv_path}. Using system environment variables or defaults.")

class Settings(BaseSettings):
    # --- ส่วนที่ 2: Pydantic อ่านจาก Environment Variables ---
    # Pydantic จะพยายามหา Environment Variable ที่ชื่อตรงกับ Attribute (Case Insensitive)
    # ถ้าไม่เจอ จะใช้ค่า Default ที่ระบุใน os.getenv() หรือค่า Default ของ Pydantic Field เอง

    # Database Configuration - อ่านค่าดิบจาก Env หรือใช้ Default
    DB_HOST: str = os.getenv("DB_HOST", "fallback_host") # Fallback ถ้าไม่มีใน Env
    DB_USER: str = os.getenv("DB_USER", "fallback_user")
    DB_PASS: str = os.getenv("DB_PASS", "fallback_pass")
    DB_NAME: str = os.getenv("DB_NAME", "fallback_db")
    FIREBASE_SERVICE_ACCOUNT_PATH: str = (r"D:\y1\internship\py\app\firebase_service_account.json")
    @property
    def DATABASE_URL(self) -> str:
        # ใช้ค่าที่ Pydantic ได้อ่านมา (ซึ่งก็คือค่าที่ os.getenv ดึงมา)
        # หรือจะเรียก os.getenv อีกครั้งก็ได้ แต่เพื่อให้สอดคล้องกับ Attribute ที่ Pydantic จัดการ
        db_user = self.DB_USER
        db_pass_raw = self.DB_PASS
        db_host = self.DB_HOST
        db_name = self.DB_NAME

        if not all([db_user, db_pass_raw, db_host, db_name]):
             print("WARNING: One or more DB configuration values are missing. Using fallbacks or defaults may lead to connection errors.")
             # อาจจะ raise Exception ที่นี่ถ้าต้องการให้ App หยุดทำงานถ้า Config ไม่ครบ

        encoded_pass = quote_plus(db_pass_raw)
        return f"mysql+pymysql://{db_user}:{encoded_pass}@{db_host}/{db_name}"

    # JWT Configuration
    SECRET_KEY: str = os.getenv("SECRET_KEY", "default_very_unsafe_secret_key")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

    # Pydantic V2 model_config
    model_config = SettingsConfigDict(
        env_file=dotenv_path, # Pydantic สามารถโหลด .env ได้เองด้วย (ถ้า python-dotenv ไม่ได้โหลด)
        env_file_encoding='utf-8',
        extra='ignore' # ถ้ามี Variable อื่นใน .env ที่ไม่ได้ Define ใน Settings ก็ให้ Ignore
    )

settings = Settings()
