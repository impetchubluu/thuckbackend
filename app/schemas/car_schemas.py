# app/schemas/car_schemas.py
from datetime import date
from pydantic import BaseModel
from typing import Optional

class CarBase(BaseModel):
    carlicense: str
    vencode: Optional[str] = None # อาจจะไม่ต้องแสดงถ้ามันซ้ำกับ vencode ของ vendor
    venname: Optional[str] = None
    conid: Optional[str] = None
    cartype: Optional[str] = None
    cartypedes: Optional[str] = None
    remark: Optional[str] = None
    stat: str # "ใช้งาน" หรือ "ไม่ใช้งาน"
    will_be_available_at: Optional[date] = None

class Car(CarBase):
    class Config:
        from_attributes = True # Pydantic V2