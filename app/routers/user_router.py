# app/routers/user_router.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List # Import List for type hinting

from ..schemas.user_schemas import User as UserResponseSchema
from ..schemas.car_schemas import Car as CarSchema # Import CarSchema
from ..db import models, crud
from ..core import security
from ..db.database import get_db

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
        "cars": []    
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
