#!/usr/bin/env python3

from pymongo import MongoClient
from passlib.context import CryptContext
from datetime import datetime, timezone
import secrets

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ======================
# ADMIN ACCOUNT
# ======================
ADMIN_EMAIL = "admin@tabayyun.com"
ADMIN_PASSWORD = "Admin@123456"
ADMIN_NAME = "Abdulaziz Admin"

# ======================
# MONGO CONFIG
# ======================
MONGO_URL = "mongodb://opscore:MongoPass123!@opscore-mongo:27017/?authSource=admin"
DB_NAME = "opscore"

client = MongoClient(MONGO_URL)
db = client[DB_NAME]

email = ADMIN_EMAIL.lower().strip()

existing = db.users.find_one({"email": email})

if existing:
    db.users.update_one(
        {"email": email},
        {
            "$set": {
                "is_admin": True,
                "password_hash": pwd_context.hash(ADMIN_PASSWORD),
                "must_change_password": False,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )
    print("✅ Existing user promoted to admin")
else:
    user_id = secrets.token_hex(16)

    db.users.insert_one(
        {
            "id": user_id,
            "email": email,
            "name": ADMIN_NAME,
            "password_hash": pwd_context.hash(ADMIN_PASSWORD),
            "avatar_url": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "must_change_password": False,
            "is_admin": True,
        }
    )

    print("✅ Admin user created")

print("\nLogin Details:")
print("Email:", ADMIN_EMAIL)
print("Password:", ADMIN_PASSWORD)

client.close()