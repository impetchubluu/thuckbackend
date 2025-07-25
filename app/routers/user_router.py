# app/routers/user_router.py
from fastapi import APIRouter, Depends, HTTPException
from grpc import Status
from sqlalchemy.orm import Session
from typing import List

from app.routers.shipment_router import get_dispatcher_and_admin_roles # Import List for type hinting

from ..schemas.user_schemas import User as UserResponseSchema
from ..schemas.car_schemas import Car as CarSchema # Import CarSchema
from ..db import models, crud
from ..core import security
from ..db.database import get_db
from app.schemas import user_schemas, vendor_schemas

router = APIRouter(
    tags=["Users (Authenticated)"] # เปลี่ยน Tag
)
@router.get("/me", response_model=UserResponseSchema)
async def read_users_me(
    current_user: models.SystemUser = Depends(security.get_current_active_user),
    db_session: Session = Depends(get_db) # db_session จะถูกใช้
):
    # แปลง SQLAlchemy model (current_user) เป็น Pydantic model (UserResponseSchema)
    # model_validate จะ map attributes ที่ชื่อตรงกันโดยอัตโนมัติ
    user_response_data = {
        "id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
        "display_name": current_user.display_name,
        "is_active": current_user.is_active,
        "vencode": None, 
        "car_count": 0,  
        "cars": [],
    }

    if current_user.role == models.UserRoleEnum.vendor and current_user.vencode_ref:
        vendor_with_cars = db_session.query(models.MVendor).filter(models.MVendor.vencode == current_user.vencode_ref).first()

        if vendor_with_cars:
            user_response_data["vencode"] = vendor_with_cars.vencode

            # ดึงข้อมูลรถทั้งหมดของ Vendor นี้
            all_cars_data = []
            for car_model in vendor_with_cars.cars:
                # ไม่กรองสถานะ ทำให้ดึงข้อมูลรถทั้งหมด
                all_cars_data.append(CarSchema.model_validate(car_model))
            
            user_response_data["cars"] = all_cars_data
            user_response_data["car_count"] = len(all_cars_data)
        else:
            print(f"Warning: Vendor details not found in mvendor for vencode_ref: {current_user.vencode_ref}")

    return UserResponseSchema(**user_response_data)
@router.get("/vendors/all", response_model=List[vendor_schemas.VendorProfileWithCars], summary="Get all vendor profiles")
async def get_all_vendors(
    current_user: models.SystemUser = Depends(security.get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    สำหรับ Admin/Dispatcher: ดึงข้อมูลโปรไฟล์ของ Vendor ทั้งหมด
    """
    if current_user.role not in get_dispatcher_and_admin_roles(): # ใช้ helper function เดิม
        raise HTTPException(status_code=403, detail="Not enough permissions")
        
    return crud.get_all_vendor_profiles(db)
@router.post("/update-fcm-token", response_model=user_schemas.User)
async def update_fcm_token(
    token_data: user_schemas.FCMTokenUpdate,
    current_user: models.SystemUser = Depends(security.get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    รับ FCM Token จาก Client และบันทึกลงใน Database ของ User ที่ Login อยู่
    """
    print(f"Updating FCM token for user {current_user.username} to {token_data.fcm_token}")
    return crud.update_user_fcm_token(db=db, user=current_user, new_token=token_data.fcm_token)