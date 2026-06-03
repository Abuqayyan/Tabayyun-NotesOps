"""OpsCore API — application factory and wiring.

Phase 0 modular entry point. Mounts every feature module's router under /api,
preserving all existing routes. Hardening applied here: explicit CORS (no wildcard
with credentials), rate limiting, security headers, global error handling, Mongo
index creation + admin seed + reminder scheduler on startup.
"""
import asyncio
import logging

from fastapi import FastAPI, APIRouter, WebSocket, WebSocketDisconnect
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

from app.core.config import APP_NAME, CORS_ORIGINS
from app.core.db_mongo import client, create_indexes, mongo_healthcheck
from app.core.db_postgres import postgres_healthcheck, dispose_engine
from app.core.security import decode_token
from app.core.errors import register_exception_handlers
from app.shared.rate_limit import limiter
from app.shared.websocket import ws_manager
from app.shared.scheduler import reminder_loop, seed_admin

# Routers (one per feature module)
from app.modules.dashboard import router as dashboard_router
from app.modules.auth import router as auth_router
from app.modules.users import router as users_router
from app.modules.projects import router as projects_router
from app.modules.files import router as files_router
from app.modules.tasks import router as tasks_router
from app.modules.notes import router as notes_router
from app.modules.reminders import router as reminders_router
from app.modules.ai import router as ai_router
from app.modules.settings import router as settings_router
from app.modules.analytics import router as analytics_router
from app.modules.focus import router as focus_router
from app.modules.notifications import router as notifications_router
from app.modules.calendar import router as calendar_router
from app.modules.canvas import router as canvas_router
from app.modules.share import router as share_router
# Phase 1 — organizational spine
from app.modules.org.router import router as org_router
from app.modules.rbac.router import router as rbac_router
from app.modules.audit.router import router as audit_router
from app.modules.activity.router import router as activity_router
# Phase 2 — operational core
from app.modules.daily_updates.router import router as daily_updates_router
from app.modules.meetings.router import router as meetings_router
from app.modules.approvals.router import router as approvals_router
from app.modules.dashboards.router import router as dashboards_router
from app.modules.reporting.router import router as reporting_router
# Phase 3 — intelligence layer
from app.modules.knowledge.router import router as knowledge_router
from app.modules.intelligence.router import router as intelligence_router
# Phase 4 — CRM
from app.modules.crm.router import router as crm_router
# Phase 5 — platform maturity
from app.modules.search.router import router as search_router
from app.modules.notifications.center import router as notification_center_router
from app.modules.observability.router import router as observability_router
from app.modules.ops.router import router as ops_router
from app.modules.exports.router import router as exports_router
from app.modules.settings.center import router as settings_center_router
from app.shared.observability import RequestObservabilityMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("opscore")

app = FastAPI(title="OpsCore API")

# Rate limiting wiring (per-route decorators live in the modules).
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

api = APIRouter(prefix="/api")

# Mount module routers. Paths are unique across modules; tasks/router.py internally
# orders /tasks/today-hints before /tasks/{tid}.
for r in (
    dashboard_router, auth_router, users_router, projects_router, files_router,
    tasks_router, notes_router, reminders_router, ai_router, settings_router,
    analytics_router, focus_router, notifications_router, calendar_router,
    canvas_router, share_router,
    org_router, rbac_router, audit_router, activity_router,
    daily_updates_router, meetings_router, approvals_router, dashboards_router, reporting_router,
    knowledge_router, intelligence_router,
    crm_router,
    search_router, notification_center_router, observability_router, ops_router,
    exports_router, settings_center_router,
):
    api.include_router(r)


@api.get("/health")
async def health():
    mongo_ok = await mongo_healthcheck()
    pg = await postgres_healthcheck()
    return {"app": APP_NAME, "status": "ok", "mongo": mongo_ok, "postgres": pg}


# ---- Websocket (token via query param) ----
@app.websocket("/api/ws")
async def ws_endpoint(ws: WebSocket, token: str):
    await ws.accept()
    uid = decode_token(token)
    if not uid:
        await ws.close(code=4001)
        return
    ws_manager.register(uid, ws)
    try:
        while True:
            await ws.receive_text()  # keepalive
    except WebSocketDisconnect:
        ws_manager.disconnect(uid, ws)
    except Exception:  # noqa: BLE001
        ws_manager.disconnect(uid, ws)


# ---- Security headers ----
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        response.headers.setdefault("X-XSS-Protection", "1; mode=block")
        return response


# ---- Mount router + middleware ----
app.include_router(api)
register_exception_handlers(app)
app.add_middleware(SecurityHeadersMiddleware)
# Phase 5: request metrics + error/denial capture + X-Request-ID (best-effort, never blocks).
app.add_middleware(RequestObservabilityMiddleware)

# CORS: explicit origins only. Credentials are disabled if a wildcard is present
# (wildcard + credentials is invalid and unsafe).
_allow_credentials = "*" not in CORS_ORIGINS
app.add_middleware(
    CORSMiddleware,
    allow_credentials=_allow_credentials,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _on_startup():
    try:
        await create_indexes()
    except Exception as e:  # noqa: BLE001
        log.warning(f"Index creation issue: {e}")
    await seed_admin()
    # Phase 1: ensure relational schema + seed RBAC catalog/system roles (idempotent).
    from app.core.config import DATABASE_URL
    if DATABASE_URL:
        try:
            from app.core.db_postgres import create_all, session_scope
            from app.modules.rbac.service import seed_rbac
            await create_all()
            async with session_scope() as s:
                seeded = await seed_rbac(s)
            log.info(f"RBAC seeded: {seeded}")
        except Exception as e:  # noqa: BLE001
            log.warning(f"Postgres schema/seed skipped: {e}")
    pg = await postgres_healthcheck()
    log.info(f"PostgreSQL: {pg}")
    asyncio.create_task(reminder_loop())
    log.info("OpsCore started — scheduler running")


@app.on_event("shutdown")
async def _on_shutdown():
    client.close()
    await dispose_engine()
