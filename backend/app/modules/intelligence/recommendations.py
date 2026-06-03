"""Recommendations engine (Module 8).

Rule-based and EXPLAINABLE: each recommendation states why it fired and carries the exact
`source_data` that triggered it. Derived from current metrics, per-department health, task
distribution, and the risk engine — never from an opaque model.
"""
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db_mongo import db as mongo
from app.modules.org.models import Department
from app.modules.reporting.service import department_metrics, compute_metrics, week_bounds
from app.modules.dashboards.service import department_user_ids
from app.modules.intelligence.risk import detect_risks
from app.modules.intelligence.scoring import health_score

_PRIORITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _rec(rtype: str, priority: str, title: str, message: str, explanation: str,
         source_data: Dict[str, Any], department_id: Optional[str] = None) -> Dict[str, Any]:
    return {"type": rtype, "priority": priority, "title": title, "message": message,
            "explanation": explanation, "source_data": source_data, "department_id": department_id}


async def _open_tasks_by_user(user_ids: List[str]) -> Dict[str, int]:
    if not user_ids:
        return {}
    rows = await mongo.tasks.find(
        {"status": {"$ne": "done"}, "$or": [{"owner_id": {"$in": user_ids}}, {"assignee_id": {"$in": user_ids}}]},
        {"_id": 0, "owner_id": 1, "assignee_id": 1},
    ).to_list(10000)
    counts: Dict[str, int] = {}
    for t in rows:
        u = t.get("assignee_id") or t.get("owner_id")
        if u in user_ids:
            counts[u] = counts.get(u, 0) + 1
    return counts


async def build_recommendations(session: AsyncSession, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    now = now or datetime.now(timezone.utc)
    start, _ = week_bounds(now)
    recs: List[Dict[str, Any]] = []

    departments = (await session.execute(select(Department).where(Department.is_active == True))).scalars().all()  # noqa: E712
    for d in departments:
        dm = await department_metrics(session, d.id, start, now)
        risks = await detect_risks(session, now, department_id=d.id)
        health = health_score(dm["metrics"], dm["participation"], risks)

        # 1. Department requires attention
        if health["score"] < 60:
            pr = "critical" if health["score"] < 40 else "high"
            recs.append(_rec("department_attention", pr, f"{d.name} requires attention",
                             f"{d.name} health score is {health['score']} ({health['grade']}).",
                             "Health score below 60 driven by delays/risks/participation.",
                             {"health": health, "risk_count": len(risks),
                              "delayed": dm["metrics"]["tasks"]["delayed"],
                              "participation_rate": dm["participation"]["participation_rate"]}, d.id))

        # 2. Employee workload imbalance
        counts = await _open_tasks_by_user(dm["user_ids"])
        if counts:
            values = list(counts.values())
            mx = max(values)
            avg = sum(values) / len(values)
            if mx >= 8 and mx >= 2 * max(1, avg):
                top = max(counts.items(), key=lambda x: x[1])
                recs.append(_rec("workload_imbalance", "medium", f"Workload imbalance in {d.name}",
                                 f"One member holds {mx} open tasks vs a team average of {avg:.1f}.",
                                 "Max open tasks >= 8 and >= 2x the team average.",
                                 {"max_open": mx, "avg_open": round(avg, 1), "user_id": top[0],
                                  "distribution": counts}, d.id))

    # 3/4/5 — company-wide signals from the risk engine
    company_metrics = await compute_metrics(session, None, None, start, now)
    company_risks = await detect_risks(session, now, department_id=None)
    delayed = company_metrics["tasks"]["delayed"]
    if delayed >= 10:
        recs.append(_rec("too_many_delays", "high" if delayed >= 20 else "medium",
                         f"{delayed} delayed tasks company-wide",
                         "A large backlog of overdue work is accumulating.",
                         "Company delayed task count >= 10.",
                         {"delayed": delayed, "open": company_metrics["tasks"]["open"]}))

    for r in company_risks:
        if r["type"] == "approval_bottleneck":
            recs.append(_rec("approval_bottleneck", r["level"], "Approval bottleneck",
                             f"{r['source'].get('count', 0)} approval(s) stalled.",
                             "Approvals pending beyond the SLA window.", r["source"], r.get("department_id")))
        elif r["type"] == "meeting_followup_failure":
            recs.append(_rec("meeting_followup", r["level"], "Meeting follow-up issues",
                             f"{r['source'].get('count', 0)} overdue action item(s).",
                             "Meeting action items past due and incomplete.", r["source"], r.get("department_id")))

    recs.sort(key=lambda x: _PRIORITY_RANK.get(x["priority"], 9))
    return recs
