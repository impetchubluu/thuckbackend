# app/db/crud.py
from collections import defaultdict
import math
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core import firebase_service
from . import models
from ..schemas import shipment_schemas, booking_round_schemas
from typing import List, Optional
from datetime import date, datetime, timedelta, time, timezone
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
def get_booking_round_by_id(db: Session, round_id: int) -> Optional[models.BookingRound]:
    """
    ดึงข้อมูล BookingRound เดียวตาม ID พร้อม Eager Load Shipments
    """
    return (
        db.query(models.BookingRound)
          .options(
              selectinload(models.BookingRound.shipments)
          )
          .filter(models.BookingRound.id == round_id)
          .first()
    )
def get_booking_rounds_by_date(db: Session, round_date: date, warehouse_code: str) -> List[models.BookingRound]:
    return (
        db.query(models.BookingRound)
          .options(
              selectinload(models.BookingRound.shipments)
          )
          .filter(
              models.BookingRound.round_date == round_date, 
              models.BookingRound.warehouse_code == warehouse_code
          )
          .order_by(models.BookingRound.round_time)
          .all()
    )
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
        shipments_to_assign = (
            db.query(models.Shipment)
            .filter(
                models.Shipment.shipid.in_(round_in.shipment_ids),
                models.Shipment.booking_round_id.is_(None), # ป้องกันการ assign ซ้ำ
                models.Shipment.is_on_hold == False # ป้องกันการ assign งานที่ถูก hold
            )
        )
        shipments_to_assign.update({"booking_round_id": db_round.id, "docstat": '01'}, synchronize_session=False)
    (db.query(models.Shipment)
       .filter(models.Shipment.is_on_hold == True)
       .update({"is_on_hold": False, "docstat": models.Shipment.docstat_before_hold}, synchronize_session=False))
    db.commit()
    db.refresh(db_round)
    return db_round
def toggle_shipment_hold_status(db: Session, shipid: str, hold: bool, current_user_id: str) -> Optional[models.Shipment]:
    """
    สลับสถานะ Hold ของ Shipment
    """
    db_shipment = db.query(models.Shipment).filter(models.Shipment.shipid == shipid).first()
    if not db_shipment:
        return None
    
    # สามารถ Hold ได้เฉพาะงานที่ยังไม่เข้ารอบ
    if db_shipment.booking_round_id is not None:
        # อาจจะ return error หรือแค่ return object เดิมไปเฉยๆ
        return None

    try:
        if hold: # ถ้าต้องการ "Hold"
            if not db_shipment.is_on_hold:
                db_shipment.docstat_before_hold = db_shipment.docstat # เก็บสถานะเดิม
                db_shipment.is_on_hold = True
                # ไม่ต้องเปลี่ยน docstat เป็น 'HD' แล้ว เพราะ is_on_hold จะเป็นตัวควบคุม
        else: # ถ้าต้องการ "Unhold"
            if db_shipment.is_on_hold:
                db_shipment.is_on_hold = False
                # คืนสถานะกลับไปเป็นสถานะเดิมก่อน Hold
                db_shipment.docstat = db_shipment.docstat_before_hold 
                db_shipment.docstat_before_hold = None

        db_shipment.chuser = current_user_id
        db_shipment.chdate = datetime.now(timezone.utc)
        db.commit()
        db.refresh(db_shipment)
        return db_shipment
    except Exception as e:
        db.rollback()
        print(f"ERROR: Failed to toggle hold status for shipment {shipid}: {e}")
        return None
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
    if filters.get("crdate"):
        # แปลง string date เป็น date object ก่อนเทียบ
        query = query.filter(func.date(models.Shipment.apmdate) == filters["crdate"]) 
        
    return query.order_by(models.Shipment.shipid).all()
def get_held_shipments(db: Session, filters: dict) -> List[models.Shipment]:
    """
    ดึงรายการ Shipments ที่ถูก Hold ไว้
    """
    query = (db.query(models.Shipment)
             .options(
                 joinedload(models.Shipment.warehouse),
                 joinedload(models.Shipment.mshiptype),
                 joinedload(models.Shipment.mleadtime),
                 selectinload(models.Shipment.details)
             )
             .filter(models.Shipment.is_on_hold == True))
    
    # Apply filters if provided
    if filters:
        if filters.get("shippoint"):
            query = query.filter(models.Shipment.shippoint == filters["shippoint"])
        if filters.get("apmdate_from"):
            query = query.filter(models.Shipment.apmdate >= filters["apmdate_from"])
        if filters.get("apmdate_to"):
            query = query.filter(models.Shipment.apmdate <= filters["apmdate_to"])
    
    return query.order_by(models.Shipment.apmdate.desc()).all()
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
# แทนที่ฟังก์ชันเดิมใน app/db/crud.py ด้วยอันนี้
# เพิ่มฟังก์ชันนี้ใน app/db/crud.py

def assign_all_ready_shipments_to_round(db: Session, round_id: int, crdate: date, shippoint: str) -> models.BookingRound:
    """
    ค้นหา Shipments ทั้งหมดที่ยังไม่ถูกจัดสรรและไม่ถูก Hold
    สำหรับ crdate และ shippoint ที่กำหนด แล้ว Assign เข้ารอบทั้งหมด
    """
    # 1. ตรวจสอบว่ารอบที่ระบุมีอยู่จริง
    booking_round = db.query(models.BookingRound).filter(models.BookingRound.id == round_id).first()
    if not booking_round:
        raise ValueError(f"Booking round with ID {round_id} not found.")

    # --- 2. ค้นหา Shipments ที่ถูกต้อง ---
    # เราจะไม่เรียก get_unassigned_shipments แล้ว แต่จะเขียน query ใหม่ที่นี่เลย
    # เพื่อให้แน่ใจว่าเรา filter ด้วย crdate จริงๆ
    shipments_to_assign = (
        db.query(models.Shipment)
        .filter(
            models.Shipment.booking_round_id.is_(None),
            models.Shipment.is_on_hold == False,
            models.Shipment.shippoint == shippoint,
            # --- ใช้ func.date() เพื่อเปรียบเทียบเฉพาะส่วนวันที่ของ crdate ---
            func.date(models.Shipment.crdate) == crdate 
        )
        .all()
    )

    if not shipments_to_assign:
        print(f"INFO: No unassigned shipments found for crdate={crdate} at shippoint={shippoint} to assign to round {round_id}.")
        return booking_round
    
    shipment_ids_to_update = [s.shipid for s in shipments_to_assign]

    # 3. ทำการ Update Shipments ทั้งหมดใน List ให้มี booking_round_id ที่ถูกต้อง
    (db.query(models.Shipment)
       .filter(models.Shipment.shipid.in_(shipment_ids_to_update))
       .update({"booking_round_id": round_id, "docstat": '01'}, synchronize_session=False)) # '01' = รอจัดสรร

    # 4. (Optional) Unhold งานที่เหลือ
    # ถ้าต้องการให้งานที่เคย Hold ไว้ กลับมาพร้อมสำหรับรอบหน้า ก็ใส่ Logic นี้
    (db.query(models.Shipment)
       .filter(models.Shipment.is_on_hold == True, models.Shipment.shippoint == shippoint)
       .update({"is_on_hold": False, "docstat": models.Shipment.docstat_before_hold}, synchronize_session=False))

    db.commit()
    db.refresh(booking_round) # Refresh เพื่อให้ booking_round.shipments มีข้อมูลล่าสุด
    
    return booking_round
def allocate_shipments_in_round(db: Session, round_id: int):
    """
    จัดสรรงานในรอบที่ระบุโดยหา Vendor ที่เหมาะสมที่สุดสำหรับแต่ละ Shipment ก่อน
    แล้วจึงพิจารณาโควต้าของแต่ละเกรด
    """
    # 1. ดึงข้อมูลรอบและ Shipments (เหมือนเดิม)
    booking_round = db.query(models.BookingRound).filter(models.BookingRound.id == round_id).first()
    if not booking_round:
        raise ValueError(f"Booking round {round_id} not found.")

    shipments_to_allocate = [s for s in booking_round.shipments if s.docstat == '01']
    if not shipments_to_allocate:
        print(f"INFO: No shipments to allocate in round {round_id}.")
        return

    # 2. เตรียมข้อมูล Vendor ทั้งหมดที่มีรถพร้อมใช้งาน
    vendor_car_types_query = (
        db.query(models.MVendor, models.MCar.cartype)
        .join(models.MCar, models.MVendor.vencode == models.MCar.vencode)
        .filter(models.MCar.stat == models.StandardStatEnum.active)
        .all()
    )
    
    vendor_data_map = defaultdict(lambda: {'vendor_obj': None, 'car_types': set()})
    for vendor, cartype in vendor_car_types_query:
        vendor_data_map[vendor.vencode]['vendor_obj'] = vendor
        vendor_data_map[vendor.vencode]['car_types'].add(cartype)

    # 3. เตรียมโครงสร้างสำหรับนับโควต้า
    total_shipments = len(shipments_to_allocate)
    # Fix quota calculation to ensure it doesn't exceed 100%
    quota_percentages = {'A': 0.40, 'B': 0.30, 'C': 0.20, 'D': 0.10}
    quota = {}
    remaining_shipments = total_shipments
    
    for grade, percentage in quota_percentages.items():
        if grade == 'D':  # Last grade gets remaining shipments
            quota[grade] = remaining_shipments
        else:
            grade_quota = math.floor(total_shipments * percentage)
            quota[grade] = grade_quota
            remaining_shipments -= grade_quota
    
    allocated_counts = defaultdict(int)

    # 4. *** [หัวใจของ Logic ใหม่] *** วนลูปตาม Shipment แต่ละชิ้น
    unassigned_shipments = []

    for shipment in shipments_to_allocate:
        # 4.1 ค้นหา "ผู้สมัคร" (Candidate Vendors) ทั้งหมดสำหรับ Shipment นี้
        candidate_vendors = []
        for v_data in vendor_data_map.values():
            if shipment.cartype in v_data['car_types']:
                candidate_vendors.append(v_data['vendor_obj'])

        if not candidate_vendors:
            print(f"WARNING: No vendor found for shipment {shipment.shipid} with car type {shipment.cartype}. Moving to unassigned.")
            unassigned_shipments.append(shipment)
            continue

        # 4.2 จัดลำดับผู้สมัคร: เกรด (A->D) -> วันที่รับงานล่าสุด (เก่า->ใหม่)
        def sort_key(vendor: models.MVendor):
            grade_order = {'A': 0, 'B': 1, 'C': 2, 'D': 3}
            if vendor.last_assigned_at:
                last_date = vendor.last_assigned_at if vendor.last_assigned_at.tzinfo else vendor.last_assigned_at.replace(tzinfo=timezone.utc)
            else:
                # ถ้าไม่มีค่า ให้สร้าง datetime.min ที่เป็น "Aware" โดยกำหนด Timezone เป็น UTC
                last_date = datetime.min.replace(tzinfo=timezone.utc)
            return (
        grade_order.get(vendor.grade, 99), # 1. เรียงตามเกรด
        last_date,                         # 2. เรียงตามวันที่ (ถ้าไม่เท่ากัน)
        vendor.vencode                     # 3. เรียงตามรหัสผู้ขาย (ถ้าวันที่เท่ากัน)
    )
        candidate_vendors.sort(key=sort_key)

        # 4.3 เลือก Vendor ที่ดีที่สุดที่ "โควต้ายังไม่เต็ม"
        target_vendor = None
        for candidate in candidate_vendors:
            if allocated_counts[candidate.grade] < quota.get(candidate.grade, 0):
                target_vendor = candidate
                break # เจอแล้ว!

        # 4.4 ทำการ Assign งาน
        if target_vendor:
            grade = target_vendor.grade
            
            # --- อัปเดต Shipment ---
            shipment.vencode = target_vendor.vencode
            shipment.docstat = '02'
            shipment.current_grade_to_assign = grade
            shipment.assigned_at = datetime.now(timezone.utc)
            shipment.chuser = "SYSTEM_ALLOCATOR"
            shipment.chdate = datetime.now(timezone.utc)
            
            # --- อัปเดตข้อมูล Vendor ---
            target_vendor.last_assigned_at = datetime.now(timezone.utc)
            allocated_counts[grade] += 1
            
            print(f"INFO: Assigning shipment {shipment.shipid} (req: {shipment.cartype}) to Grade {grade} (Vendor: {target_vendor.vencode})")

            vendor_user = get_user_by_vendor_code(db, target_vendor.vencode)
            if vendor_user and vendor_user.fcm_token:
                try:
                    firebase_service.send_fcm_notification(
                        token=vendor_user.fcm_token,
                        title="มีงานใหม่สำหรับคุณ!",
                        body=f"Shipment ID: {shipment.shipid} รอการยืนยัน",
                        data={
                            "shipment_id": str(shipment.shipid),
                            "round_id": str(round_id),
                            "type": "new_assignment"
                        }
                    )
                except Exception as e:
                    print(f"WARNING: Failed to send notification to vendor {target_vendor.vencode}: {e}")
                    # Continue with allocation even if notification fails
        else:
            # ไม่มี Vendor คนไหนใน List ที่โควต้าว่างเลย
            print(f"WARNING: All suitable vendors have full quota for shipment {shipment.shipid}. Moving to hold.")
            shipment.docstat = 'HD'  # เปลี่ยนสถานะเป็น "Hold"
            shipment.current_grade_to_assign = None
            shipment.assigned_at = datetime.now(timezone.utc)
            shipment.chuser = "SYSTEM_ALLOCATOR"
            shipment.chdate = datetime.now(timezone.utc)
            unassigned_shipments.append(shipment)

    # 6. Commit การเปลี่ยนแปลงทั้งหมด
    try:
        db.commit()
        print(f"SUCCESS: Allocation for round {round_id} completed successfully.")
        print(f"Allocation summary: {dict(allocated_counts)}")
        if unassigned_shipments:
            print(f"WARNING: {len(unassigned_shipments)} shipments moved to hold due to quota limits.")
    except Exception as e:
        db.rollback()
        print(f"CRITICAL: Failed to commit allocation for round {round_id}. Error: {e}")
        raise e
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
def get_rounds_pending_confirmation(db: Session) -> List[models.BookingRound]:
    """
    ดึงข้อมูลรอบทั้งหมดที่มี Shipment อย่างน้อยหนึ่งรายการ
    อยู่ในสถานะรอการยืนยันจาก Dispatcher (docstat = '03')
    """
    return (
        db.query(models.BookingRound)
        .join(models.Shipment) # Join กับ Shipment
        .filter(models.Shipment.docstat == '03') # กรองเฉพาะที่มี Shipment สถานะ '03'
        .options(selectinload(models.BookingRound.shipments)) # โหลด Shipments มาด้วย
        .distinct() # ป้องกันการได้รอบซ้ำ
        .order_by(models.BookingRound.round_date, models.BookingRound.round_time)
        .all()
    )


def confirm_all_shipments_in_round(db: Session, round_id: int, current_user_id: str) -> models.BookingRound:
    """
    ยืนยันการจ่ายงาน Shipments ทั้งหมดในรอบที่ระบุ
    - เปลี่ยน docstat จาก '03' เป็น '04'
    - เรียกใช้ Logic การอัปเดตสถานะรถสำหรับแต่ละ Shipment
    """
    # ใช้ with_for_update() เพื่อ Lock ทั้งรอบและ Shipments ที่เกี่ยวข้อง
    booking_round = db.query(models.BookingRound).filter(models.BookingRound.id == round_id).with_for_update().first()
    if not booking_round:
        raise ValueError(f"Booking round with ID {round_id} not found.")

    shipments_to_confirm = [s for s in booking_round.shipments if s.docstat == '03']
    if not shipments_to_confirm:
        print(f"INFO: No shipments in round {round_id} are pending confirmation.")
        return booking_round # ไม่มีอะไรให้ทำ
    
    updated_cars = []
    for shipment in shipments_to_confirm:
        # --- เรียกใช้ฟังก์ชันที่เรามีอยู่แล้ว ---
        updated_car = assign_job_to_car(db, shipment=shipment)
        if not updated_car:
            # ถ้าการอัปเดตรถล้มเหลว ควรจะ Rollback ทั้งหมด
            raise Exception(f"Failed to update availability for car {shipment.carlicense} on shipment {shipment.shipid}")
        
        updated_cars.append(updated_car)
        
        # อัปเดตสถานะ Shipment
        shipment.docstat = '04' # Dispatcher Assigned
        shipment.chuser = current_user_id
        shipment.chdate = datetime.now(timezone.utc)
    
    # Commit transaction ทีเดียว
    db.commit()
    db.refresh(booking_round)
    
    # ส่ง Notification กลับไปหา Vendor ว่างานถูกยืนยันแล้ว
    for shipment in shipments_to_confirm:
        vendor_user = get_user_by_vencode(db, shipment.vencode)
        if vendor_user and vendor_user.fcm_token:
            try:
                firebase_service.send_fcm_notification(
                    token=vendor_user.fcm_token,
                    title="งานของคุณได้รับการยืนยันแล้ว!",
                    body=f"Shipment ID: {shipment.shipid} ถูกยืนยันโดย Dispatcher",
                    data={
                        "shipment_id": str(shipment.shipid),
                        "round_id": str(round_id),
                        "type": "shipment_confirmed"
                    }
                )
            except Exception as e:
                print(f"WARNING: Failed to send confirmation notification to vendor {shipment.vencode}: {e}")

    return booking_round
def get_ongoing_shipments(db: Session, vencode: Optional[str] = None) -> List[models.Shipment]:
    """
    ดึงรายการ Shipments ที่กำลังดำเนินการอยู่
    - ถ้ามี vencode: ดึงเฉพาะของ Vendor คนนั้น
    - ถ้าไม่มี vencode (None): ดึงของทุก Vendor (สำหรับ Admin/Dispatcher)
    """
    in_progress_statuses = ['03', '04']
    
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

    final_statuses = ['06', 'RJ', '05'] 
    
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

def get_user_by_vendor_code(db: Session, vencode: str) -> Optional[models.SystemUser]:
    """ดึง SystemUser โดยใช้ vencode_ref - alias for get_user_by_vencode for consistency"""
    return get_user_by_vencode(db, vencode)

def get_car_by_license(db: Session, carlicense: str) -> Optional[models.MCar]:
    """ดึงข้อมูลรถด้วยทะเบียน"""
    return db.query(models.MCar).filter(models.MCar.carlicense == carlicense).first()

def is_car_available(db: Session, carlicense: str, required_datetime: datetime) -> bool:
    """
    เช็คว่ารถว่าง ณ เวลาที่ต้องการหรือไม่
    ใช้ข้อมูลจาก MCar.will_be_available_at แทน CarAssignment
    """
    car = db.query(models.MCar).filter(models.MCar.carlicense == carlicense).first()
    if not car:
        return False
    
    # ถ้าสถานะรถไม่ใช่ "ใช้งาน" หรือมีวันที่ว่างในอนาคต
    if (car.stat != models.StandardStatEnum.active or 
        (car.will_be_available_at and car.will_be_available_at > required_datetime.date())):
        return False
    
    return True


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