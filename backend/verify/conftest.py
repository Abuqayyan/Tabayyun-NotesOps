"""Verification harness bootstrap.

Runs the REAL FastAPI app against an in-memory MongoDB (mongomock_motor), since no
Docker/Mongo/Postgres is available in this environment. This still exercises: imports,
circular-import safety, route registration, dependency injection, auth, RBAC, and the
full request/response cycle of every module.

Patches applied BEFORE the app is imported:
  - motor.AsyncIOMotorClient  -> mongomock_motor (in-memory)
  - sys.path                  -> backend/ + verify/stubs (stub emergentintegrations)
  - env                       -> valid secrets, ALLOW_REGISTRATION=true, no Postgres
"""
import os
import sys
import secrets
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
STUBS = Path(__file__).resolve().parent / "stubs"
for p in (str(BACKEND), str(STUBS)):
    if p not in sys.path:
        sys.path.insert(0, p)

# ---- Environment (valid config so fail-fast passes) ----
from cryptography.fernet import Fernet  # noqa: E402
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "opscore_verify")
os.environ.setdefault("JWT_SECRET", secrets.token_urlsafe(48))
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ["ALLOW_REGISTRATION"] = "true"
os.environ["CORS_ORIGINS"] = "http://localhost:3000"
os.environ["EMERGENT_LLM_KEY"] = "test-emergent-key"  # non-empty so claude_chat reaches the stub

# Relational layer: use a throwaway SQLite file (stands in for Postgres) so the RBAC /
# org / audit tables are really created + seeded and the resolver runs for real.
from pathlib import Path as _Path  # noqa: E402
_DBFILE = _Path(__file__).resolve().parent / "_verify_pg.sqlite"
try:
    _DBFILE.unlink()
except FileNotFoundError:
    pass
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_DBFILE.as_posix()}"

# ---- Patch motor -> in-memory before any app import ----
import mongomock_motor  # noqa: E402
import motor.motor_asyncio as _mm  # noqa: E402
_mm.AsyncIOMotorClient = mongomock_motor.AsyncMongoMockClient


@pytest.fixture(scope="session")
def appmod():
    import app.main as m
    # Neutralize the background reminder loop so it doesn't run during tests.
    async def _noop():
        return
    m.reminder_loop = _noop
    return m


@pytest.fixture(scope="session")
def client(appmod):
    from starlette.testclient import TestClient
    # Disable rate limiting for functional tests (a dedicated test re-enables it).
    from app.shared.rate_limit import limiter
    limiter.enabled = False
    with TestClient(appmod.app) as c:
        yield c


@pytest.fixture(scope="session")
def db(appmod):
    from app.core.db_mongo import db as _db
    return _db
