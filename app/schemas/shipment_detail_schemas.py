# app/schemas/shipment_detail_schemas.py
from pydantic import BaseModel
from typing import Optional
from datetime import date

class ShipmentDetail(BaseModel): # หรือจะตั้งชื่อว่า DOHSchema ก็ได้
    doid: str
    shipid: str
    dlvdate: date
    cusid: str
    cusname: str
    route: str
    routedes: Optional[str] = None
    province: str
    volumn: float # Pydantic จะแปลง DECIMAL เป็น float

    class Config:
        from_attributes = True