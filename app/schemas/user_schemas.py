# app/schemas/user_schemas.py
from pydantic import BaseModel, Field
from typing import Optional, List # <<--- Import List
from ..db.models import UserRoleEnum
from .car_schemas import Car as CarSchema # <<--- Import CarSchema

class UserBase(BaseModel):
    username: str
    role: UserRoleEnum
    display_name: Optional[str] = None

class User(UserBase):
    id: int
    is_active: bool
    vencode: Optional[str] = None
    cars: Optional[List[CarSchema]] = None 
    car_count: int = 0
    class Config:
        from_attributes = True
class FCMTokenUpdate(BaseModel):
    fcm_token: str