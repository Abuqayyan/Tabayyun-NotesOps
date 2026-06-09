"""Dashboard aggregation helpers (read-only rollups across Postgres + Mongo).

Tasks/activity live in Mongo; org/meetings/approvals/daily-updates live in Postgres.
These helpers join them by UUID at read time (the hybrid model — no cross-store FKs).
"""
from datetime import datetime, timezone, timedelta
from typing import List, Set, Dict, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db_mongo import db as mongo
from app.modules.org.models import Employee, DepartmentMember, Department
from app.modules.meetings.models import Meeting, ActionItem
from app.modules.approvals.models import ApprovalRequest
from app.modules.daily_updates.models import DailyUpdate


def _parse(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


async def department_user_ids(session: AsyncSession, department_id: str) -> Set[str]:
    out: Set[str] = set()
    emps = (await session.execute(select(Employee.user_id).where(Employee.primary_department_id == department_id))).scalars().all()
    out.update(emps)
    mems = (await session.execute(select(DepartmentMember.user_id).where(DepartmentMember.department_id == department_id))).scalars().all()
    out.update(mems)
    return out


async def task_metrics(user_ids: List[str], now: datetime) -> Dict[str, int]:
    """Aggregate task counts for the given owner/assignee set (empty list -> company-wide)."""
    q: Dict[str, Any] = {}
    if user_ids is not None:
        q = {"$or": [{"owner_id": {"$in": user_ids}}, {"assignee_id": {"$in": user_ids}}]}
    tasks = await mongo.tasks.find(q, {"_id": 0, "status": 1, "due_date": 1, "priority": 1}).to_list(5000)
    m = {"total": len(tasks), "open": 0, "completed": 0, "in_progress": 0, "blocked": 0, "delayed": 0, "critical": 0}
    for t in tasks:
        st = t.get("status")
        if st == "done":
            m["completed"] += 1
        else:
            m["open"] += 1
            if st == "in_progress":
                m["in_progress"] += 1
            elif st == "blocked":
                m["blocked"] += 1
            due = _parse(t.get("due_date"))
            if due and due < now:
                m["delayed"] += 1
            if t.get("priority") in ("high", "critical"):
                m["critical"] += 1
    return m


async def department_dashboard(session: AsyncSession, department_id: str) -> dict:
    now = datetime.now(timezone.utc)
    dept = (await session.execute(select(Department).where(Department.id == department_id))).scalar_one_or_none()
    if not dept:
        return {}
    user_ids = list(await department_user_ids(session, department_id))
    tasks = await task_metrics(user_ids, now)  # empty set -> $in:[] -> all-zero metrics

    meetings = (await session.execute(select(Meeting).where(Meeting.department_id == department_id))).scalars().all()
    upcoming_meetings = [m for m in meetings if m.status == "scheduled" and (_parse(m.meeting_at) or now) >= now]
    pending_approvals = (await session.execute(select(ApprovalRequest).where(
        ApprovalRequest.department_id == department_id, ApprovalRequest.status == "pending"))).scalars().all()
    today = now.date().isoformat()
    updates_today = (await session.execute(select(DailyUpdate).where(
        DailyUpdate.department_id == department_id, DailyUpdate.update_date == today))).scalars().all()
    open_action_items = (await session.execute(select(ActionItem).where(
        ActionItem.department_id == department_id, ActionItem.status.in_(["open", "in_progress"])))).scalars().all()

    activity = await mongo.activity_feed.find(
        {"department_id": department_id}, {"_id": 0}).sort("created_at", -1).to_list(15)

    return {
        "department": {"id": dept.id, "name": dept.name, "lead_user_id": dept.lead_user_id},
        "headcount": len(user_ids),
        "tasks": tasks,
        "meetings_total": len(meetings),
        "meetings_upcoming": len(upcoming_meetings),
        "pending_approvals": len(pending_approvals),
        "open_action_items": len(open_action_items),
        "updates_today": len(updates_today),
        "activity": activity,
    }
