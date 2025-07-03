# generate_test_hashes.py

from passlib.context import CryptContext 

# สร้าง Context สำหรับ bcrypt (ควรทำนอก Loop)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

users_to_create = [
    {"email": "admin", "password": "admin123", "role": "admin", "display_name": "Administrator"},
    {"email": "MIZUHO", "password": "user123", "role": "vendor", "vencode": "500000860", "display_name": "MIZUHO VENDOR"},
    {"email": "jpplogis", "password": "user1234", "role": "vendor", "vencode": "500000088", "display_name": "บจก.เจ.พี.พี โลจิสติกส์ อินเตอร์ กร VENDOR"}
    # เพิ่ม User อื่นๆ ที่นี่ถ้าต้องการ
]

print("--- Hashed Passwords for Test Users ---")
for user_data in users_to_create:
    hashed_password = pwd_context.hash(user_data["password"])
    print(f"\nEmail: {user_data['email']}")
    print(f"Plain Password (for reference only, DO NOT STORE): {user_data['password']}")
    print(f"Hashed Password (to insert into DB): {hashed_password}")
    print(f"Role: {user_data['role']}")
    if user_data["role"] == "vendor":
        
        print(f"Vencode: {user_data['vencode']}")
    print(f"Display Name: {user_data['display_name']}")
print("--------------------------------------")