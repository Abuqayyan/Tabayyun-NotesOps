"""Department + CEO Executive dashboard endpoints (permission-gated, scope-aware)."""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db_mongo import db as mongo
from app.core.db_postgres import get_session
from app.core.security import get_current_user
from app.modules.org.models import Department
from app.modules.meetings.models import Meeting
from app.modules.approvals.models import ApprovalRequest
from app.modules.daily_updates.models import DailyUpdate
from app.modules.rbac.resolver import require_permission, ensure_permission
from app.modules.dashboards.service import department_dashboard, task_metrics, department_user_ids, _parse

router = APIRouter()


@router.get("/departments/{did}/dashboard")
async def get_department_dashboard(did: str, user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    dept = (await session.execute(select(Department).where(Department.id == did))).scalar_one_or_none()
    if not dept:
        raise HTTPException(404, "Department not found")
    # Department-scoped permission: a manager assigned to THIS department passes; so does a
    # global holder / admin. A manager of another department does not.
    await ensure_permission(session, user, "department.dashboard.view", department_id=did)
    return await department_dashboard(session, did)


@router.get("/executive/dashboard")
async def executive_dashboard(user=Depends(require_permission("company.dashboard.view")),
                              session: AsyncSession = Depends(get_session)):
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()

    company_tasks = await task_metrics(None, now)  # None -> company-wide

    # Per-department health (comparison).
    depts = (await session.execute(select(Department).where(Department.is_active == True).order_by(Department.name))).scalars().all()  # noqa: E712
    dept_health = []
    for d in depts:
        uids = list(await department_user_ids(session, d.id))
        tm = await task_metrics(uids, now)
        pending = len((await session.execute(select(ApprovalRequest.id).where(
            ApprovalRequest.department_id == d.id, ApprovalRequest.status == "pending"))).scalars().all())
        updates = len((await session.execute(select(DailyUpdate.id).where(
            DailyUpdate.department_id == d.id, DailyUpdate.update_date == today))).scalars().all())
        completion = int(tm["completed"] * 100 / tm["total"]) if tm["total"] else 0
        dept_health.append({
            "id": d.id, "name": d.name, "headcount": len(uids),
            "open_tasks": tm["open"], "completed_tasks": tm["completed"], "delayed_tasks": tm["delayed"],
            "critical_tasks": tm["critical"], "pending_approvals": pending, "updates_today": updates,
            "completion_rate": completion,
        })

    # Upcoming meetings (company-wide).
    meetings = (await session.execute(select(Meeting).where(Meeting.status == "scheduled"))).scalars().all()
    upcoming = sorted(
        [m for m in meetings if (_parse(m.meeting_at) or now) >= now],
        key=lambda m: _parse(m.meeting_at) or now,
    )[:10]
    upcoming_meetings = [{"id": m.id, "title": m.title, "department_id": m.department_id,
                          "meeting_at": m.meeting_at, "organizer_id": m.organizer_id} for m in upcoming]

    # Pending approvals (company-wide), oldest first (most at-risk).
    pend = (await session.execute(select(ApprovalRequest).where(
        ApprovalRequest.status == "pending").order_by(ApprovalRequest.created_at))).scalars().all()
    pending_approvals = [{"id": r.id, "title": r.title, "requester_id": r.requester_id,
                          "department_id": r.department_id, "current_step": r.current_step,
                          "created_at": r.created_at} for r in pend[:15]]

    # Risks / blocked work — critical or delayed open tasks across the company.
    risk_tasks = await mongo.tasks.find(
        {"status": {"$ne": "done"}}, {"_id": 0, "id": 1, "title": 1, "status": 1, "priority": 1, "due_date": 1, "owner_id": 1}
    ).to_list(5000)
    risks = []
    for t in risk_tasks:
        due = _parse(t.get("due_date"))
        overdue = bool(due and due < now)
        if overdue or t.get("priority") in ("high", "critical") or t.get("status") == "blocked":
            risks.append({**t, "overdue": overdue})
    risks.sort(key=lambda x: (not x["overdue"], x.get("priority") != "critical"))

    # Recent company activity + employee activity snapshot.
    recent_activity = await mongo.activity_feed.find({}, {"_id": 0}).sort("created_at", -1).to_list(20)
    updates_today_total = len((await session.execute(select(DailyUpdate.id).where(
        DailyUpdate.update_date == today))).scalars().all())

    return {
        "generated_at": now.isoformat(),
        "company_health": {
            **company_tasks,
            "completion_rate": int(company_tasks["completed"] * 100 / company_tasks["total"]) if company_tasks["total"] else 0,
            "departments": len(depts),
            "upcoming_meetings": len(upcoming_meetings),
            "pending_approvals": len(pend),
            "updates_today": updates_today_total,
        },
        "department_performance": dept_health,
        "upcoming_meetings": upcoming_meetings,
        "pending_approvals": pending_approvals,
        "risks": risks[:20],
        "blocked_work": [r for r in risks if r.get("status") == "blocked"][:10],
        "recent_activity": recent_activity,
    }
