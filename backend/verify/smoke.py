"""Standalone import + startup smoke test (no pytest)."""
import os, sys, secrets, asyncio
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
STUBS = Path(__file__).resolve().parent / "stubs"
sys.path.insert(0, str(BACKEND)); sys.path.insert(0, str(STUBS))

from cryptography.fernet import Fernet
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "opscore_verify")
os.environ.setdefault("JWT_SECRET", secrets.token_urlsafe(48))
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ["ALLOW_REGISTRATION"] = "true"
os.environ.pop("DATABASE_URL", None)

import mongomock_motor, motor.motor_asyncio as _mm
_mm.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient

print("[1] importing app.main ...")
import app.main as m
print("    OK — app imported, no circular/import errors")

routes = [r for r in m.app.routes]
http = [r for r in routes if hasattr(r, "methods")]
print(f"[2] routes registered: {len(http)} HTTP routes + websocket")

print("[3] create_indexes() on in-memory mongo ...")
from app.core.db_mongo import create_indexes
n = asyncio.get_event_loop().run_until_complete(create_indexes())
print(f"    OK — {n} indexes ensured")

print("[4] TestClient startup + /api/health ...")
m.reminder_loop = lambda: None  # neutralize (sync no-op won't be awaited by patched path)
from starlette.testclient import TestClient
async def _noop():
    return
m.reminder_loop = _noop
with TestClient(m.app) as c:
    r = c.get("/api/health")
    print("    /api/health ->", r.status_code, r.json())
    r2 = c.get("/api/")
    print("    /api/        ->", r2.status_code, r2.json())
print("SMOKE OK")
