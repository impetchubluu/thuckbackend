# app/core/firebase_service.py
import firebase_admin
from firebase_admin import credentials, messaging
import os
from .config import settings # Import settings เพื่อเอา Path

# Global variable to check if app is initialized
_firebase_app = None

def initialize_firebase():
    """
    Initializes the Firebase Admin SDK if not already initialized.
    Uses the service account path from settings.
    """
    global _firebase_app
    if _firebase_app is None:
        try:
            cred = credentials.Certificate(settings.FIREBASE_SERVICE_ACCOUNT_PATH)
            _firebase_app = firebase_admin.initialize_app(cred)
            print("INFO: Firebase Admin SDK Initialized successfully!")
        except Exception as e:
            print(f"ERROR: Failed to initialize Firebase Admin SDK: {e}")


def send_fcm_notification(token: str, title: str, body: str, data: dict = None) -> str:
    """
    ส่ง FCM Notification ไปยังอุปกรณ์ที่ระบุ (Device Token)
    """
    if _firebase_app is None:
        initialize_firebase() # พยายาม Initialize อีกครั้งถ้ายังไม่ได้ทำ
        if _firebase_app is None:
            error_msg = "Firebase Admin SDK not initialized. Cannot send notification."
            print(f"ERROR: {error_msg}")
            return error_msg

    message = messaging.Message(
    notification=messaging.Notification(
        title=title,
        body=body,
    ),
    token=token,
    data=data or {},
    android=messaging.AndroidConfig(
        priority='high', # บอกให้ Android ให้ความสำคัญสูง
        notification=messaging.AndroidNotification(
            channel_id='high_importance_channel' # ระบุ Channel ID ให้ตรงกับใน AndroidManifest
        )
    )
)
    try:
        response = messaging.send(message)
        print(f"Successfully sent message: {response}")
        return response
    except Exception as e:
        print(f"Error sending FCM message: {e}")
        return str(e)