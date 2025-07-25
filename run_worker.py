import os
import sys
import logging
from datetime import datetime, timedelta, timezone
from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy.orm import Session

# --- ส่วน Setup Path และ Logging (เหมือนเดิม) ---
# เพิ่ม Path ของโปรเจกต์
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from app.db import crud, models, database
from app.core import firebase_service

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- ค่าคงที่ ---
RESPONSE_TIMEOUT_MINUTES = 30 # เวลาที่ให้ Vendor ตอบรับ (นาที)

#====================================================================
# ฟังก์ชันหลักของ Worker (แก้ไขใหม่)
#====================================================================
def check_expired_shipments_job():
    """
    ฟังก์ชัน Wrapper ที่จัดการการสร้างและปิด Session ของฐานข้อมูล
    เพื่อให้แต่ละ Job ที่รันมี Session ของตัวเอง
    """
    logging.info("Worker Job: Starting check for expired shipments...")
    db: Session = database.SessionLocal() # สร้าง Session ใหม่ทุกครั้งที่ Job ทำงาน
    try:
        # กำหนดเวลาหมดอายุ (30 นาทีที่แล้ว)
        expiration_time_limit = datetime.now(timezone.utc) - timedelta(minutes=RESPONSE_TIMEOUT_MINUTES)
        
        # 1. Query หา Shipments ที่รอการตอบรับจากเกรดที่ระบุ ('02') และหมดเวลาแล้ว
        expired_shipments = db.query(models.Shipment).filter(
            models.Shipment.docstat == '02',
            models.Shipment.assigned_at <= expiration_time_limit
        ).all()
        
        if not expired_shipments:
            logging.info("Worker Job: No expired shipments found.")
            return

        logging.info(f"Worker Job: Found {len(expired_shipments)} expired shipments. Broadcasting them...")
        
        # 2. Loop จัดการแต่ละ Shipment ที่หมดเวลา
        for shipment in expired_shipments:
            logging.info(f"  - Processing expired shipment: {shipment.shipid} from grade {shipment.current_grade_to_assign}")
            grade_that_timed_out = shipment.current_grade_to_assign
            vendor_to_reject = crud.get_vendor_by_grade(db, grade=grade_that_timed_out) # <--- สร้างฟังก์ชันนี้ใน CRUD

            # 2. เตรียม List ของคนที่ถูก Reject
            existing_rejected_list = shipment.rejected_by_vencodes or []
            if vendor_to_reject and vendor_to_reject.vencode_ref not in existing_rejected_list:
                existing_rejected_list.append(vendor_to_reject.vencode_ref)
            # 3. Logic ใหม่: เปลี่ยนสถานะเป็น Broadcast ('BC')
            shipment.rejected_by_vencodes = existing_rejected_list
            shipment.docstat = 'BC'
            shipment.current_grade_to_assign = None # ไม่มีเกรดที่เจาะจงแล้ว
            shipment.assigned_at = None # ล้างเวลา
            shipment.chuser = 'AUTOMATED_WORKER'
            shipment.chdate = datetime.now(timezone.utc)
            shipment.assigned_at = datetime.now(timezone.utc)

            # 4. ส่ง Notification ไปหา Vendor ทุกคน
            # (ยกเว้นเกรด A ที่เพิ่งปล่อยให้หมดเวลา เพื่อไม่ให้เกิดความสับสน)
            vendors_to_notify = crud.get_all_vendors(db) # ใช้ฟังก์ชันจาก crud
            grade_that_timed_out = shipment.current_grade_to_assign # เกรดเดิมก่อนจะเปลี่ยน
            
            for vendor in vendors_to_notify:
                # ไม่ต้องส่งหา Vendor ในเกรดที่เพิ่งหมดเวลาไป
                if vendor.vendor_details and vendor.vendor_details.grade == grade_that_timed_out:
                    continue
                
                if vendor.fcm_token:
                    firebase_service.send_fcm_notification(
                        token=vendor.fcm_token, 
                        title="[งานเปิด] มีงานใหม่ให้เลือก!", 
                        body=f"Shipment ID: {shipment.shipid} เปิดให้รับงาน (หมดเวลาจากเกรดก่อนหน้า)"
                    )
            logging.info(f"    -> Broadcast notification sent for {shipment.shipid}")
        expired_broadcast_shipments = db.query(models.Shipment).filter(
            models.Shipment.docstat == 'BC',
            models.Shipment.assigned_at <= expiration_time_limit
        ).all()
        
        if expired_broadcast_shipments:
            logging.info(f"Worker Job: Found {len(expired_broadcast_shipments)} broadcast shipments to mark as rejected.")
            
            # ดึง Dispatcher ทั้งหมดมาเพื่อส่ง Notification ทีเดียว
            dispatchers_to_notify = crud.get_all_dispatchers(db)

            for shipment in expired_broadcast_shipments:
                logging.info(f"  - Processing expired broadcast shipment: {shipment.shipid}")
                
                # --- Logic ใหม่: เปลี่ยนสถานะเป็น 'RJ' (Rejected All) ---
                shipment.docstat = 'HD'  # เปลี่ยนเป็น Hold ก่อน
                shipment.current_grade_to_assign = None
                shipment.assigned_at = None
                shipment.chuser = 'AUTOMATED_WORKER'
                shipment.chdate = datetime.now(timezone.utc)

                # --- ส่ง Notification แจ้งเตือน Dispatcher ---
                if dispatchers_to_notify:
                    for dispatcher in dispatchers_to_notify:
                        if dispatcher.fcm_token:
                            firebase_service.send_fcm_notification(
                                token=dispatcher.fcm_token,
                                title="⚠️ งานไม่มีผู้รับ (Unclaimed Job)",
                                body=f"Shipment ID: {shipment.shipid} ไม่มี Vendor กดรับภายในเวลาที่กำหนด"
                            )

        # 5. Commit การเปลี่ยนแปลงทั้งหมดลงฐานข้อมูล
        db.commit()
        logging.info(f"Worker Job: Successfully processed and broadcasted {len(expired_shipments)} shipments.")

    except Exception as e:
        logging.error(f"Worker Job: An error occurred: {e}", exc_info=True)
        db.rollback() # Rollback ถ้าเกิดปัญหา
    finally:
        db.close() # ปิด Session เสมอ
        logging.info("Worker Job: Check finished, database session closed.")


if __name__ == "__main__":
    scheduler = BlockingScheduler(timezone="UTC") 

    scheduler.add_job(check_expired_shipments_job, 'interval', minutes=1, id='check_expired_shipments_job')

    logging.info("Scheduler started. Press Ctrl+C to exit.")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        logging.info("Scheduler shut down successfully.")