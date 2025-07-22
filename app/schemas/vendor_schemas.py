# app/schemas/vendor_schemas.py
from pydantic import BaseModel
from typing import List, Optional

# Schema สำหรับรถ (อาจจะใช้ซ้ำกับที่มีอยู่แล้ว)
class CarProfile(BaseModel):
    carlicense: str
    cartypedes: Optional[str] = None
    stat: str

    class Config:
        from_attributes = True

# Schema หลักสำหรับโปรไฟล์ Vendor
class VendorProfileWithCars(BaseModel):
    vencode: str
    venname: str
    grade: str
    cars: List[CarProfile] = []

    class Config:
        from_attributes = True