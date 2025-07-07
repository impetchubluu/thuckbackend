# app/db/crud.py
from sqlalchemy.orm import Session, joinedload, selectinload
from . import models
from ..schemas import shipment_schemas, booking_round_schemas
from typing import List, Optional
from datetime import date, datetime, timedelta
from sqlalchemy import func

# --- User CRUD ---
def get_user_by_username(db: Session, username: str) -> Optional[models.SystemUser]:
    return db.query(models.SystemUser).options(joinedload(models.SystemUser.vendor_details)).filter(models.SystemUser.username == username).first()
def get_shipment_by_id(db: Session, shipid: str) -> Optional[models.Shipment]:
    return db.query(models.Shipment).filter(models.Shipment.shipid == shipid).first()
# --- Master Data CRUD ---
def get_warehouses(db: Session) -> List[models.MWarehouse]:
    return db.query(models.MWarehouse).filter(models.MWarehouse.is_active == True).all()
# เพิ่ม 2 ฟังก์ชันนี้เข้าไปในไฟล์ app/db/crud.py

def get_shipments(db: Session, filters: dict = None) -> List[models.Shipment]:
    """
    ดึงรายการ Shipments ทั้งหมด พร้อมความสามารถในการ Filter
    สำหรับ Dispatcher และ Admin
    """
    if filters is None:
        filters = {}
        
    query = db.query(models.Shipment).options(
        selectinload(models.Shipment.details) # โหลด details มาด้วยเพื่อประสิทธิภาพ
    )

    # ตัวอย่างการใช้ Filter
    if filters.get("docstat"):
        query = query.filter(models.Shipment.docstat == filters["docstat"])
    
    if filters.get("is_on_hold") is not None:
        # แปลง string 'true'/'false' เป็น boolean
        is_on_hold_bool = str(filters["is_on_hold"]).lower() == 'true'
        query = query.filter(models.Shipment.is_on_hold == is_on_hold_bool)

    if filters.get("apmdate_from"):
        query = query.filter(models.Shipment.apmdate >= filters["apmdate_from"])
    
    if filters.get("apmdate_to"):
        query = query.filter(models.Shipment.apmdate <= filters["apmdate_to"])
    
    # เพิ่ม Filter อื่นๆ ตามต้องการ
    # ...
    
    return query.order_by(models.Shipment.apmdate.desc()).all()


def get_shipments_for_vendor(db: Session, grade: str) -> List[models.Shipment]:
    """
    ดึงรายการ Shipments ที่ถูกส่งให้ Vendor ตามเกรด
    และมีสถานะรอการตอบรับ (เช่น docstat = '02')
    """
    return (db.query(models.Shipment)
              .options(selectinload(models.Shipment.details))
              .filter(
                  models.Shipment.current_grade_to_assign == grade,
                  models.Shipment.docstat == '02' # สถานะรอ Vendor ตอบรับ
              )
              .order_by(models.Shipment.apmdate.desc())
              .all())
# --- Booking Round CRUD ---
def get_booking_rounds_by_date(db: Session, round_date: date, warehouse_code: str) -> List[models.BookingRound]:
    return (db.query(models.BookingRound)
              .options(selectinload(models.BookingRound.shipments))
              .filter(models.BookingRound.round_date == round_date, models.BookingRound.warehouse_code == warehouse_code)
              .order_by(models.BookingRound.round_time)
              .all())

def create_booking_round(db: Session, round_in: booking_round_schemas.BookingRoundCreate, creator_id: str) -> models.BookingRound:
    db_round = models.BookingRound(
        round_name=round_in.round_name,
        round_date=round_in.round_date,
        round_time=round_in.round_time,
        warehouse_code=round_in.warehouse_code,
        total_volume_cbm=round_in.total_volume_cbm,
        created_by=creator_id,
        status='pending'
    )
    db.add(db_round)
    db.flush()

    if round_in.shipment_ids:
        (db.query(models.Shipment)
           .filter(models.Shipment.shipid.in_(round_in.shipment_ids), models.Shipment.booking_round_id == None)
           .update({"booking_round_id": db_round.id, "docstat": '01'}, synchronize_session=False))

    db.commit()
    db.refresh(db_round)
    return db_round

# --- Shipment CRUD ---
def get_unassigned_shipments(db: Session, filters: dict) -> List[models.Shipment]:
    query = db.query(models.Shipment).filter(models.Shipment.booking_round_id == None, models.Shipment.is_on_hold == False)
    if filters.get("shippoint"):
        query = query.filter(models.Shipment.shippoint == filters["shippoint"])
    if filters.get("apmdate"):
        query = query.filter(func.date(models.Shipment.apmdate) == filters["apmdate"])
    return query.order_by(models.Shipment.shipid).all()

def get_held_shipments(db: Session, filters: dict) -> List[models.Shipment]:
    query = db.query(models.Shipment).filter(models.Shipment.is_on_hold == True)
    # ... add filters ...
    return query.all()
def get_vendor_fcm_token_by_username(db: Session, username: str) -> Optional[str]:
    """ดึง FCM Token ของ Vendor โดยใช้ชื่อผู้ใช้ (Username)"""
    user = db.query(models.SystemUser).filter(models.SystemUser.username == username).first()
    if user and user.fcm_token:
        return user.fcm_token  # คืนค่า FCM Token ของ Vendor
    return None
def update_user_fcm_token(db: Session, user: models.SystemUser, new_token: str) -> models.SystemUser:
    """
    อัปเดต FCM Token สำหรับ User ที่ระบุ
    """
    
    if user:
        user.fcm_token = new_token
        db.commit()
        db.refresh(user)
    return user

def get_users_by_grade(db: Session, grade: str) -> List[models.SystemUser]:
    """
    ดึง User ทั้งหมดในเกรดที่ระบุ (เพื่อส่ง Notification)
    """
    return (db.query(models.SystemUser)
              .join(models.MVendor, models.SystemUser.vencode_ref == models.MVendor.vencode)
              .filter(models.MVendor.grade == grade, models.SystemUser.is_active == True)
              .all())

def get_all_dispatchers(db: Session) -> List[models.SystemUser]:
    """
    ดึง Dispatchers และ Admins ทั้งหมด (เพื่อส่ง Notification)
    """
    return db.query(models.SystemUser).filter(
        models.SystemUser.role.in_([models.UserRoleEnum.dispatcher, models.UserRoleEnum.admin]),
        models.SystemUser.is_active == True
    ).all()
def get_user_by_vencode(db: Session, vencode: str) -> Optional[models.SystemUser]:
    """ดึง SystemUser โดยใช้ vencode_ref"""
    return db.query(models.SystemUser).filter(models.SystemUser.vencode_ref == vencode).first()

def get_car_by_license(db: Session, carlicense: str) -> Optional[models.MCar]:
    """ดึงข้อมูลรถด้วยทะเบียน"""
    return db.query(models.MCar).filter(models.MCar.carlicense == carlicense).first()

def is_car_available(db: Session, carlicense: str, required_datetime: datetime) -> bool:
    """เช็คว่ารถว่าง ณ เวลาที่ต้องการหรือไม่"""
    assignment = (db.query(models.CarAssignment)
        .filter(
            models.CarAssignment.carlisence == carlicense,
            models.CarAssignment.status == 'ASSIGNED',
            models.CarAssignment.estimated_return_date >= required_datetime
        ).first())
    return assignment is None


def complete_or_cancel_car_assignment(db: Session, shipid: str, new_status: str) -> bool:
    """อัปเดตสถานะ car assignment (COMPLETED หรือ CANCELED)"""
    assignment = db.query(models.CarAssignment).filter(models.CarAssignment.shipid == shipid).first()
    if assignment and assignment.status == 'ASSIGNED':
        assignment.status = new_status
        db.commit()
        return True
    return False
# ... (CRUD อื่นๆ สำหรับ Shipment ที่จำเป็น) ...