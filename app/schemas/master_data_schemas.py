# app/schemas/master_data_schemas.py
from datetime import time
from pydantic import BaseModel
from typing import Optional

class Province(BaseModel):
    province: int
    provname: Optional[str] = None
    class Config: from_attributes = True

class ShipType(BaseModel):
    cartype: str
    cartypedes: Optional[str] = None
    class Config: from_attributes = True

class Vendor(BaseModel):
    vencode: str
    venname: Optional[str] = None
    grade: Optional[str] = None
    class Config: from_attributes = True

class ControlCode(BaseModel):
    contkey: Optional[str] = None
    contcode: str
    contdese: Optional[str] = None
    class Config: from_attributes = True
class MasterBookingRound(BaseModel):
    round_time: time
    round_name: Optional[str] = None

    class Config:
        from_attributes = True