"""Weekly department + monthly executive reports (Modules 4 & 5).

Built on the reusable reporting foundation (Module 10): compute_metrics + participation +
risk detection + health scoring, wrapped in an AI (or fallback) narrative, and persisted to
the shared Postgres `reports` table so history is queryable alongside Phase 2 reports.
"""
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db_mongo import db as mongo
from app.modules.reporting.service import (
    compute_metrics, participation, store_report, department_metrics,
    all_active_departments, week_bounds, month_bounds,
)
from app.modules.dashboards.service import department_user_ids
from app.modules.intelligence.risk import detect_risks
from app.modules.intelligence.scoring import health_score
from app.modules.intelligence.ai import narrate

_WEEKLY_SYSTEM = ("You are a department chief of staff. Write a concise weekly status summary covering "
                  "throughput, delays, risks, approvals, meetings and team participation.")
_MONTHLY_SYSTEM = ("You are a chief of staff to the CEO. Write a concise monthly executive summary of company "
                   "performance, the standout and at-risk departments, and the key operational risks.")


async def _activity_count(department_id: Optional[str], start: datetime, end: datetime) -> int:
    q: Dict[str, Any] = {"created_at": {"$gte": start.isoformat(), "$lte": end.isoformat()}}
    if department_id:
        q["department_id"] = department_id
    return await mongo.activity_feed.count_documents(q)


def _weekly_fallback(name: str, data: dict) -> str:
    t = data["metrics"]["tasks"]
    return (f"{name}: {t['completed']} completed, {t['delayed']} delayed, {t['open']} open. "
            f"{data['metrics']['meetings_held']} meeting(s), {data['participation']['participation_rate']}% participation, "
            f"{len(data['risks'])} risk(s) ({data['health']['grade']}).")


async def generate_weekly_department_report(session: AsyncSession, department_id: str, ref: datetime,
                                            user: dict) -> Any:
    start, end = week_bounds(ref)
    dm = await department_metrics(session, department_id, start, end)
    risks = await detect_risks(session, end, department_id=department_id)
    health = health_score(dm["metrics"], dm["participation"], risks)
    data = {
        "scope": "department", "department_id": department_id,
        "metrics": dm["metrics"], "participation": dm["participation"],
        "activity_level": await _activity_count(department_id, start, end),
        "risks": risks, "health": health,
    }
    from sqlalchemy import select
    from app.modules.org.models import Department
    dept = (await session.execute(select(Department).where(Department.id == department_id))).scalar_one_or_none()
    name = dept.name if dept else department_id
    narrative, ai_used = await narrate(_WEEKLY_SYSTEM, {"name": name, **data}, _weekly_fallback(name, data),
                                       user_id=user.get("id"), session_id=f"wk-{department_id}")
    data["ai_used"] = ai_used
    r = await store_report(session, "weekly_department", "department", department_id,
                           start.date().isoformat(), end.date().isoformat(), data, narrative, user.get("id"))
    return r


async def generate_monthly_executive_report(session: AsyncSession, ref: datetime, user: dict) -> Any:
    start, end = month_bounds(ref)
    company_metrics = await compute_metrics(session, None, None, start, end)
    company_risks = await detect_risks(session, end, department_id=None)

    departments = []
    for d in await all_active_departments(session):
        uids = list(await department_user_ids(session, d.id))
        m = await compute_metrics(session, uids, d.id, start, end)
        p = await participation(session, uids, start, end)
        dr = await detect_risks(session, end, department_id=d.id)
        h = health_score(m, p, dr)
        departments.append({
            "department_id": d.id, "name": d.name,
            "performance": m, "participation": p, "activity_level": await _activity_count(d.id, start, end),
            "risks": dr, "risk_count": len(dr), "pending_approvals": m["approvals"]["pending"],
            "delays": m["tasks"]["delayed"], "operational_health": h,
        })

    company_health = health_score(company_metrics, {"participation_rate": 100}, company_risks)
    data = {
        "scope": "company", "metrics": company_metrics,
        "activity_level": await _activity_count(None, start, end),
        "risks": company_risks, "health": company_health, "departments": departments,
    }
    fallback = (f"Company: {company_metrics['tasks']['completed']} tasks completed, "
                f"{company_metrics['tasks']['delayed']} delayed across {len(departments)} department(s); "
                f"{len(company_risks)} company risk(s); health {company_health['grade']}.")
    narrative, ai_used = await narrate(_MONTHLY_SYSTEM, data, fallback, user_id=user.get("id"), session_id="monthly-exec")
    data["ai_used"] = ai_used
    r = await store_report(session, "monthly_company", "company", None,
                           start.date().isoformat(), end.date().isoformat(), data, narrative, user.get("id"))
    return r
