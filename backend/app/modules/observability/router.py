"""Observability & analytics API (Module 4) — operational insight over audit + request data.

Gated by audit.view. Derives user-activity analytics and module-usage statistics from the
Audit Log (Postgres), and failed-operations / permission-usage from the request-metrics +
error collections written by the observability middleware.
"""
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db_mongo import db as mongo
from app.core.db_postgres import get_session
from app.modules.audit.models import AuditLog
from app.modules.rbac.resolver import require_permission
from app.shared.observability import metrics_summary

router = APIRouter()


@router.get("/observability/user-activity")
async def user_activity(limit: int = 50, user=Depends(require_permission("audit.view")),
                        session: AsyncSession = Depends(get_session)):
    """Per-user action counts from the audit log (who is doing what)."""
    rows = (await session.execute(
        select(AuditLog.actor_user_id, AuditLog.actor_name, func.count().label("n"))
        .group_by(AuditLog.actor_user_id, AuditLog.actor_name)
        .order_by(func.count().desc()).limit(min(max(limit, 1), 200))
    )).all()
    return [{"actor_user_id": r[0], "actor_name": r[1], "actions": r[2]} for r in rows]


@router.get("/observability/module-usage")
async def module_usage(user=Depends(require_permission("audit.view")), session: AsyncSession = Depends(get_session)):
    """Usage statistics grouped by module (audit action namespace) and by entity type."""
    by_action = (await session.execute(
        select(AuditLog.action, func.count().label("n")).group_by(AuditLog.action).order_by(func.count().desc())
    )).all()
    modules: Dict[str, int] = {}
    for action, n in by_action:
        mod = (action or "other").split(".")[0]
        modules[mod] = modules.get(mod, 0) + n
    by_entity = (await session.execute(
        select(AuditLog.entity_type, func.count().label("n")).group_by(AuditLog.entity_type).order_by(func.count().desc())
    )).all()
    return {
        "by_module": [{"module": k, "count": v} for k, v in sorted(modules.items(), key=lambda x: -x[1])],
        "by_action": [{"action": a, "count": n} for a, n in by_action[:50]],
        "by_entity_type": [{"entity_type": e, "count": n} for e, n in by_entity],
    }


@router.get("/observability/failed-operations")
async def failed_operations(limit: int = 50, user=Depends(require_permission("audit.view"))):
    """Recent server errors + failed background sends."""
    errors = await mongo.api_errors.find({}, {"_id": 0}).sort("created_at", -1).to_list(min(max(limit, 1), 200))
    failed_reminders = await mongo.reminders.count_documents({"error": {"$exists": True}})
    stuck_reminders = await mongo.reminders.count_documents({"sent": False, "attempts": {"$gte": 1}})
    return {"recent_errors": errors, "error_count": len(errors),
            "failed_reminders": failed_reminders, "retrying_reminders": stuck_reminders}


@router.get("/observability/permission-usage")
async def permission_usage(user=Depends(require_permission("audit.view"))):
    """Permission-denial hotspots (403s) per route — surfaces over/under-scoped access."""
    rows = await mongo.api_metrics.find({"denials": {"$gt": 0}}, {"_id": 0}).sort("denials", -1).to_list(100)
    total_denials = sum(r.get("denials", 0) for r in rows)
    return {"total_denials": total_denials,
            "by_route": [{"route": r["id"], "denials": r.get("denials", 0), "count": r.get("count", 0)} for r in rows]}


@router.get("/observability/metrics")
async def request_metrics(user=Depends(require_permission("audit.view"))):
    """Aggregate request metrics: volume, latency, error rate, slowest/busiest routes."""
    return await metrics_summary()
