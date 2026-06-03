"""PostgreSQL infrastructure (Phase 0: connectivity only — no business tables yet).

Postgres is the future system of record for relational/transactional data (identity,
RBAC, org structure, approvals, finance, audit). In Phase 0 we only stand up the
connection + migration foundation (Alembic) and a healthcheck. No feature data is
migrated here. The engine is created lazily and the app boots even if Postgres is
briefly unreachable; status is surfaced via /api/health.
"""
import logging
from contextlib import asynccontextmanager
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

from app.core.config import DATABASE_URL

log = logging.getLogger("opscore.pg")

_engine: Optional[AsyncEngine] = None
_sessionmaker: Optional[async_sessionmaker] = None


class Base(DeclarativeBase):
    """Declarative base for future ORM models (RBAC, org, approvals, audit...)."""
    pass


def _normalize_url(url: str) -> str:
    """Ensure the async driver is used (postgresql+asyncpg://)."""
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


def get_engine() -> Optional[AsyncEngine]:
    global _engine, _sessionmaker
    if not DATABASE_URL:
        return None
    if _engine is None:
        _engine = create_async_engine(_normalize_url(DATABASE_URL), pool_pre_ping=True, future=True)
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)
    return _engine


async def get_session() -> AsyncSession:
    """FastAPI dependency for future relational modules."""
    if _sessionmaker is None:
        get_engine()
    if _sessionmaker is None:
        raise RuntimeError("PostgreSQL is not configured (DATABASE_URL missing).")
    async with _sessionmaker() as session:
        yield session


@asynccontextmanager
async def session_scope():
    """Context-managed session for startup tasks / scripts."""
    get_engine()
    if _sessionmaker is None:
        raise RuntimeError("PostgreSQL is not configured (DATABASE_URL missing).")
    async with _sessionmaker() as session:
        yield session


async def create_all() -> None:
    """Create all ORM tables (idempotent). Phase 1 bootstrap for the relational schema.

    ORM models are the single source of truth; this is safe to call on every startup.
    A fresh deploy that prefers Alembic can instead `alembic stamp head` after this.
    Importing the models module registers them on Base.metadata.
    """
    import app.modules.org.models  # noqa: F401
    import app.modules.rbac.models  # noqa: F401
    import app.modules.audit.models  # noqa: F401
    # Phase 2 relational schema
    import app.modules.daily_updates.models  # noqa: F401
    import app.modules.meetings.models  # noqa: F401
    import app.modules.approvals.models  # noqa: F401
    import app.modules.reporting.models  # noqa: F401
    # Phase 4 — CRM + client portal foundation
    import app.modules.crm.models  # noqa: F401
    import app.modules.crm.portal_models  # noqa: F401
    eng = get_engine()
    if eng is None:
        log.info("create_all skipped — DATABASE_URL not configured")
        return
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    log.info("PostgreSQL tables ensured (create_all)")


async def postgres_healthcheck() -> dict:
    """Returns {configured, ok} without raising."""
    if not DATABASE_URL:
        return {"configured": False, "ok": False}
    try:
        eng = get_engine()
        async with eng.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"configured": True, "ok": True}
    except Exception as exc:  # noqa: BLE001
        log.warning(f"Postgres healthcheck failed: {exc}")
        return {"configured": True, "ok": False}


async def dispose_engine() -> None:
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
