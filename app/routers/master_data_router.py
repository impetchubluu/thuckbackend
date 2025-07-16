# app/routers/master_data_router.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List

from ..db import crud, database
# VVVVVV แก้ไขการ Import ที่นี่ VVVVVV
from ..schemas import master_data_schemas, warehouse_schemas
from app import db

from app import schemas # Import Submodules ที่ต้องการใช้

router = APIRouter(
    tags=["Master Data"]
)

@router.get("/warehouses", response_model=List[warehouse_schemas.Warehouse]) # <<--- อ้างอิงผ่าน Submodule ที่ Import มา
async def get_all_warehouses(db_session: Session = Depends(database.get_db)):
    return crud.get_warehouses(db_session)

# ตัวอย่างสำหรับ Route อื่นในไฟล์เดียวกัน
@router.get("/doc-statuses", response_model=List[master_data_schemas.ControlCode])
async def get_document_statuses(db_session: Session = Depends(database.get_db)):
    return crud.get_control_codes_by_key(db_session, key='DOCST')
@router.get("/booking-rounds", response_model=List[schemas.master_data_schemas.MasterBookingRound])
async def get_master_rounds(db_session: Session = Depends(db.database.get_db)):
    """
    ดึงข้อมูล Master สำหรับรอบเวลาทั้งหมดที่ Active อยู่
    """
    return db.crud.get_master_booking_rounds(db_session)

