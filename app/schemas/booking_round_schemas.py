# app/schemas/booking_round_schemas.py
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, datetime, time
from .shipment_schemas import Shipment
# Schema สำหรับ Master เวลา (จากตาราง mbooking_round)
class MasterBookingRound(BaseModel):
    round_time: time
    round_name: Optional[str] = None
    class Config: from_attributes = True

# Schema สำหรับแต่ละรอบที่ส่งมาจาก Client เพื่อ Save
class RoundTimeInput(BaseModel):
    round_time_str: str # รับเป็น String เช่น "10:00"

# Schema สำหรับ Request Body หลักตอน Save
class SaveDayRoundsRequest(BaseModel):
    round_date: date
    warehouse_code: str
    rounds: List[RoundTimeInput]
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