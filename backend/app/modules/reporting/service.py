"""Reusable reporting foundation (Module 10).

A single place that turns the live stores (Mongo tasks/activity + Postgres
meetings/approvals/daily-updates/org) into period metrics, participation, and persisted
report rows. Phase 2's report endpoint, the Phase 3 weekly/monthly generators, the
executive intelligence dashboard, and any FUTURE module (CRM/Finance/HR) reuse these
functions instead of re-implementing aggregation.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db_mongo import db as mongo
from app.core.utils import now_iso
from app.modules.meetings.models import Meeting
from app.modules.approvals.models import ApprovalRequest
from app.modules.daily_updates.models import DailyUpdate
from app.modules.org.models import Department
from app.modules.dashboards.service import department_user_ids


def parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def in_period(s: Optional[str], start: datetime, end: datetime) -> bool:
    d = parse_dt(s)
    return bool(d and start <= d <= end)


def period_bounds(period_start: str, period_end: str):
    """Parse 'YYYY-MM-DD' bounds into aware datetimes spanning the full days."""
    start = parse_dt(period_start + "T00:00:00+00:00")
    end = parse_dt(period_end + "T23:59:59+00:00")
    return start, end


def week_bounds(ref: datetime):
    """ISO week (Mon..Sun) containing ref."""
    monday = (ref - timedelta(days=ref.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return monday, monday + timedelta(days=7) - timedelta(seconds=1)


def month_bounds(ref: datetime):
    start = ref.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    nxt = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return start, nxt - timedelta(seconds=1)


async def compute_metrics(session: AsyncSession, user_ids: Optional[List[str]],
                          department_id: Optional[str], start: datetime, end: datetime) -> Dict[str, Any]:
    """Period flow metrics (created/completed/delayed) for a scope. user_ids=None => company."""
    q: Dict[str, Any] = {}
    if user_ids is not None:
        q = {"$or": [{"owner_id": {"$in": user_ids}}, {"assignee_id": {"$in": user_ids}}]}
    tasks = await mongo.tasks.find(q, {"_id": 0, "status": 1, "due_date": 1, "created_at": 1, "completed_at": 1, "priority": 1}).to_list(10000)
    created = completed = delayed = critical_open = open_tasks = 0
    for t in tasks:
        if in_period(t.get("created_at"), start, end):
            created += 1
        if t.get("status") == "done" and in_period(t.get("completed_at"), start, end):
            completed += 1
        if t.get("status") != "done":
            open_tasks += 1
            due = parse_dt(t.get("due_date"))
            if due and due < end:
                delayed += 1
            if t.get("priority") in ("high", "critical"):
                critical_open += 1

    mq = select(Meeting)
    if department_id:
        mq = mq.where(Meeting.department_id == department_id)
    meetings = (await session.execute(mq)).scalars().all()
    meetings_held = sum(1 for m in meetings if in_period(m.meeting_at, start, end))

    aq = select(ApprovalRequest)
    if department_id:
        aq = aq.where(ApprovalRequest.department_id == department_id)
    approvals = (await session.execute(aq)).scalars().all()
    appr_created = sum(1 for a in approvals if in_period(a.created_at, start, end))
    appr_approved = sum(1 for a in approvals if a.status == "approved" and in_period(a.decided_at, start, end))
    appr_rejected = sum(1 for a in approvals if a.status == "rejected" and in_period(a.decided_at, start, end))
    appr_pending = sum(1 for a in approvals if a.status == "pending")

    uq = select(DailyUpdate).where(
        DailyUpdate.update_date >= start.date().isoformat(), DailyUpdate.update_date <= end.date().isoformat())
    if department_id:
        uq = uq.where(DailyUpdate.department_id == department_id)
    updates = (await session.execute(uq)).scalars().all()

    return {
        "tasks": {"created": created, "completed": completed, "delayed": delayed,
                  "open": open_tasks, "critical_open": critical_open},
        "meetings_held": meetings_held,
        "approvals": {"created": appr_created, "approved": appr_approved, "rejected": appr_rejected, "pending": appr_pending},
        "daily_updates_submitted": len(updates),
        "headcount": len(user_ids) if user_ids is not None else None,
    }


async def participation(session: AsyncSession, user_ids: List[str], start: datetime, end: datetime) -> Dict[str, Any]:
    """Team participation: how many members submitted updates / had activity in the window."""
    headcount = len(user_ids)
    if not headcount:
        return {"headcount": 0, "submitted_updates": 0, "participation_rate": 0, "active_members": 0}
    rows = await mongo.activity_feed.find(
        {"actor_id": {"$in": user_ids}, "created_at": {"$gte": start.isoformat(), "$lte": end.isoformat()}},
        {"_id": 0, "actor_id": 1},
    ).to_list(10000)
    active_members = len({r["actor_id"] for r in rows})
    submitters = (await session.execute(
        select(DailyUpdate.user_id).where(
            DailyUpdate.user_id.in_(user_ids),
            DailyUpdate.update_date >= start.date().isoformat(),
            DailyUpdate.update_date <= end.date().isoformat(),
        )
    )).scalars().all()
    submitted = len(set(submitters))
    return {
        "headcount": headcount,
        "submitted_updates": submitted,
        "participation_rate": int(submitted * 100 / headcount),
        "active_members": active_members,
    }


async def store_report(session: AsyncSession, report_type: str, scope_type: str, department_id: Optional[str],
                       period_start: str, period_end: str, data: dict, summary: str, generated_by: Optional[str]):
    """Persist a report row in the shared Postgres `reports` table (the foundation store)."""
    from app.modules.reporting.models import Report
    r = Report(report_type=report_type, scope_type=scope_type, department_id=department_id,
               period_start=period_start, period_end=period_end, data=data, summary=summary or "",
               status="generated", generated_by=generated_by)
    session.add(r)
    await session.flush()
    return r


async def all_active_departments(session: AsyncSession) -> List[Department]:
    return list((await session.execute(select(Department).order_by(Department.name))).scalars().all())


async def department_metrics(session: AsyncSession, department_id: str, start: datetime, end: datetime) -> Dict[str, Any]:
    """Convenience: metrics + participation for one department over a window."""
    uids = list(await department_user_ids(session, department_id))
    m = await compute_metrics(session, uids, department_id, start, end)
    p = await participation(session, uids, start, end)
    return {"metrics": m, "participation": p, "user_ids": uids}
