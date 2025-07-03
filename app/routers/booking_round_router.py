# app/routers/booking_round_router.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List
from datetime import date

from .. import db, schemas
from ..core import security

router = APIRouter(
    tags=["Booking Rounds"],
    # ถ้าทุก Endpoint ในนี้ต้องการ Auth ให้ใส่ Dependency ที่นี่
    # dependencies=[Depends(security.get_current_active_user)]
)

@router.get("", response_model=List[schemas.booking_round_schemas.BookingRound])
async def get_booking_rounds_by_date(
    # ใช้ Query() เพื่อรับค่าจาก Query Parameters พร้อม Validation
    round_date: date = Query(..., description="Date in YYYY-MM-DD format"),
    warehouse_code: str = Query(..., description="Warehouse code (e.g., WH7, SW)"),
    db_session: Session = Depends(db.database.get_db),
    # current_user: models.SystemUser = Depends(security.get_current_active_user) # ถ้าต้องการ Auth
):
    """
    ดึงข้อมูลรอบการจองทั้งหมดสำหรับวันที่และคลังสินค้าที่ระบุ
    """
    return db.crud.get_booking_rounds_by_date(db_session, round_date=round_date, warehouse_code=warehouse_code)


@router.post("", response_model=schemas.booking_round_schemas.BookingRound, status_code=status.HTTP_201_CREATED)
async def create_new_booking_round(
    round_in: schemas.booking_round_schemas.BookingRoundCreate,
    current_user: db.models.SystemUser = Depends(security.get_current_active_user), # การสร้างรอบต้องใช้ Auth
    db_session: Session = Depends(db.database.get_db)
):
    """
    สร้างรอบการจองใหม่ และ Assign Shipments เข้ารอบ (สำหรับ Dispatcher)
    """
    if current_user.role not in [db.models.UserRoleEnum.dispatcher, db.models.UserRoleEnum.admin]:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    # TODO: เพิ่ม Validation เช่น ไม่สามารถสร้างรอบซ้ำในวันและเวลาเดียวกันได้
    return db.crud.create_booking_round(db=db_session, round_in=round_in, creator_id=current_user.username)