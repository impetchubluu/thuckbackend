# app/db/crud.py
from sqlalchemy.orm import Session, joinedload, selectinload
from . import models
from ..schemas import shipment_schemas, booking_round_schemas
from typing import List, Optional
from datetime import date, datetime, timedelta, time
from sqlalchemy import and_, func, not_, or_
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
        selectinload(models.Shipment.details),  # Eager load details
        joinedload(models.Shipment.warehouse),  # Eager load warehouse
        joinedload(models.Shipment.mshiptype),  # Eager load ship type
        joinedload(models.Shipment.mleadtime)   # Eager load lead time
    )
    

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

    
    return query.order_by(models.Shipment.apmdate.desc()).all()


def get_vendor_by_grade(db: Session, grade: str) -> Optional[models.SystemUser]:
    """ดึง User คนแรกที่เจอในเกรดที่ระบุ"""
    return (db.query(models.SystemUser)
              .join(models.MVendor, models.SystemUser.vencode_ref == models.MVendor.vencode)
              .filter(models.MVendor.grade == grade)
              .first())

def get_shipments_for_vendor(db: Session, grade: str, vencode: str) -> List[models.Shipment]:
    """
    ดึงรายการ Shipments สำหรับ Vendor
    - งานที่ถูกส่งให้เกรดของตนเองโดยเฉพาะ (docstat='02')
    - งานเปิดที่ทุกคนเห็น (docstat='BC')
    """
    return (db.query(models.Shipment)
              .options(selectinload(models.Shipment.details))
              .filter(
    or_(
        # เงื่อนไขกลุ่มที่ 1: ต้องเป็นจริงทั้งสองอย่าง
        and_(
            models.Shipment.docstat == '02',
            models.Shipment.current_grade_to_assign == grade
        ),
        
        # เงื่อนไขกลุ่มที่ 2
           and_(
                          models.Shipment.docstat == 'BC',
                          # --- แก้ไขเงื่อนไขนี้ ---
                          or_(
                              # กรณีที่ยังไม่มีใครปฏิเสธเลย (field เป็น NULL)
                              models.Shipment.rejected_by_vencodes.is_(None),
                              # กรณีที่มีคนปฏิเสธแล้ว และเราไม่ได้อยู่ในนั้น
                              not_(models.Shipment.rejected_by_vencodes.contains(vencode))
                          )
                      )
    )
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
    query = (db.query(models.Shipment)
               # --- จุดสำคัญคือบรรทัดนี้ ---
                .options(
                   joinedload(models.Shipment.warehouse),
                   joinedload(models.Shipment.mshiptype),
                   joinedload(models.Shipment.mleadtime),
               )
               .filter(models.Shipment.booking_round_id == None, models.Shipment.is_on_hold == False)
    )

    if filters.get("shippoint"):
        query = query.filter(models.Shipment.shippoint == filters["shippoint"])
    if filters.get("apmdate"):
        # แปลง string date เป็น date object ก่อนเทียบ
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
def assign_job_to_car(db: Session, shipment: models.Shipment) -> Optional[models.MCar]:
    """
    ฟังก์ชันหลักในการจ่ายงานให้รถ:
    1. ตรวจสอบข้อมูลที่จำเป็น
    2. คำนวณวันที่รถจะว่าง
    3. อัปเดตสถานะและวันที่ว่างของรถ
    """
    # 1. ตรวจสอบข้อมูล
    if not (shipment.carlicense and shipment.apmdate and shipment.route and shipment.province is not None):
        print(f"WARNING: Shipment {shipment.shipid} is missing required data for availability calculation.")
        return None

    # 2. ดึงข้อมูลรถและ Lead Time
    car_to_update = db.query(models.MCar).filter(models.MCar.carlicense == shipment.carlicense).first()
    if not car_to_update:
        print(f"ERROR: Car with license {shipment.carlicense} not found.")
        return None

    # ดึง Lead Time
    province_obj = db.query(models.MProvince).filter(models.MProvince.province == shipment.province).first()
    if not province_obj:
        print(f"ERROR: Province with ID {shipment.province} not found.")
        return None

    lead_time_obj = db.query(models.MLeadTime).filter(
        models.MLeadTime.route == shipment.route
                ).first()

    if not lead_time_obj or not lead_time_obj.leadtime:
        print(f"ERROR: Lead time not found for route {shipment.route} and province {province_obj.provname}.")
        return None
        
    lead_time_days = int(lead_time_obj.leadtime)

    # 3. คำนวณวันที่รถจะว่าง
    appointment_date = shipment.apmdate.date()
    available_date = appointment_date + timedelta(days=lead_time_days - 1)

    # 4. อัปเดตข้อมูลรถ
    car_to_update.stat = models.StandardStatEnum.inactive # เปลี่ยนสถานะเป็น "ไม่ใช้งาน"
    car_to_update.will_be_available_at = available_date

    # 5. ไม่ต้อง commit ที่นี่ ให้ Router เป็นตัวจัดการ Transaction
    
    print(f"INFO: Car {car_to_update.carlicense} availability will be updated to {available_date.isoformat()}.")
    return car_to_update
def update_user_fcm_token(db: Session, user: models.SystemUser, new_token: str) -> models.SystemUser:
    """
    อัปเดต FCM Token สำหรับ User ที่ระบุ
    """
    
    if user:
        user.fcm_token = new_token
        db.commit()
        db.refresh(user)
    return user
def get_shipment_for_update(db: Session, shipid: str) -> Optional[models.Shipment]:
    """
    ดึงข้อมูล Shipment พร้อมกับ Lock แถวข้อมูลนั้นใน Transaction
    เพื่อป้องกัน Race Condition
    """
    return db.query(models.Shipment).filter(models.Shipment.shipid == shipid).with_for_update().first()

def get_all_vendor_profiles(db: Session) -> List[models.MVendor]:
    """
    ดึงข้อมูลโปรไฟล์ของ Vendor ทั้งหมด (สำหรับ Admin/Dispatcher)
    พร้อมกับ Eager Load ข้อมูลรถของแต่ละ Vendor มาด้วย
    """
    return (db.query(models.MVendor)
              .options(
                  selectinload(models.MVendor.cars),
                  selectinload(models.MVendor.user_account)
              )
              .order_by(models.MVendor.grade, models.MVendor.venname) # เรียงตามเกรด และตามชื่อ
              .all())
def get_all_vendors(db: Session) -> List[models.SystemUser]:
    """ดึง user ที่มี role เป็น vendor ทั้งหมด"""
    return db.query(models.SystemUser).filter(models.SystemUser.role == models.UserRoleEnum.vendor, models.SystemUser.is_active == True).all()
def get_users_by_grade(db: Session, grade: str) -> List[models.SystemUser]:
    """
    ดึง User ทั้งหมดในเกรดที่ระบุ (เพื่อส่ง Notification)
    """
    return (db.query(models.SystemUser)
              .join(models.MVendor, models.SystemUser.vencode_ref == models.MVendor.vencode)
              .filter(models.MVendor.grade == grade, models.SystemUser.is_active == True)
              .all())
def get_ongoing_shipments(db: Session, vencode: Optional[str] = None) -> List[models.Shipment]:
    """
    ดึงรายการ Shipments ที่กำลังดำเนินการอยู่
    - ถ้ามี vencode: ดึงเฉพาะของ Vendor คนนั้น
    - ถ้าไม่มี vencode (None): ดึงของทุก Vendor (สำหรับ Admin/Dispatcher)
    """
    in_progress_statuses = ['03', '04', '05']
    
    query = (db.query(models.Shipment)
               .options(selectinload(models.Shipment.details))
               .filter(models.Shipment.docstat.in_(in_progress_statuses)))
    
    # เพิ่มเงื่อนไขการกรอง vencode ถ้ามีการส่งค่าเข้ามา
    if vencode:
        query = query.filter(models.Shipment.vencode == vencode)
        
    return query.order_by(models.Shipment.apmdate.asc()).all()


def get_past_shipments(db: Session, vencode: Optional[str] = None, filters: dict = None) -> List[models.Shipment]:
    """
    ดึงประวัติงานที่เสร็จสิ้นหรือยกเลิกไปแล้ว
    - ถ้ามี vencode: ดึงเฉพาะของ Vendor คนนั้น
    - ถ้าไม่มี vencode: ดึงของทุก Vendor (สำหรับ Admin/Dispatcher)
    - รองรับการ Filter เพิ่มเติม
    """
    if filters is None:
        filters = {}

    final_statuses = ['06', 'RJ', '05'] # เพิ่ม 05 เข้าไปด้วย
    
    query = (db.query(models.Shipment)
               .options(selectinload(models.Shipment.details)) # Eager load details
               .filter(models.Shipment.docstat.in_(final_statuses)))
    
    # --- Logic เดิม ---
    if vencode:
        query = query.filter(models.Shipment.vencode == vencode)
    
    # --- เพิ่ม Logic การ Filter สำหรับ Admin/Dispatcher ---
    if filters.get("shipid"):
        query = query.filter(models.Shipment.shipid.like(f"%{filters['shipid']}%"))
    
    if filters.get("route"):
        # ต้อง JOIN กับ details (DOH) เพื่อ filter ตาม route
        # SQLAlchemy จะทำ auto-join ถ้ามี relationship แต่เพื่อความชัดเจน เราใช้ join()
        query = query.join(models.DOH).filter(models.DOH.route == filters["route"])

    if filters.get("apmdate_from"):
        query = query.filter(models.Shipment.apmdate >= filters["apmdate_from"])
        
    if filters.get("apmdate_to"):
        # บวก 1 วันเพื่อให้รวมวันสิ้นสุดเข้าไปด้วย
        end_date = datetime.fromisoformat(filters["apmdate_to"]) + timedelta(days=1)
        query = query.filter(models.Shipment.apmdate < end_date)

    return query.order_by(models.Shipment.chdate.desc()).limit(200).all()
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

def get_master_booking_rounds(db: Session) -> List[models.MBookingRound]:
    """ดึง Master เวลารอบทั้งหมดที่ Active"""
    return db.query(models.MBookingRound).filter(models.MBookingRound.is_active == True).order_by(models.MBookingRound.round_time).all()
def save_day_rounds(db: Session, request: booking_round_schemas.SaveDayRoundsRequest, creator_id: str):
    """
    จัดการการบันทึกรอบของทั้งวัน (ลบอันเก่าที่ไม่มี, สร้าง/อัปเดตอันใหม่)
    """
    # 1. ดึงรอบทั้งหมดที่มีอยู่แล้วสำหรับวันและคลังสินค้านี้
    existing_rounds = db.query(models.BookingRound).filter(
        models.BookingRound.round_date == request.round_date,
        models.BookingRound.warehouse_code == request.warehouse_code
    ).all()

    # 2. ลบรอบเก่าที่ไม่มีอยู่ใน Request ใหม่
    # (วิธีนี้ง่ายที่สุด คือลบทั้งหมดแล้วสร้างใหม่)
    for old_round in existing_rounds:
        # ก่อนลบ ต้อง un-assign shipments ก่อน
        (db.query(models.Shipment)
           .filter(models.Shipment.booking_round_id == old_round.id)
           .update({"booking_round_id": None}, synchronize_session=False))
        db.delete(old_round)
    
    db.flush() # Execute delete commands

    # 3. สร้างรอบใหม่ทั้งหมดตามที่ส่งมา
    new_rounds = []
    for i, round_data in enumerate(request.rounds):
        try:
            # แปลง string "HH:mm" เป็น time object
            time_parts = round_data.round_time_str.split(':')
            new_time = time(hour=int(time_parts[0]), minute=int(time_parts[1]))
        except (ValueError, IndexError):
            continue # ข้ามถ้า format เวลาผิด

        db_round = models.BookingRound(
            round_name=f"รอบที่ {i + 1}",
            round_date=request.round_date,
            round_time=new_time,
            warehouse_code=request.warehouse_code,
            created_by=creator_id,
            status='pending'
        )
        db.add(db_round)
        new_rounds.append(db_round)
    
    db.commit()
    
    # ไม่จำเป็นต้อง refresh object เพราะเราจะ query ใหม่จาก frontend
    # แต่ถ้าต้องการคืนค่ากลับไป ก็ต้อง query ใหม่อีกครั้ง
    return True