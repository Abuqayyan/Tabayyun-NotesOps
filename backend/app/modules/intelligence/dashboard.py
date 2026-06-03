"""Executive Intelligence dashboard composition (Module 7).

Pulls health scores, risks, escalations, activity ranking, trend/period comparisons, and
recommendations into one CEO-facing payload. Read-only; reuses the risk engine, scoring,
reporting foundation, and the Phase 2 escalation records.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db_mongo import db as mongo
from app.modules.org.models import Department
from app.modules.approvals.models import ApprovalRequest
from app.modules.reporting.service import (
    compute_metrics, participation, department_metrics, week_bounds, month_bounds,
)
from app.modules.dashboards.service import department_user_ids
from app.modules.intelligence.risk import detect_risks, summarize_levels
from app.modules.intelligence.scoring import health_score
from app.modules.intelligence.recommendations import build_recommendations


async def _activity_count(department_id: Optional[str], start: datetime, end: datetime) -> int:
    q: Dict[str, Any] = {"created_at": {"$gte": start.isoformat(), "$lte": end.isoformat()}}
    if department_id:
        q["department_id"] = department_id
    return await mongo.activity_feed.count_documents(q)


def _delta(curr: int, prev: int) -> Dict[str, Any]:
    return {"current": curr, "previous": prev, "change": curr - prev,
            "direction": "up" if curr > prev else "down" if curr < prev else "flat"}


async def _period_comparison(session: AsyncSession, cur_start, cur_end, prev_start, prev_end) -> Dict[str, Any]:
    cur = await compute_metrics(session, None, None, cur_start, cur_end)
    prev = await compute_metrics(session, None, None, prev_start, prev_end)
    return {
        "completed": _delta(cur["tasks"]["completed"], prev["tasks"]["completed"]),
        "created": _delta(cur["tasks"]["created"], prev["tasks"]["created"]),
        "delayed": _delta(cur["tasks"]["delayed"], prev["tasks"]["delayed"]),
        "meetings": _delta(cur["meetings_held"], prev["meetings_held"]),
        "approvals_approved": _delta(cur["approvals"]["approved"], prev["approvals"]["approved"]),
    }


async def build_intelligence_dashboard(session: AsyncSession, now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    wk_start, wk_end = week_bounds(now)
    mo_start, mo_end = month_bounds(now)

    company_metrics = await compute_metrics(session, None, None, wk_start, now)
    company_risks = await detect_risks(session, now, department_id=None)
    company_health = health_score(company_metrics, {"participation_rate": 100}, company_risks)

    # Department health + activity ranking
    dept_health: List[Dict[str, Any]] = []
    for d in (await session.execute(select(Department).where(Department.is_active == True))).scalars().all():  # noqa: E712
        dm = await department_metrics(session, d.id, wk_start, now)
        dr = await detect_risks(session, now, department_id=d.id)
        h = health_score(dm["metrics"], dm["participation"], dr)
        dept_health.append({
            "id": d.id, "name": d.name, "health": h, "risk_count": len(dr),
            "activity_level": await _activity_count(d.id, wk_start, now),
            "delayed": dm["metrics"]["tasks"]["delayed"], "open": dm["metrics"]["tasks"]["open"],
            "participation_rate": dm["participation"]["participation_rate"],
        })
    ranked = sorted(dept_health, key=lambda x: -x["activity_level"])
    most_active = ranked[:3]
    least_active = list(reversed(ranked[-3:])) if len(ranked) > 3 else []

    # Pending approvals + escalations + blocked work
    pending = (await session.execute(select(ApprovalRequest).where(ApprovalRequest.status == "pending"))).scalars().all()
    escalations = await mongo.escalations.find({}, {"_id": 0}).sort("level", -1).to_list(50)
    esc_by_level: Dict[int, int] = {}
    for e in escalations:
        esc_by_level[e.get("level", 0)] = esc_by_level.get(e.get("level", 0), 0) + 1
    blocked = next((r for r in company_risks if r["type"] == "blocked_work"), None)

    # Trend / comparisons
    prev_wk_start, prev_wk_end = week_bounds(wk_start - timedelta(days=1))
    prev_mo_start, prev_mo_end = month_bounds(mo_start - timedelta(days=1))
    weekly_comparison = await _period_comparison(session, wk_start, now, prev_wk_start, prev_wk_end)
    monthly_comparison = await _period_comparison(session, mo_start, now, prev_mo_start, prev_mo_end)

    recommendations = await build_recommendations(session, now)

    return {
        "generated_at": now.isoformat(),
        "company_health_score": company_health["score"],
        "company_health": company_health,
        "department_health": dept_health,
        "operational_risks": company_risks,
        "risk_indicators": summarize_levels(company_risks),
        "blocked_work": blocked["source"] if blocked else {"count": 0},
        "pending_approvals": {"count": len(pending),
                              "items": [{"id": r.id, "title": r.title, "department_id": r.department_id,
                                         "created_at": r.created_at} for r in pending[:10]]},
        "escalations": {"total": len(escalations), "by_level": esc_by_level, "items": escalations[:10]},
        "most_active_departments": most_active,
        "least_active_departments": least_active,
        "trend_analysis": {"weekly": weekly_comparison, "monthly": monthly_comparison},
        "weekly_comparison": weekly_comparison,
        "monthly_comparison": monthly_comparison,
        "recommendations": recommendations,
    }
