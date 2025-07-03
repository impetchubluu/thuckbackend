# app/schemas/warehouse_schemas.py
from pydantic import BaseModel

class Warehouse(BaseModel):
    warehouse_code: str
    warehouse_name: str
    # is_active: bool # อาจจะไม่ต้องส่ง is_active กลับไปก็ได้ถ้ากรองมาแล้ว

    class Config:
        from_attributes = True # หรือ orm_mode=True สำหรับ Pydantic V1