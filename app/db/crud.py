# app/db/crud.py
from sqlalchemy.orm import Session, joinedload, selectinload
from . import models
from ..schemas import shipment_schemas, booking_round_schemas
from typing import List, Optional
from datetime import date, datetime, timedelta
from sqlalchemy import func

# --- User CRUD ---
def get_user_by_username(db: Session, username: str) -> Optional[models.SystemUser]:
    return db.query(models.SystemUser).options(joinedload(models.SystemUser.vendor_details)).filter(models.SystemUser.username == username).first()
def get_shipment_by_id(db: Session, shipid: str) -> Optional[models.Shipment]:
    return db.query(models.Shipment).filter(models.Shipment.shipid == shipid).first()
# --- Master Data CRUD ---
def get_warehouses(db: Session) -> List[models.MWarehouse]:
    return db.query(models.MWarehouse).filter(models.MWarehouse.is_active == True).all()

# --- Booking Round CRUD ---
def get_booking_rounds_by_date(db: Session, round_date: date, warehouse_code: str) -> List[models.BookingRound]:
    return (db.query(models.BookingRound)
              .options(selectinload(models.BookingRound.shipments))
              .filter(models.BookingRound.round_date == round_date, models.BookingRound.warehouse_code == warehouse_code)
              .order_by(models.BookingRound.round_time)
              .all())

def create_booking_round(db: Session, round_in: booking_round_schemas.BookingRoundCreate, creator_id: str) -> models.BookingRound:
    db_round = models.BookingRound(
        round_name=round_in.round_name,
        round_date=round_in.round_date,
        round_time=round_in.round_time,
        warehouse_code=round_in.warehouse_code,
        total_volume_cbm=round_in.total_volume_cbm,
        created_by=creator_id,
        status='pending'
    )
    db.add(db_round)
    db.flush()

    if round_in.shipment_ids:
        (db.query(models.Shipment)
           .filter(models.Shipment.shipid.in_(round_in.shipment_ids), models.Shipment.booking_round_id == None)
           .update({"booking_round_id": db_round.id, "docstat": '01'}, synchronize_session=False))

    db.commit()
    db.refresh(db_round)
    return db_round

# --- Shipment CRUD ---
def get_unassigned_shipments(db: Session, filters: dict) -> List[models.Shipment]:
    query = db.query(models.Shipment).filter(models.Shipment.booking_round_id == None, models.Shipment.is_on_hold == False)
    if filters.get("shippoint"):
        query = query.filter(models.Shipment.shippoint == filters["shippoint"])
    if filters.get("apmdate"):
        query = query.filter(func.date(models.Shipment.apmdate) == filters["apmdate"])
    return query.order_by(models.Shipment.shipid).all()

def get_held_shipments(db: Session, filters: dict) -> List[models.Shipment]:
    query = db.query(models.Shipment).filter(models.Shipment.is_on_hold == True)
    # ... add filters ...
    return query.all()

# ... (CRUD อื่นๆ สำหรับ Shipment ที่จำเป็น) ...