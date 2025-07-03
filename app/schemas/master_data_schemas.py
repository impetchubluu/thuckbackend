# app/schemas/master_data_schemas.py
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