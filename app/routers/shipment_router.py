from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import date, datetime, timezone

from ..schemas import shipment_schemas
from ..db import crud, models
from ..core.security import get_current_active_user
from ..db.database import get_db

router = APIRouter(
    tags=["Shipments"],
    dependencies=[Depends(get_current_active_user)] # ป้องกันทุก Route ใน Router นี้ด้วย Authentication
)

# ลำดับการ Assign งานให้เกรดต่างๆ (สามารถย้ายไป Config ได้)
GRADE_ASSIGNMENT_ORDER = ['A', 'B', 'C', 'D']

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
    if current_user.role not in [models.UserRoleEnum.dispatcher, models.UserRoleEnum.admin]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
    
    # สามารถเพิ่ม filter อื่นๆ ได้ตามต้องการ
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
    if current_user.role in [models.UserRoleEnum.dispatcher, models.UserRoleEnum.admin]:
        filters = {
            "docstat": request.query_params.get("docstat"),
            "vencode": request.query_params.get("vencode"),
            "apmdate_from": request.query_params.get("apmdate_from"),
            "apmdate_to": request.query_params.get("apmdate_to"),
            "is_on_hold": request.query_params.get("is_on_hold"),
        }
        active_filters = {k: v for k, v in filters.items() if v is not None}
        return crud.get_shipments(db, filters=active_filters)
    elif current_user.role == models.UserRoleEnum.vendor and current_user.grade:
        return crud.get_shipments_for_vendor(db, grade=current_user.grade)
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
    if current_user.role not in [models.UserRoleEnum.dispatcher, models.UserRoleEnum.admin]:
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
    if current_user.role not in [models.UserRoleEnum.dispatcher, models.UserRoleEnum.admin]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only dispatchers can request booking")

    db_shipment = crud.get_shipment_by_id(db, shipid=action.shipid)
    if not db_shipment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shipment not found")


    if db_shipment.is_on_hold:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot book a shipment that is currently on hold.")
    if db_shipment.docstat not in ['01', '06', 'RJ']:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Shipment with status '{db_shipment.docstat}' cannot be booked.")

    first_grade_in_order = GRADE_ASSIGNMENT_ORDER[0]
    db_shipment.docstat = '02' # 'รอ Vendor ยืนยัน'
    db_shipment.current_grade_to_assign = first_grade_in_order
    db_shipment.chuser = current_user.username
    db_shipment.chdate = datetime.now(timezone.utc)
    db_shipment.vencode = None
    db_shipment.carlisence = None
    db_shipment.carnote = None
    db_shipment.confirmed_by_grade = None

    db.commit()
    db.refresh(db_shipment)
    # TODO: Trigger notification to Grade A vendors
    return db_shipment

@router.post("/confirm", response_model=shipment_schemas.Shipment, summary="Vendor confirms a shipment booking")
async def confirm_shipment(
    action: shipment_schemas.ConfirmShipment,
    current_user: models.SystemUser = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    # ... (โค้ดเหมือนเดิม) ...
    db_shipment = crud.get_shipment_by_id(db, shipid=action.shipid) # ... (validation logic)
    # ...
    db.commit()
    db.refresh(db_shipment)
    return db_shipment

@router.post("/reject", response_model=shipment_schemas.Shipment, summary="Vendor rejects a shipment booking")
async def reject_shipment(
    action: shipment_schemas.RejectShipment,
    current_user: models.SystemUser = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    # ... (โค้ดเหมือนเดิม) ...
    db_shipment = crud.get_shipment_by_id(db, shipid=action.shipid) # ... (validation & grade logic)
    # ...
    db.commit()
    db.refresh(db_shipment)
    return db_shipment

@router.post("/finalize", response_model=shipment_schemas.Shipment, summary="Dispatcher finalizes a confirmed booking")
async def finalize_booking(
    action: shipment_schemas.ShipmentAction,
    current_user: models.SystemUser = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    # ... (โค้ดเหมือนเดิม) ...
    db_shipment = crud.get_shipment_by_id(db, shipid=action.shipid) # ... (validation logic)
    # ...
    db.commit()
    db.refresh(db_shipment)
    return db_shipment

@router.post("/cancel", response_model=shipment_schemas.Shipment, summary="Dispatcher cancels a confirmed booking")
async def cancel_booking(
    action: shipment_schemas.ShipmentAction,
    current_user: models.SystemUser = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    # ... (โค้ดเหมือนเดิม พร้อมการแก้ไข bug) ...
    if current_user.role not in [models.UserRoleEnum.dispatcher, models.UserRoleEnum.admin]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only dispatchers can cancel bookings")

    db_shipment = crud.get_shipment_by_id(db, shipid=action.shipid)
    if not db_shipment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shipment not found")

    # Business logic: Cannot cancel a shipment past its appointment date
    if db_shipment.apmdate and datetime.now(timezone.utc) > db_shipment.apmdate.replace(tzinfo=timezone.utc):
        raise HTTPException(status_code=400, detail="Cannot cancel a shipment past its appointment date")

    if db_shipment.docstat not in ['03', '04']: # ยกเลิกได้เฉพาะที่ Vendor/Dispatcher ยืนยันแล้ว
        raise HTTPException(status_code=400, detail=f"Cannot cancel a shipment in its current state ('{db_shipment.docstat}')")

    # TODO: ต้องมีการยกเลิก car assignment ที่เกี่ยวข้องด้วย
    # crud.complete_or_cancel_car_assignment(db, shipid=action.shipid, new_status='CANCELED')

    db_shipment.docstat = '06' # 'ยกเลิก'
    # Clear vendor assignment details
    db_shipment.vencode = None
    db_shipment.carlisence = None
    db_shipment.carnote = None
    db_shipment.confirmed_by_grade = None
    db_shipment.current_grade_to_assign = None
    db_shipment.chuser = current_user.username
    db_shipment.chdate = datetime.now(timezone.utc)
    db.commit()
    db.refresh(db_shipment)
    # TODO: Trigger notification to the vendor who had confirmed it
    return db_shipment

@router.post("/hold", response_model=shipment_schemas.Shipment, summary="Dispatcher holds or unholds a shipment")
async def hold_unhold_shipment(
    action: shipment_schemas.HoldShipment, # รับ shipid และสถานะ hold จาก Body
    current_user: models.SystemUser = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    พัก หรือ ยกเลิกการพัก Shipment (สำหรับ Dispatcher)
    """
    if current_user.role not in [models.UserRoleEnum.dispatcher, models.UserRoleEnum.admin]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only dispatchers can hold/unhold shipments")

    db_shipment = crud.get_shipment_by_id(db, shipid=action.shipid)
    if not db_shipment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shipment not found")

    if action.hold: # ถ้าต้องการ Hold
        if db_shipment.is_on_hold:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Shipment is already on hold")
        db_shipment.docstat_before_hold = db_shipment.docstat
        db_shipment.is_on_hold = True
        # คุณอาจจะต้องการเปลี่ยน docstat เป็น 'HD' ด้วย เพื่อให้ Filter ง่ายขึ้น
        # db_shipment.docstat = 'HD'
    else: # ถ้าต้องการ Unhold
        if not db_shipment.is_on_hold:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Shipment is not on hold")
        # กลับไปใช้สถานะเดิมก่อน Hold (ถ้ามี) หรือสถานะเริ่มต้น
        db_shipment.docstat = db_shipment.docstat_before_hold if db_shipment.docstat_before_hold else '01'
        db_shipment.is_on_hold = False
        db_shipment.docstat_before_hold = None

    db_shipment.chuser = current_user.username
    db_shipment.chdate = datetime.now(timezone.utc)
    db.commit()
    db.refresh(db_shipment)
    return db_shipment
class HoldActionBody(BaseModel):
    hold: bool
@router.post("/{shipid}/hold", response_model=shipment_schemas.Shipment, summary="Dispatcher holds or unholds a shipment")
async def hold_unhold_shipment_by_path(
    shipid: str,
    action: HoldActionBody,
    current_user: models.SystemUser = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    พัก หรือ ยกเลิกการพัก Shipment โดยระบุ shipid ใน Path
    """
    if current_user.role not in [models.UserRoleEnum.dispatcher, models.UserRoleEnum.admin]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only dispatchers can hold/unhold shipments")

    db_shipment = crud.get_shipment_by_id(db, shipid=shipid)
    if not db_shipment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shipment not found")

    if action.hold:
        if db_shipment.is_on_hold:
            raise HTTPException(status_code=400, detail="Shipment is already on hold")
        db_shipment.docstat_before_hold = db_shipment.docstat
        db_shipment.is_on_hold = True
        db_shipment.docstat = 'HD' # สมมติ 'HD' คือ Hold
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