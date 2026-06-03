"""Executive digests (Module 9) — daily / weekly / monthly.

A digest condenses the intelligence dashboard into a stored, narrated artifact. One record
per (period_type, period) is kept, so history accrues across periods. Stored in Mongo
`executive_digests`.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db_mongo import db as mongo
from app.core.utils import new_id, now_iso
from app.modules.reporting.service import compute_metrics, week_bounds, month_bounds
from app.modules.intelligence.risk import detect_risks, summarize_levels
from app.modules.intelligence.scoring import health_score
from app.modules.intelligence.recommendations import build_recommendations
from app.modules.intelligence.ai import narrate, source_hash

PERIOD_TYPES = ("daily", "weekly", "monthly")
_SYSTEM = ("You are the CEO's chief of staff. Write a brief executive digest: overall health, the most "
           "important risks, and the top recommended actions.")


def _bounds(period_type: str, ref: datetime):
    if period_type == "daily":
        start = ref.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=1) - timedelta(seconds=1)
    if period_type == "weekly":
        return week_bounds(ref)
    return month_bounds(ref)


async def generate_digest(session: AsyncSession, period_type: str, ref: datetime, user: dict,
                          force: bool = False) -> Dict[str, Any]:
    if period_type not in PERIOD_TYPES:
        raise ValueError("period_type must be daily|weekly|monthly")
    start, end = _bounds(period_type, ref)

    metrics = await compute_metrics(session, None, None, start, end)
    risks = await detect_risks(session, end, department_id=None)
    health = health_score(metrics, {"participation_rate": 100}, risks)
    recommendations = await build_recommendations(session, end)
    top_risks = risks[:5]
    top_recs = recommendations[:5]

    structured = {
        "period_type": period_type,
        "health": health,
        "key_metrics": {
            "tasks_completed": metrics["tasks"]["completed"],
            "tasks_created": metrics["tasks"]["created"],
            "tasks_delayed": metrics["tasks"]["delayed"],
            "meetings_held": metrics["meetings_held"],
            "approvals_pending": metrics["approvals"]["pending"],
            "daily_updates": metrics["daily_updates_submitted"],
        },
        "risk_indicators": summarize_levels(risks),
        "top_risks": top_risks,
        "top_recommendations": top_recs,
    }
    payload = {"period": [start.date().isoformat(), end.date().isoformat()], **structured}
    shash = source_hash(payload)

    existing = await mongo.executive_digests.find_one(
        {"period_type": period_type, "period_start": start.date().isoformat()}, {"_id": 0})
    if existing and existing.get("source_hash") == shash and not force:
        existing["deduped"] = True
        return existing

    fallback = (f"{period_type.title()} digest: health {health['grade']} ({health['score']}), "
                f"{metrics['tasks']['completed']} completed / {metrics['tasks']['delayed']} delayed, "
                f"{len(top_risks)} key risk(s), {len(top_recs)} recommendation(s).")
    narrative, ai_used = await narrate(_SYSTEM, payload, fallback, user_id=user.get("id"),
                                       session_id=f"digest-{period_type}")
    doc = {
        "id": existing["id"] if existing else new_id(),
        "period_type": period_type, "period_start": start.date().isoformat(), "period_end": end.date().isoformat(),
        "structured": structured, "narrative": narrative, "ai_used": ai_used,
        "source_hash": shash, "generated_by": user.get("id"), "created_at": now_iso(),
    }
    await mongo.executive_digests.replace_one({"id": doc["id"]}, doc, upsert=True)
    doc["deduped"] = False
    return doc
