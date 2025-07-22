# app/db/models.py

from datetime import date, datetime
from typing import List
from sqlalchemy import (
    JSON, Boolean, Column, ForeignKey, Integer, String, DateTime, Date, Time,
    Enum as SAEnum, func, DECIMAL
)
from sqlalchemy.orm import relationship, Mapped, mapped_column # Use Mapped for modern type-annotated style
from .database import Base
import enum

# --- Python Enums for roles and statuses ---
class UserRoleEnum(str, enum.Enum):
    dispatcher = "dispatcher"
    vendor = "vendor"
    admin = "admin"

class StandardStatEnum(str, enum.Enum):
    active = "ใช้งาน"
    inactive = "ไม่ใช้งาน"

# --- Master Data Models ---

class MWarehouse(Base):
    __tablename__ = "mwarehouse"
    warehouse_code: Mapped[str] = mapped_column(String(4), primary_key=True) # **PK ต้องตรงกับ shipment.shippoint**
    warehouse_name: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

class MBookingRound(Base):
    __tablename__ = "mbooking_round"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    round_time: Mapped[Time] = mapped_column(Time, nullable=False, unique=True)
    round_name: Mapped[str] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

class MProvince(Base):
    __tablename__ = "mprovince"
    province: Mapped[int] = mapped_column(Integer, primary_key=True)
    provname: Mapped[str] = mapped_column(String(100))
    stat: Mapped[StandardStatEnum] = mapped_column(SAEnum("ใช้งาน", "ไม่ใช้งาน", name="mprovince_stat_enum"))
class MShipType(Base):
    __tablename__ = "mshiptype"
    cartype: Mapped[str] = mapped_column(String(2), primary_key=True)
    cartypedes: Mapped[str] = mapped_column(String(255))
    stat: Mapped[StandardStatEnum] = mapped_column(SAEnum("ใช้งาน", "ไม่ใช้งาน", "", name="mshiptype_stat_enum"))

# --- Core Operational Models ---

class MCar(Base):
    __tablename__ = "mcar"
    carlicense: Mapped[str] = mapped_column(String(20), primary_key=True, index=True)
    vencode: Mapped[str] = mapped_column(String(10), ForeignKey("mvendor.vencode", name="fk_mcar_vencode_mvendor"))
    venname: Mapped[str] = mapped_column(String(255))
    conid: Mapped[str] = mapped_column(String(3))
    cartype: Mapped[str] = mapped_column(String(2))
    cartypedes: Mapped[str] = mapped_column(String(255))
    remark: Mapped[str] = mapped_column(String(255), nullable=True)
    stat: Mapped[StandardStatEnum] = mapped_column(SAEnum("ใช้งาน", "ไม่ใช้งาน", name="mcar_stat_enum"), default="ใช้งาน")
    will_be_available_at: Mapped[date] = mapped_column(Date, nullable=True)
    # Relationship back to MVendor
    owner_vendor: Mapped["MVendor"] = relationship(back_populates="cars")

class MVendor(Base):
    __tablename__ = "mvendor"
    vencode: Mapped[str] = mapped_column(String(10), primary_key=True, index=True)
    venname: Mapped[str] = mapped_column(String(255))
    grade: Mapped[str] = mapped_column(String(1))
    Score: Mapped[float] = mapped_column(DECIMAL(10, 2), nullable=True)
    perallocate: Mapped[float] = mapped_column(DECIMAL(10, 2), nullable=True)
    stat: Mapped[StandardStatEnum] = mapped_column(SAEnum("ใช้งาน", "ไม่ใช้งาน", name="mvendor_stat_enum"), default="ใช้งาน")

    # Relationship to its Cars (One-to-Many)
    cars: Mapped[list["MCar"]] = relationship(back_populates="owner_vendor", cascade="all, delete-orphan", lazy="selectin")

    # Relationship to its SystemUser account (One-to-One)
    user_account: Mapped["SystemUser"] = relationship(back_populates="vendor_details", uselist=False)

class SystemUser(Base):
    __tablename__ = "system_users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRoleEnum] = mapped_column(SAEnum(UserRoleEnum), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    vencode_ref: Mapped[str] = mapped_column(String(10), ForeignKey("mvendor.vencode", name="fk_sysusers_vencode_mvendor"), nullable=True)
    fcm_token: Mapped[str] = mapped_column(String(255), nullable=True)  # เพิ่มฟิลด์นี้สำหรับเก็บ FCM token
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    # Relationship to MVendor (Many-to-One, but conceptually One-to-One from this side)
    vendor_details: Mapped["MVendor"] = relationship(
        back_populates="user_account",
        foreign_keys=[vencode_ref], # Explicitly define which local column is the foreign key
        lazy="joined" # Use joined loading to get vendor details with user
    )
class DOH(Base):
    __tablename__ = "doh" # ชื่อตารางใน Database ของคุณ

    doid: Mapped[str] = mapped_column(String(10), primary_key=True, index=True)
    shipid: Mapped[str] = mapped_column(String(10), ForeignKey("shipment.shipid", name="fk_doh_shipid_shipment"), index=True)
    dlvdate: Mapped[date] = mapped_column(Date)
    cusid: Mapped[str] = mapped_column(String(10))
    cusname: Mapped[str] = mapped_column(String(100))
    route: Mapped[str] = mapped_column(String(6))
    routedes: Mapped[str] = mapped_column(String(100), nullable=True)
    province: Mapped[str] = mapped_column(String(2)) # เป็น varchar(2) ตามรูป
    volumn: Mapped[float] = mapped_column(DECIMAL(13, 3)) # เป็น DECIMAL(13,3) ตามรูป

    # Relationship กลับไปยัง Shipment
    shipment: Mapped["Shipment"] = relationship(back_populates="details")

class BookingRound(Base):
    __tablename__ = "booking_round"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    round_name: Mapped[str] = mapped_column(String(100), nullable=False)
    round_date: Mapped[date] = mapped_column(Date, nullable=False)
    round_time: Mapped[Time] = mapped_column(Time, nullable=False)
    warehouse_code: Mapped[str] = mapped_column(String(10), ForeignKey("mwarehouse.warehouse_code"))
    total_volume_cbm: Mapped[float] = mapped_column(DECIMAL(10, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default='pending')
    allocation_start_time: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    allocation_duration_mins: Mapped[int] = mapped_column(Integer, nullable=True)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationship to Shipments in this round
    shipments: Mapped[list["Shipment"]] = relationship(back_populates="booking_round", lazy="selectin")
class MLeadTime(Base):
    __tablename__ = "mleadtime"
    route: Mapped[str] = mapped_column(String(6), primary_key=True)
    provth: Mapped[str] = mapped_column(String(100))
    routedes: Mapped[str] = mapped_column(String(255))
    proven: Mapped[str] = mapped_column(String(100))
    zone: Mapped[str] = mapped_column(String(10))
    zonedes: Mapped[str] = mapped_column(String(100))
    leadtime: Mapped[float] = mapped_column(DECIMAL(10, 2), nullable=False)
    class Config:
        from_attributes = True

class DocStatEnum(str, enum.Enum):
    WAITING_ROUND = '01'      # รอจัดเข้ารอบ
    WAITING_VENDOR = '02'     # รอ Vendor เกรดที่ระบุยืนยัน
    VENDOR_CONFIRMED = '03'   # Vendor ยืนยันแล้ว
    DISPATCHER_ASSIGNED = '04'# Dispatcher จ่ายงานแล้ว
    CANCELED = '06'           # ยกเลิกโดย Dispatcher
    BROADCAST = 'BC'          # งานเปิดให้ทุกเกรด
    REJECTED_ALL = 'RJ'       # ถูกปฏิเสธทั้งหมด
    ON_HOLD = 'HD'            # พักงาน
class Shipment(Base):
    __tablename__ = "shipment"
    shipid: Mapped[str] = mapped_column(String(10), primary_key=True, index=True)
    customer_name: Mapped[str] = mapped_column(String(255), nullable=True)
    doctype: Mapped[str] = mapped_column(String(4), nullable=True)
    shippoint: Mapped[str] = mapped_column(String(4), ForeignKey("mwarehouse.warehouse_code"))
    province: Mapped[int] = mapped_column(Integer, ForeignKey("mprovince.province"), nullable=True)
    route: Mapped[str] = mapped_column(String(6), ForeignKey("mleadtime.route"), nullable=True)
    cartype: Mapped[str] = mapped_column(String(2), ForeignKey("mshiptype.cartype"), nullable=True)
    vencode: Mapped[str] = mapped_column(String(10), ForeignKey("mvendor.vencode"), nullable=True)
    carlicense: Mapped[str] = mapped_column(String(20), ForeignKey("mcar.carlicense"), nullable=True)
    carnote: Mapped[str] = mapped_column(String(255), nullable=True)
    dockno: Mapped[str] = mapped_column(String(15), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=True)
    volume_cbm: Mapped[float] = mapped_column(DECIMAL(10, 4), nullable=True)
    apmdate: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    cruser: Mapped[str] = mapped_column(String(20), nullable=True)
    crdate: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    chuser: Mapped[str] = mapped_column(String(20), nullable=True)
    chdate: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    sapstat: Mapped[str] = mapped_column(String(1), nullable=True)
    sapupdate: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    docstat: Mapped[DocStatEnum] = mapped_column(String(2), nullable=True)
    booking_round_id: Mapped[int] = mapped_column(Integer, ForeignKey("booking_round.id"), nullable=True)
    is_on_hold: Mapped[bool] = mapped_column(Boolean, default=False)
    docstat_before_hold: Mapped[str] = mapped_column(String(2), nullable=True)
    current_grade_to_assign: Mapped[str] = mapped_column(String(1), nullable=True)
    confirmed_by_grade: Mapped[str] = mapped_column(String(1), nullable=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    rejected_by_vencodes: Mapped[list] = mapped_column(JSON, nullable=True)

    # Relationships to get descriptive data
    warehouse: Mapped["MWarehouse"] = relationship(
    "MWarehouse", # ระบุชื่อคลาสเป้าหมาย
    primaryjoin="Shipment.shippoint == MWarehouse.warehouse_code", # ระบุเงื่อนไขการ JOIN อย่างชัดเจน
    lazy="joined"
)
    mleadtime : Mapped["MLeadTime"] = relationship(
        "MLeadTime",
        primaryjoin="Shipment.route == MLeadTime.route",
        lazy="joined"
    )
    mprovince: Mapped["MProvince"] = relationship(lazy="joined")
    mshiptype: Mapped["MShipType"] = relationship(lazy="joined")
    mvendor: Mapped["MVendor"] = relationship()
    mcar: Mapped["MCar"] = relationship()
    booking_round: Mapped["BookingRound"] = relationship(back_populates="shipments")
    details: Mapped[List["DOH"]] = relationship(
        back_populates="shipment",
        cascade="all, delete-orphan",
        lazy="selectin" 
    )
