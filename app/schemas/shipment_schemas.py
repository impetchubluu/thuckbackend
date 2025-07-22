# app/schemas/shipment_schemas.py
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Any, List
from datetime import date, datetime

from app.schemas import shipment_detail_schemas
from app.schemas.car_schemas import CarBase

# ShipmentBase จะเก็บเฉพาะ Fields ที่จำเป็นสำหรับการ "สร้าง" Shipment
class ShipmentCreate(BaseModel):
    shipid: str = Field(..., max_length=10)
    customer_name: Optional[str] = Field(None, max_length=255)
    shippoint: Optional[str] = Field(None, max_length=4)
    province: int
    route: Optional[str] = Field(None, max_length=6)
    cartype: str = Field(..., max_length=2) # รหัสประเภทรถ (cartype)
    dockno: Optional[str] = Field(None, max_length=15)
    quantity: Optional[int] = None
    volume_cbm: Optional[float] = None
    apmdate: datetime
class ShipTypeSchema(BaseModel):
    cartype: str
    cartypedes: str

    class Config:
        from_attributes = True
class MProvince(BaseModel):
    province: int
    provname: str

    class Config:
        from_attributes = True
class MLeadTimeSchema(BaseModel):

    leadtime: float 

    class Config:
        from_attributes = True
# Shipment คือ Schema สำหรับ Response ซึ่งจะมีข้อมูลทั้งหมด
class Shipment(ShipmentCreate): # สืบทอด Fields ทั้งหมดจาก ShipmentCreate
    doctype: Optional[str] = None
    provname: Optional[str] = None
    confirmed_vencode: Optional[str] = Field(None, alias="vencode")
    confirmed_vendor_name: Optional[str] = None
    carlicense: Optional[str] = None
    warehouse_name: Optional[str] = None
    carnote: Optional[str] = None
    docstat: Optional[str] = None
    is_on_hold: bool = False
    booking_round_id: Optional[int] = None
    current_grade_to_assign: Optional[str] = None
    confirmed_by_grade: Optional[str] = None
    cruser: Optional[str] = None
    mshiptype: Optional[ShipTypeSchema] = None
    mprovince: Optional[MProvince] = None
    mleadtime: Optional[MLeadTimeSchema] = None
    details: List[shipment_detail_schemas.ShipmentDetail] = []
    # Fields ที่มีปัญหา
    crdate: Optional[datetime] = None
    chuser: Optional[str] = None
    chdate: Optional[datetime] = None
    sapstat: Optional[str] = None
    sapupdate: Optional[datetime] = None
    assigned_at: Optional[datetime] = None

    @field_validator('crdate', 'chdate', 'sapupdate', 'apmdate', mode='before')
    @classmethod
    def check_zero_date(cls, v: Any) -> Optional[datetime]:
        if v is None:
            return None
        # ตรวจสอบค่าที่เป็น "Zero Date" string จาก MySQL/MariaDB
        if isinstance(v, str) and v.startswith('0000-00-00'):
            return None
        # ตรวจสอบค่าที่เป็น datetime object ที่ไม่ถูกต้อง (ปีน้อยมากๆ)
        if isinstance(v, datetime) and v.year < 1900:
            return None
        return v

    class Config:
        from_attributes = True
        populate_by_name = True

# Schemas สำหรับ Actions ต่างๆ
class ShipmentAction(BaseModel):
    shipid: str

class HoldShipment(ShipmentAction):
    hold: bool

class ConfirmShipment(ShipmentAction):
    carlicense: str = Field(..., max_length=20) # <<--- แก้ไขการสะกดคำที่นี่
    carnote: Optional[str] = Field(None, max_length=255)

class RejectShipment(ShipmentAction):
    rejection_reason: str

class ManualAssign(ShipmentAction):
    vencode: str
