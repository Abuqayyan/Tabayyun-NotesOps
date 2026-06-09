"""Risk Detection Engine (Module 6).

Pure, rule-based, EXPLAINABLE risk detection over the live stores. Every risk carries a
`source` object with the exact counts/entities that triggered it, so dashboards and
recommendations can justify themselves. Scope is company-wide or a single department.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db_mongo import db as mongo
from app.modules.org.models import Employee, Department
from app.modules.approvals.models import ApprovalRequest
from app.modules.meetings.models import ActionItem
from app.modules.daily_updates.models import DailyUpdate
from app.modules.dashboards.service import department_user_ids
from app.modules.reporting.service import parse_dt

LEVELS = ["low", "medium", "high", "critical"]
LEVEL_SCORE = {"low": 25, "medium": 50, "high": 75, "critical": 95}

INACTIVE_DAYS = 7          # no activity in this many days => inactive
NO_UPDATE_DAYS = 3         # no daily update in this many days
APPROVAL_STALE_HOURS = 48  # pending approval older than this => bottleneck


def _level(count: int, med: int, high: int, crit: int) -> str:
    if count >= crit:
        return "critical"
    if count >= high:
        return "high"
    if count >= med:
        return "medium"
    return "low"


def _risk(rtype: str, level: str, title: str, description: str, source: Dict[str, Any],
          department_id: Optional[str] = None) -> Dict[str, Any]:
    return {"type": rtype, "level": level, "score": LEVEL_SCORE[level], "title": title,
            "description": description, "department_id": department_id, "source": source}


async def _scope_tasks(session: AsyncSession, department_id: Optional[str]) -> List[dict]:
    q: Dict[str, Any] = {}
    if department_id:
        uids = list(await department_user_ids(session, department_id))
        if not uids:
            return []
        q = {"$or": [{"owner_id": {"$in": uids}}, {"assignee_id": {"$in": uids}}]}
    return await mongo.tasks.find(q, {"_id": 0, "id": 1, "title": 1, "status": 1, "due_date": 1,
                                      "priority": 1, "owner_id": 1, "assignee_id": 1}).to_list(10000)


async def detect_risks(session: AsyncSession, now: Optional[datetime] = None,
                       department_id: Optional[str] = None) -> List[Dict[str, Any]]:
    now = now or datetime.now(timezone.utc)
    risks: List[Dict[str, Any]] = []
    tasks = await _scope_tasks(session, department_id)

    # 1. Overdue tasks
    overdue = [t for t in tasks if t.get("status") != "done" and (parse_dt(t.get("due_date")) and parse_dt(t["due_date"]) < now)]
    if overdue:
        lvl = _level(len(overdue), 3, 8, 15)
        risks.append(_risk("overdue_tasks", lvl, f"{len(overdue)} overdue task(s)",
                           "Open tasks past their due date.",
                           {"count": len(overdue), "samples": [{"id": t["id"], "title": t.get("title")} for t in overdue[:5]]},
                           department_id))

    # 2. Repeated delays (per assignee/owner with many overdue)
    by_user: Dict[str, int] = {}
    for t in overdue:
        u = t.get("assignee_id") or t.get("owner_id")
        if u:
            by_user[u] = by_user.get(u, 0) + 1
    repeat_offenders = {u: c for u, c in by_user.items() if c >= 3}
    if repeat_offenders:
        worst = max(repeat_offenders.values())
        lvl = _level(worst, 3, 6, 10)
        risks.append(_risk("repeated_delays", lvl, f"{len(repeat_offenders)} person(s) with repeated delays",
                           "Individuals carrying 3+ overdue tasks.",
                           {"offenders": [{"user_id": u, "overdue": c} for u, c in sorted(repeat_offenders.items(), key=lambda x: -x[1])]},
                           department_id))

    # 3. Blocked work
    blocked = [t for t in tasks if t.get("status") == "blocked"]
    if blocked:
        lvl = _level(len(blocked), 1, 4, 8)
        risks.append(_risk("blocked_work", lvl, f"{len(blocked)} blocked task(s)",
                           "Tasks explicitly marked blocked.",
                           {"count": len(blocked), "samples": [{"id": t["id"], "title": t.get("title")} for t in blocked[:5]]},
                           department_id))

    # 4. Approval bottlenecks
    aq = select(ApprovalRequest).where(ApprovalRequest.status == "pending")
    if department_id:
        aq = aq.where(ApprovalRequest.department_id == department_id)
    pending = (await session.execute(aq)).scalars().all()
    stale = [r for r in pending if (parse_dt(r.created_at) and (now - parse_dt(r.created_at)) > timedelta(hours=APPROVAL_STALE_HOURS))]
    if stale:
        lvl = _level(len(stale), 1, 3, 6)
        risks.append(_risk("approval_bottleneck", lvl, f"{len(stale)} stalled approval(s)",
                           f"Approvals pending more than {APPROVAL_STALE_HOURS}h.",
                           {"count": len(stale), "total_pending": len(pending),
                            "samples": [{"id": r.id, "title": r.title, "since": r.created_at} for r in stale[:5]]},
                           department_id))

    # 5. Meeting follow-up failures (overdue action items)
    iq = select(ActionItem).where(ActionItem.status.in_(["open", "in_progress"]))
    if department_id:
        iq = iq.where(ActionItem.department_id == department_id)
    action_items = (await session.execute(iq)).scalars().all()
    overdue_items = [a for a in action_items if a.due_date and parse_dt(a.due_date) and parse_dt(a.due_date) < now]
    if overdue_items:
        lvl = _level(len(overdue_items), 1, 4, 8)
        risks.append(_risk("meeting_followup_failure", lvl, f"{len(overdue_items)} overdue action item(s)",
                           "Meeting action items past due and not completed.",
                           {"count": len(overdue_items),
                            "samples": [{"id": a.id, "title": a.title, "meeting_id": a.meeting_id} for a in overdue_items[:5]]},
                           department_id))

    # 6. Inactive employees
    eq = select(Employee).where(Employee.employment_status == "active")
    if department_id:
        eq = eq.where(Employee.primary_department_id == department_id)
    employees = (await session.execute(eq)).scalars().all()
    inactive_emps = []
    activity_cutoff = (now - timedelta(days=INACTIVE_DAYS)).isoformat()
    update_cutoff = (now - timedelta(days=NO_UPDATE_DAYS)).date().isoformat()
    for e in employees:
        recent_activity = await mongo.activity_feed.find_one(
            {"actor_id": e.user_id, "created_at": {"$gte": activity_cutoff}}, {"_id": 0, "id": 1})
        recent_update = (await session.execute(select(DailyUpdate.id).where(
            DailyUpdate.user_id == e.user_id, DailyUpdate.update_date >= update_cutoff))).first()
        if not recent_activity and not recent_update:
            inactive_emps.append(e.user_id)
    if inactive_emps:
        lvl = _level(len(inactive_emps), 2, 5, 10)
        risks.append(_risk("inactive_employees", lvl, f"{len(inactive_emps)} inactive employee(s)",
                           f"No activity in {INACTIVE_DAYS}d and no update in {NO_UPDATE_DAYS}d.",
                           {"count": len(inactive_emps), "user_ids": inactive_emps[:10]}, department_id))

    # 7. Inactive departments (company scope only)
    if not department_id:
        depts = (await session.execute(select(Department).where(Department.is_active == True))).scalars().all()  # noqa: E712
        inactive_depts = []
        for d in depts:
            recent = await mongo.activity_feed.find_one(
                {"department_id": d.id, "created_at": {"$gte": activity_cutoff}}, {"_id": 0, "id": 1})
            if not recent:
                inactive_depts.append({"id": d.id, "name": d.name})
        if inactive_depts:
            lvl = _level(len(inactive_depts), 1, 3, 6)
            risks.append(_risk("inactive_departments", lvl, f"{len(inactive_depts)} inactive department(s)",
                               f"No department activity in {INACTIVE_DAYS}d.",
                               {"count": len(inactive_depts), "departments": inactive_depts}))

    risks.sort(key=lambda r: -r["score"])
    return risks


def summarize_levels(risks: List[Dict[str, Any]]) -> Dict[str, int]:
    out = {lvl: 0 for lvl in LEVELS}
    for r in risks:
        out[r["level"]] = out.get(r["level"], 0) + 1
    return out
