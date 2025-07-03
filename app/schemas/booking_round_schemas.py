# app/schemas/booking_round_schemas.py
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, datetime, time
from .shipment_schemas import Shipment

class BookingRoundBase(BaseModel):
    round_name: str
    round_date: date
    round_time: time
    warehouse_code: str
    total_volume_cbm: Optional[float] = Field(None, description="ปริมาตรรถบรรทุก เช่น 38 คิว")

class BookingRoundCreate(BookingRoundBase):
    shipment_ids: List[str] # รับ list ของ shipid เพื่อ assign เข้ารอบ

class BookingRound(BookingRoundBase):
    id: int
    status: str
    allocation_start_time: Optional[datetime] = None
    allocation_duration_mins: Optional[int] = None
    shipments: List[Shipment] = []

    class Config:
        from_attributes = True