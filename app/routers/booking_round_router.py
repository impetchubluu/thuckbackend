# app/routers/booking_round_router.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List
from datetime import date

from app.db import crud, models

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
@router.get("/pending-confirmation", response_model=List[schemas.booking_round_schemas.BookingRound], summary="Get rounds waiting for dispatcher confirmation")
def get_rounds_pending_dispatcher_confirmation(
    db_session: Session = Depends(db.database.get_db),
    current_user: models.SystemUser = Depends(security.get_current_active_user)
):
    """
    ดึงข้อมูลรอบทั้งหมดที่มี Shipment อยู่ในสถานะ '03' (Vendor Confirmed)
    """
    if current_user.role not in [models.UserRoleEnum.dispatcher, models.UserRoleEnum.admin]:
        raise HTTPException(status_code=403, detail="Not authorized")
    return crud.get_rounds_pending_confirmation(db_session)

@router.get("/{round_id}", response_model=schemas.booking_round_schemas.BookingRound)
def get_single_booking_round(
    round_id: int,
    db_session: Session = Depends(db.database.get_db),
    # current_user: models.SystemUser = Depends(security.get_current_active_user) # ถ้าต้องการ Auth
):
    """
    ดึงข้อมูลรอบการจองเดียวตาม ID พร้อมกับ Shipments ทั้งหมดในรอบนั้น
    """
    db_round = db.crud.get_booking_round_by_id(db_session, round_id=round_id)
    if not db_round:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Booking round with ID {round_id} not found"
        )
    return db_round
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
@router.post("/save-for-day", status_code=status.HTTP_200_OK)
async def save_rounds_for_day(
    request_body: schemas.booking_round_schemas.SaveDayRoundsRequest,
    current_user: models.SystemUser = Depends(security.get_current_active_user),
    db_session: Session = Depends(db.database.get_db)
):
    """
    รับลิสต์ของรอบทั้งหมดสำหรับวัน/คลังที่ระบุ และทำการ Sync (ลบ/สร้างใหม่)
    """
    if current_user.role not in [models.UserRoleEnum.dispatcher, models.UserRoleEnum.admin]:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    try:
        crud.save_day_rounds(db=db_session, request=request_body, creator_id=current_user.username)
        return {"message": "Booking rounds for the day have been saved successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save rounds: {e}")
@router.post("/{round_id}/assign-all", response_model=schemas.booking_round_schemas.BookingRound, summary="Assign all ready shipments to this round")
def assign_all_to_round(
    round_id: int,
    # เราต้องรับ crdate และ shippoint มาจาก Frontend เพื่อให้รู้ว่าจะดึง unassigned shipments ชุดไหน
    crdate: date = Query(..., description="The appointment date of the shipments to assign"),
    shippoint: str = Query(..., description="The shippoint of the shipments to assign"),
    db_session: Session = Depends(db.database.get_db),
    current_user: models.SystemUser = Depends(security.get_current_active_user)
):
    """
    นำ Shipments ทั้งหมดที่พร้อม (Unassigned & Not on Hold)
    สำหรับวันที่และคลังที่ระบุ มาใส่ในรอบนี้ทั้งหมด
    """
    if current_user.role not in [models.UserRoleEnum.dispatcher, models.UserRoleEnum.admin]:
        raise HTTPException(status_code=403, detail="Not authorized")

    try:
        updated_round = crud.assign_all_ready_shipments_to_round(
            db=db_session, 
            round_id=round_id, 
            crdate=crdate,
            shippoint=shippoint
        )
        return updated_round
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {e}")

@router.post("/{round_id}/allocate", status_code=status.HTTP_200_OK, summary="Start allocation process for a booking round")
def start_allocation_for_round(
    round_id: int,
    db_session: Session = Depends(db.database.get_db),
    current_user: models.SystemUser = Depends(security.get_current_active_user)
):
    """
    เริ่มกระบวนการจัดสรรและจ่ายงานทั้งหมดในรอบที่ระบุ (สำหรับ Dispatcher)
    โดยใช้ Logic การแบ่งโควต้าตามเกรด
    """
    # 1. ตรวจสอบสิทธิ์
    if current_user.role not in [models.UserRoleEnum.dispatcher, models.UserRoleEnum.admin]:
        raise HTTPException(status_code=403, detail="Not authorized")

    try:
        # 2. เรียกใช้ฟังก์ชัน CRUD หลักที่เราเคยสร้างไว้
        crud.allocate_shipments_in_round(db=db_session, round_id=round_id)
        
        # 3. คืนค่า Response สำเร็จ
        return {"message": f"Allocation process for round {round_id} has been started successfully."}

    except ValueError as e:
        # ดักจับ Error ที่เรา raise ไว้ใน CRUD (เช่น Round not found)
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        # ดักจับ Error อื่นๆ ที่ไม่คาดคิด
        print(f"CRITICAL: Allocation for round {round_id} failed: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to allocate shipments: {e}")


@router.post("/{round_id}/confirm-assignment", response_model=schemas.booking_round_schemas.BookingRound, summary="Dispatcher confirms all assignments in a round")
def confirm_round_assignments(
    round_id: int,
    db_session: Session = Depends(db.database.get_db),
    current_user: models.SystemUser = Depends(security.get_current_active_user)
):
    """
    ยืนยันการจ่ายงานทั้งหมดในรอบนี้
    - เปลี่ยนสถานะ Shipments จาก '03' -> '04'
    - อัปเดตสถานะรถที่เกี่ยวข้องทั้งหมด
    """
    if current_user.role not in [models.UserRoleEnum.dispatcher, models.UserRoleEnum.admin]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    try:
        updated_round = crud.confirm_all_shipments_in_round(
            db=db_session, 
            round_id=round_id, 
            current_user_id=current_user.username
        )
        return updated_round
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

