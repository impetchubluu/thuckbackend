# app/main.py
from fastapi import FastAPI
from fastapi.concurrency import asynccontextmanager
from .core import firebase_service
from fastapi.middleware.cors import CORSMiddleware # เพิ่ม CORS Middleware
from .routers import auth_router, user_router
from .db.database import Base, engine # ถ้าจะให้ SQLAlchemy สร้างตาราง
from .routers import (
    auth_router,
    user_router,
    shipment_router, # <<--- ตรวจสอบว่า Import มาถูกต้อง
    master_data_router,
    booking_round_router
)

app = FastAPI(title="Truck Booking API - Login")
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup event
    await firebase_service.initialize_firebase()  # เรียกใช้ฟังก์ชันเชื่อมต่อกับ Firebase ในช่วง startup
    yield  # ให้ FastAPI รันส่วนอื่น ๆ ของแอป
    # Shutdown event (หากต้องการ)
    await firebase_service.close_firebase() 
# --- CORS Middleware ---
# อนุญาตให้ Flutter Web App (หรือ Client อื่นๆ) เรียก API นี้ได้
# ใน Development อาจจะใช้ origins = ["*"]
# ใน Production ควรระบุ Domain ของ Frontend ให้ชัดเจน
origins = [
    "http://localhost",       # ถ้า Flutter Web รันบน Port Default
    "http://localhost:55780",  # Port อื่นๆ ที่ Flutter Web อาจจะใช้
    # "http://your-flutter-web-app.com", # สำหรับ Production
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # หรือ ["*"] เพื่อทดสอบ
    allow_credentials=True,
    allow_methods=["*"],   # อนุญาตทุก Method
    allow_headers=["*"],   # อนุญาตทุก Header
)
# --- End CORS Middleware ---

app.include_router(auth_router.router, prefix="/auth")
app.include_router(user_router.router, prefix="/users")
app.include_router(shipment_router.router, prefix="/api/v1/shipments")
app.include_router(master_data_router.router, prefix="/api/v1/master")
app.include_router(booking_round_router.router, prefix="/api/v1/booking-rounds")
app.include_router(user_router.router, prefix="/api/v1/users", tags=["Users & Profiles"])
@app.get("/")
async def root():
    return {"message": "Welcome to Truck Booking API! Use /auth/login to login."}