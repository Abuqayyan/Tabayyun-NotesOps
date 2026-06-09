"""Admin Operations Center (Module 7) — internal monitoring dashboard.

Gated by ops.view. Surfaces system health, scheduler/reminder/escalation status, recent
API errors, request metrics, search metrics, and background-job health — read-only, derived
from the live stores + the observability collections written by the middleware/scheduler.
"""
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db_mongo import db as mongo, mongo_healthcheck
from app.core.db_postgres import get_session, postgres_healthcheck
from app.modules.rbac.resolver import require_permission
from app.shared.observability import metrics_summary

router = APIRouter()


def _parse(s):
    try:
        d = datetime.fromisoformat((s or "").replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


async def _scheduler_status() -> Dict[str, Any]:
    hb = await mongo.ops_heartbeat.find_one({"id": "scheduler"}, {"_id": 0}) or {}
    last = _parse(hb.get("last_run_at"))
    now = datetime.now(timezone.utc)
    age = (now - last).total_seconds() if last else None
    return {
        "alive": bool(age is not None and age < 180),  # heartbeat within 3 min
        "last_run_at": hb.get("last_run_at"), "loop_count": hb.get("loop_count", 0),
        "last_escalation_at": hb.get("last_escalation_at"), "heartbeat_age_seconds": round(age, 1) if age is not None else None,
    }


async def _reminder_status() -> Dict[str, Any]:
    now_iso = datetime.now(timezone.utc).isoformat()
    return {
        "pending": await mongo.reminders.count_documents({"enabled": True, "sent": {"$ne": True}}),
        "due_now": await mongo.reminders.count_documents({"enabled": True, "sent": {"$ne": True}, "fire_at": {"$lte": now_iso}}),
        "sent": await mongo.reminders.count_documents({"sent": True}),
        "failed": await mongo.reminders.count_documents({"error": {"$exists": True}}),
        "retrying": await mongo.reminders.count_documents({"sent": False, "attempts": {"$gte": 1}}),
    }


async def _escalation_status() -> Dict[str, Any]:
    rows = await mongo.escalations.find({}, {"_id": 0, "level": 1}).to_list(5000)
    by_level: Dict[int, int] = {}
    for r in rows:
        by_level[r.get("level", 0)] = by_level.get(r.get("level", 0), 0) + 1
    return {"total": len(rows), "by_level": by_level}


@router.get("/ops/health")
async def ops_health(user=Depends(require_permission("ops.view"))):
    return {
        "mongo": await mongo_healthcheck(),
        "postgres": await postgres_healthcheck(),
        "scheduler": await _scheduler_status(),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/ops/scheduler")
async def ops_scheduler(user=Depends(require_permission("ops.view"))):
    return await _scheduler_status()


@router.get("/ops/reminders")
async def ops_reminders(user=Depends(require_permission("ops.view"))):
    return await _reminder_status()


@router.get("/ops/escalations")
async def ops_escalations(user=Depends(require_permission("ops.view"))):
    return await _escalation_status()


@router.get("/ops/errors")
async def ops_errors(limit: int = 50, user=Depends(require_permission("ops.view"))):
    rows = await mongo.api_errors.find({}, {"_id": 0}).sort("created_at", -1).to_list(min(max(limit, 1), 200))
    return {"count": len(rows), "errors": rows}


@router.get("/ops/metrics")
async def ops_metrics(user=Depends(require_permission("ops.view"))):
    metrics = await metrics_summary()
    metrics["search_queries"] = await mongo.search_history.count_documents({})
    return metrics


@router.get("/ops/jobs")
async def ops_jobs(user=Depends(require_permission("ops.view"))):
    """Background-job health: scheduler + reminders + escalations + intelligence artifacts."""
    return {
        "scheduler": await _scheduler_status(),
        "reminders": await _reminder_status(),
        "escalations": await _escalation_status(),
        "intelligence": {
            "summaries": await mongo.ai_summaries.count_documents({}),
            "digests": await mongo.executive_digests.count_documents({}),
        },
    }


@router.get("/ops/overview")
async def ops_overview(user=Depends(require_permission("ops.view")), session: AsyncSession = Depends(get_session)):
    return {
        "health": {"mongo": await mongo_healthcheck(), "postgres": await postgres_healthcheck()},
        "scheduler": await _scheduler_status(),
        "reminders": await _reminder_status(),
        "escalations": await _escalation_status(),
        "metrics": await metrics_summary(),
        "users": await mongo.users.count_documents({}),
        "notifications_unread_total": await mongo.notifications.count_documents({"read": False, "archived": False}),
    }
