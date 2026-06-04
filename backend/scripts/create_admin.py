#!/usr/bin/env python3
"""Create (or reset) an admin user directly in MongoDB.

Idempotent: keyed by email. If the user already exists it is promoted to admin
and (optionally) its password is reset. A user document with ``is_admin: True``
is a full superuser across RBAC and the entire UI.

Usage (inside the backend container, where MONGO_URL/DB_NAME are already set):

    docker compose exec backend python -m scripts.create_admin \
        --email you@example.com --name "Admin" --password 'StrongPass#1'

Or locally with env vars set:

    MONGO_URL=mongodb://user:pass@localhost:27017/?authSource=admin \
    DB_NAME=opscore \
    python backend/scripts/create_admin.py --email you@example.com --password 'StrongPass#1'

If --password is omitted a strong one is generated and printed once.
"""
import argparse
import os
import secrets
import string
import sys
from datetime import datetime, timezone

try:
    from pymongo import MongoClient
    from passlib.context import CryptContext
except ImportError as exc:  # pragma: no cover
    sys.exit(f"Missing dependency ({exc}). Run inside the backend env where pymongo+passlib are installed.")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def gen_password(n: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#%^*-_"
    # ensure at least one of each class
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(n))
        if (any(c.islower() for c in pw) and any(c.isupper() for c in pw)
                and any(c.isdigit() for c in pw) and any(c in "!@#%^*-_" for c in pw)):
            return pw


def main() -> int:
    ap = argparse.ArgumentParser(description="Create or reset an admin user in MongoDB.")
    ap.add_argument("--email", default=os.environ.get("ADMIN_EMAIL"), help="Admin email (login).")
    ap.add_argument("--password", default=os.environ.get("ADMIN_PASSWORD"), help="Admin password (generated if omitted).")
    ap.add_argument("--name", default=os.environ.get("ADMIN_NAME", "Administrator"), help="Display name.")
    ap.add_argument("--mongo-url", default=os.environ.get("MONGO_URL"), help="Mongo connection string.")
    ap.add_argument("--db-name", default=os.environ.get("DB_NAME"), help="Database name.")
    ap.add_argument("--keep-existing-password", action="store_true",
                    help="If the user already exists, only promote to admin; do not change the password.")
    args = ap.parse_args()

    if not args.email:
        return _fail("--email is required (or set ADMIN_EMAIL).")
    if not args.mongo_url:
        return _fail("MONGO_URL is required (set env or pass --mongo-url).")
    if not args.db_name:
        return _fail("DB_NAME is required (set env or pass --db-name).")

    email = args.email.strip().lower()
    password = args.password or gen_password()
    generated = args.password is None

    client = MongoClient(args.mongo_url, serverSelectionTimeoutMS=8000)
    try:
        client.admin.command("ping")
    except Exception as exc:  # noqa: BLE001
        return _fail(f"Cannot reach MongoDB at the given URL: {exc}")

    db = client[args.db_name]
    now = datetime.now(timezone.utc).isoformat()
    existing = db.users.find_one({"email": email})

    if existing:
        update = {"is_admin": True, "updated_at": now}
        if not args.keep_existing_password:
            update["password_hash"] = pwd_context.hash(password)
            update["must_change_password"] = False
        db.users.update_one({"email": email}, {"$set": update})
        action = "promoted to admin" + ("" if args.keep_existing_password else " + password reset")
        user_id = existing["id"]
    else:
        user_id = secrets.token_hex(16)
        db.users.insert_one({
            "id": user_id,
            "email": email,
            "name": args.name,
            "password_hash": pwd_context.hash(password),
            "avatar_url": None,
            "created_at": now,
            "must_change_password": False,
            "is_admin": True,
        })
        action = "created"

    print("=" * 56)
    print(f"  Admin user {action}")
    print("=" * 56)
    print(f"  URL (UI)   : {os.environ.get('PUBLIC_APP_URL', 'http://localhost:3000')}/login")
    print(f"  Email      : {email}")
    if args.keep_existing_password and existing:
        print("  Password   : (unchanged)")
    else:
        print(f"  Password   : {password}")
    print(f"  User ID    : {user_id}")
    print(f"  is_admin   : True")
    if generated:
        print("\n  NOTE: password was auto-generated above — store it now; it is not shown again.")
    print("=" * 56)
    client.close()
    return 0


def _fail(msg: str) -> int:
    print(f"ERROR: {msg}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
