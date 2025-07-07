# app/routers/shipment_router.py
from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import date, datetime, timezone

from ..schemas import shipment_schemas
from ..db import crud, models
from ..core.security import get_current_active_user
from ..core import firebase_service
from ..db.database import get_db

router = APIRouter(
    tags=["Shipments"],
    dependencies=[Depends(get_current_active_user)] # ป้องกันทุก Route ใน Router นี้ด้วย Authentication
)

# ลำดับการ Assign งานให้เกรดต่างๆ (สามารถย้ายไป Config ได้)
GRADE_ASSIGNMENT_ORDER = ['A', 'B', 'C', 'D']

# --- Helper ---
def get_dispatcher_and_admin_roles():
    return [models.UserRoleEnum.dispatcher, models.UserRoleEnum.admin]

# Pydantic Model สำหรับ Body ของ Hold Action (ใช้เฉพาะในไฟล์นี้)
class HoldActionBody(BaseModel):
    hold: bool

# ===================================================================
# Specific GET Routes (ต้องอยู่ก่อน Dynamic Routes เช่น /{shipid})
# ===================================================================

@router.get("/unassigned", response_model=List[shipment_schemas.Shipment])
async def read_unassigned_shipments(
    apmdate: date = Query(..., description="Appointment date to filter (YYYY-MM-DD)"),
    shippoint: str = Query(..., description="Shippoint/Warehouse code to filter"),
    db: Session = Depends(get_db)
):
    """
    ดึงรายการ Shipments ที่ยังไม่ถูกจัดสรรเข้ารอบ และไม่ได้ถูก Hold
    """
    filters = {"apmdate": apmdate, "shippoint": shippoint}
    return crud.get_unassigned_shipments(db, filters=filters)

@router.get("/held", response_model=List[shipment_schemas.Shipment])
async def read_held_shipments(
    request: Request,
    current_user: models.SystemUser = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    ดึงรายการ Shipments ที่ถูก Hold (สำหรับ Dispatcher)
    """
    if current_user.role not in get_dispatcher_and_admin_roles():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
    
    filters = { "shippoint": request.query_params.get("shippoint") }
    active_filters = {k: v for k, v in filters.items() if v is not None}
    return crud.get_held_shipments(db, filters=active_filters)

# ===================================================================
# General GET and Dynamic GET Routes
# ===================================================================

@router.get("/", response_model=List[shipment_schemas.Shipment])
async def read_shipments(
    request: Request,
    current_user: models.SystemUser = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    ดึงรายการ Shipments
    - Dispatcher: สามารถดู Shipments ทั้งหมดและ Filter ได้
    - Vendor: จะเห็นเฉพาะ Shipments ที่ถูก Assign ให้เกรดของตนเองและรอการ Confirm (docstat = '02')
    """
    if current_user.role in get_dispatcher_and_admin_roles():
        filters = {
            "docstat": request.query_params.get("docstat"),
            "vencode": request.query_params.get("vencode"),
            "apmdate_from": request.query_params.get("apmdate_from"),
            "apmdate_to": request.query_params.get("apmdate_to"),
            "is_on_hold": request.query_params.get("is_on_hold"),
        }
        active_filters = {k: v for k, v in filters.items() if v is not None}
        return crud.get_shipments(db, filters=active_filters)
    elif current_user.role == models.UserRoleEnum.vendor and current_user.vendor_details and current_user.vendor_details.grade:
        return crud.get_shipments_for_vendor(db, grade=current_user.vendor_details.grade)
    else:
        return []

@router.get("/{shipid}", response_model=shipment_schemas.Shipment)
async def read_single_shipment(
    shipid: str,
    db: Session = Depends(get_db)
):
    """
    ดึงข้อมูล Shipment เดียวตาม shipid
    """
    db_shipment = crud.get_shipment_by_id(db, shipid=shipid)
    if not db_shipment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Shipment with ID '{shipid}' not found")
    return db_shipment

# ===================================================================
# POST Routes (Actions)
# ===================================================================

@router.post("/", response_model=shipment_schemas.Shipment, status_code=status.HTTP_201_CREATED)
async def create_new_shipment(
    shipment_in: shipment_schemas.ShipmentCreate,
    current_user: models.SystemUser = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    สร้าง Shipment ใหม่ (สำหรับ Dispatcher/Admin เท่านั้น)
    """
    if current_user.role not in get_dispatcher_and_admin_roles():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions to create a shipment")

    existing_shipment = crud.get_shipment_by_id(db, shipid=shipment_in.shipid)
    if existing_shipment:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Shipment with ID '{shipment_in.shipid}' already exists.")

    return crud.create_shipment(db=db, shipment=shipment_in, creator_user_id=current_user.username)

@router.post("/request-booking", response_model=shipment_schemas.Shipment, summary="Send shipment to the first vendor grade")
async def request_booking(
    action: shipment_schemas.ShipmentAction,
    current_user: models.SystemUser = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    ส่ง Shipment ไปให้ Vendor เกรดแรกพิจารณา (สำหรับ Dispatcher)
    """
    if current_user.role not in get_dispatcher_and_admin_roles():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only dispatchers can request booking")

    db_shipment = crud.get_shipment_by_id(db, shipid=action.shipid)
    if not db_shipment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shipment not found")

    if db_shipment.docstat not in ['01', '06', 'RJ']: # 01=รอจัดเข้ารอบ, 06=ยกเลิก, RJ=ถูกปฏิเสธทั้งหมด
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Shipment with status '{db_shipment.docstat}' cannot be booked.")

    first_grade_in_order = GRADE_ASSIGNMENT_ORDER[0]
    db_shipment.docstat = '02' # 'รอ Vendor ยืนยัน'
    db_shipment.current_grade_to_assign = first_grade_in_order
    db_shipment.chuser = current_user.username
    db_shipment.chdate = datetime.now(timezone.utc)
    db.commit()
    db.refresh(db_shipment)

    # Trigger Notification to Grade A vendors
    vendors_to_notify = crud.get_users_by_grade(db, grade=first_grade_in_order)
    for vendor in vendors_to_notify:
        if vendor.fcm_token:
            firebase_service.send_fcm_notification(
                token=vendor.fcm_token,
                title="มีงานใหม่สำหรับคุณ!",
                body=f"Shipment ID: {db_shipment.shipid} รอการยืนยัน"
            )
    return db_shipment

@router.post("/confirm", response_model=shipment_schemas.Shipment, summary="Vendor confirms a booking")
async def confirm_shipment(
    action: shipment_schemas.ConfirmShipment,
    current_user: models.SystemUser = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    ยืนยันการรับงาน (สำหรับ Vendor เท่านั้น)
    """
    if current_user.role != models.UserRoleEnum.vendor or not current_user.vencode or not current_user.grade:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only vendors can confirm shipments")

    db_shipment = crud.get_shipment_by_id(db, shipid=action.shipid)
    if not db_shipment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shipment not found")
    if db_shipment.docstat != '02' or db_shipment.current_grade_to_assign != current_user.grade:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Shipment is not assigned to your grade or is not in the correct state for confirmation.")

    # ตรวจสอบรถ
    car = crud.get_car_by_license(db, carlicense=action.carlicense)
    if not car:
        raise HTTPException(status_code=404, detail=f"Car with license '{action.carlicense}' not found.")
    if car.vencode != current_user.vencode:
        raise HTTPException(status_code=403, detail=f"Car '{action.carlicense}' does not belong to your company.")
    if not crud.is_car_available(db, carlisence=action.carlicense, required_datetime=db_shipment.apmdate):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Car '{action.carlicense}' is not available for the required date.")

    db_shipment.docstat = '03' # 'Vendor ยืนยันแล้ว'
    db_shipment.vencode = current_user.vencode
    db_shipment.confirmed_by_grade = current_user.grade
    db_shipment.carlicense = action.carlicense
    db_shipment.carnote = action.carnote
    db_shipment.chuser = current_user.username
    db_shipment.chdate = datetime.now(timezone.utc)
    db.add(db_shipment)
    crud.create_car_assignment(db, shipment=db_shipment)
    db.commit()
    db.refresh(db_shipment)

    # Trigger notification to dispatchers
    dispatchers = crud.get_all_dispatchers(db)
    for dispatcher in dispatchers:
        if dispatcher.fcm_token:
            firebase_service.send_fcm_notification(
                token=dispatcher.fcm_token,
                title=f"Vendor ยืนยันงานแล้ว (Grade {current_user.grade})",
                body=f"Shipment '{db_shipment.shipid}' ถูกยืนยันโดย {current_user.display_name}"
            )
    return db_shipment

@router.post("/reject", response_model=shipment_schemas.Shipment, summary="Vendor rejects a booking")
async def reject_shipment(
    action: shipment_schemas.RejectShipment,
    current_user: models.SystemUser = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """ปฏิเสธงาน (สำหรับ Vendor) และส่งต่อไปยังเกรดถัดไป"""
    if current_user.role != models.UserRoleEnum.vendor or not current_user.grade:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only vendors can reject shipments")

    db_shipment = crud.get_shipment_by_id(db, shipid=action.shipid)
    if not db_shipment or db_shipment.docstat != '02' or db_shipment.current_grade_to_assign != current_user.grade:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Shipment cannot be rejected by you at this moment.")

    print(f"INFO: Shipment {action.shipid} rejected by {current_user.username} (Grade {current_user.grade}) with reason: {action.rejection_reason}")
    try:
        current_grade_index = GRADE_ASSIGNMENT_ORDER.index(current_user.grade)
        if current_grade_index + 1 < len(GRADE_ASSIGNMENT_ORDER):
            next_grade = GRADE_ASSIGNMENT_ORDER[current_grade_index + 1]
            db_shipment.current_grade_to_assign = next_grade
            # Notify next grade
            vendors_to_notify = crud.get_users_by_grade(db, grade=next_grade)
            for vendor in vendors_to_notify:
                if vendor.fcm_token:
                    firebase_service.send_fcm_notification(token=vendor.fcm_token, title="มีงานใหม่ (ส่งต่อ)", body=f"Shipment ID: {db_shipment.shipid} รอการยืนยัน")
        else:
            db_shipment.docstat = 'RJ' # All Rejected
            db_shipment.current_grade_to_assign = None
            # Notify dispatchers
            dispatchers = crud.get_all_dispatchers(db)
            for d in dispatchers:
                if d.fcm_token:
                    firebase_service.send_fcm_notification(token=d.fcm_token, title="[ACTION NEEDED] Shipment ถูกปฏิเสธทั้งหมด", body=f"Shipment '{db_shipment.shipid}' ไม่มี Vendor รับงาน")
    except ValueError:
        db_shipment.docstat = 'RJ'
        db_shipment.current_grade_to_assign = None
    
    db_shipment.chuser = current_user.username
    db_shipment.chdate = datetime.now(timezone.utc)
    db.commit()
    db.refresh(db_shipment)
    return db_shipment

@router.post("/{shipid}/hold", response_model=shipment_schemas.Shipment, summary="Hold or Unhold a shipment")
async def hold_unhold_shipment(
    shipid: str,
    action: HoldActionBody,
    current_user: models.SystemUser = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """พัก หรือ ยกเลิกการพัก Shipment โดยระบุ shipid ใน Path (Dispatcher)"""
    if current_user.role not in get_dispatcher_and_admin_roles():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")

    db_shipment = crud.get_shipment_by_id(db, shipid=shipid)
    if not db_shipment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shipment not found")

    if action.hold:
        if db_shipment.is_on_hold:
            raise HTTPException(status_code=400, detail="Shipment is already on hold")
        db_shipment.docstat_before_hold = db_shipment.docstat
        db_shipment.is_on_hold = True
        db_shipment.docstat = 'HD'
    else:
        if not db_shipment.is_on_hold:
            raise HTTPException(status_code=400, detail="Shipment is not on hold")
        db_shipment.docstat = db_shipment.docstat_before_hold if db_shipment.docstat_before_hold else '01'
        db_shipment.is_on_hold = False
        db_shipment.docstat_before_hold = None

    db_shipment.chuser = current_user.username
    db_shipment.chdate = datetime.now(timezone.utc)
    db.commit()
    db.refresh(db_shipment)
    return db_shipment

@router.post("/manual-assign", response_model=shipment_schemas.Shipment, summary="Dispatcher manually assigns a vendor")
async def manual_assign_vendor(
    action: shipment_schemas.ManualAssign,
    current_user: models.SystemUser = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """จัดเลือกขนส่งเอง (สำหรับ Dispatcher) ให้กับงานที่ Unresponsive หรือถูกปฏิเสธทั้งหมด"""
    if current_user.role not in get_dispatcher_and_admin_roles():
        raise HTTPException(status_code=403, detail="Not enough permissions")

    db_shipment = crud.get_shipment_by_id(db, shipid=action.shipid)
    if not db_shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")
    if db_shipment.docstat not in ['RJ', '01']:
        raise HTTPException(status_code=400, detail="Shipment is not in a state for manual assignment")

    vendor_to_assign = crud.get_user_by_vencode(db, vencode=action.vencode)
    if not vendor_to_assign or not vendor_to_assign.vendor_details:
        raise HTTPException(status_code=404, detail=f"Vendor with code '{action.vencode}' not found")
    db_shipment.vencode = action.vencode
    db_shipment.vendor_name = vendor_to_assign.display_name
    db_shipment.docstat = '02'
    db_shipment.current_grade_to_assign = vendor_to_assign.vendor_details.grade
    db_shipment.chuser = current_user.username
    db_shipment.chdate = datetime.now(timezone.utc)
    db.commit()
    db.refresh(db_shipment)

    if vendor_to_assign.fcm_token:
        firebase_service.send_fcm_notification(
            token=vendor_to_assign.fcm_token,
            title="คุณได้รับมอบหมายงาน",
            body=f"Shipment ID: {db_shipment.shipid} รอการยืนยันจากคุณ"
        )
    return db_shipment