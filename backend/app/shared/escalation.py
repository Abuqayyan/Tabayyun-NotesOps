"""Escalation engine — overdue work climbs the reporting chain.

Overdue tasks (incl. meeting action-item tasks) and overdue approval steps are escalated
in levels: L1 owner/approver → L2 their manager → L3 skip-level / department lead. It
INTEGRATES WITH THE EXISTING REMINDER ENGINE: each new level enqueues a `db.reminders`
document that the normal scheduler loop then delivers, so there is one delivery path.
A `db.escalations` record tracks the level reached per entity so we notify once per level
(no minute-by-minute spam). Designed to be called from the reminder loop AND unit-tested
directly by passing an explicit `now`.
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional

from app.core.db_mongo import db
from app.core.utils import new_id, now_iso
from app.core.db_postgres import session_scope, get_engine
from app.shared.activity import emit_activity

log = logging.getLogger("opscore.escalation")

ESCALATION_L2_HOURS = 24    # overdue this long -> notify the manager
ESCALATION_L3_HOURS = 72    # overdue this long -> notify skip-level / department lead
APPROVAL_SLA_HOURS = 24     # a pending approval step idle this long -> start escalating


def _parse(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _desired_level(hours_over: float, l2: float, l3: float) -> int:
    if hours_over >= l3:
        return 3
    if hours_over >= l2:
        return 2
    if hours_over >= 0:
        return 1
    return 0


async def _enqueue(entity_type: str, entity_id: str, recipients: List[str], message: str) -> None:
    recipients = [r for r in dict.fromkeys(recipients) if r]
    if not recipients:
        return
    await db.reminders.insert_one({
        "id": new_id(), "entity_type": entity_type, "entity_id": entity_id,
        "user_id": None, "recipient_ids": recipients, "fire_at": now_iso(), "offset_minutes": None,
        "message": message, "channel": "email", "enabled": True, "sent": False, "sent_at": None,
        "created_at": now_iso(), "source": "escalation",
    })
    # In-app notification (best-effort) in addition to the queued email.
    try:
        from app.shared.notifications import notify
        await notify(recipients, "escalation", message, ref_type=entity_type, ref_id=entity_id)
    except Exception:  # noqa: BLE001
        pass


async def _current_level(entity_type: str, entity_id: str) -> int:
    rec = await db.escalations.find_one({"entity_type": entity_type, "entity_id": entity_id}, {"_id": 0})
    return (rec or {}).get("level", 0)


async def _save_level(entity_type: str, entity_id: str, level: int) -> None:
    await db.escalations.update_one(
        {"entity_type": entity_type, "entity_id": entity_id},
        {"$set": {"level": level, "last_notified_at": now_iso()},
         "$setOnInsert": {"id": new_id(), "entity_type": entity_type, "entity_id": entity_id, "created_at": now_iso()}},
        upsert=True,
    )


async def _manager_chain(session, user_id: str):
    """(direct_manager_user_id, skip_level_user_id) for a user, via employees.manager_id."""
    from app.modules.approvals.service import _manager_user_id
    return await _manager_user_id(session, user_id, 1), await _manager_user_id(session, user_id, 2)


async def _dept_lead(session, department_id: Optional[str]) -> Optional[str]:
    if not department_id:
        return None
    from sqlalchemy import select
    from app.modules.org.models import Department
    d = (await session.execute(select(Department).where(Department.id == department_id))).scalar_one_or_none()
    return d.lead_user_id if d else None


async def _escalate_tasks(session, now: datetime) -> int:
    overdue = await db.tasks.find(
        {"status": {"$ne": "done"}, "due_date": {"$ne": None}},
        {"_id": 0, "id": 1, "title": 1, "owner_id": 1, "assignee_id": 1, "due_date": 1, "source_meeting_id": 1},
    ).to_list(5000)
    count = 0
    for t in overdue:
        due = _parse(t.get("due_date"))
        if not due:
            continue
        hours = (now - due).total_seconds() / 3600.0
        desired = _desired_level(hours, ESCALATION_L2_HOURS, ESCALATION_L3_HOURS)
        if desired <= 0:
            continue
        current = await _current_level("task", t["id"])
        if desired <= current:
            continue
        responsible = t.get("assignee_id") or t.get("owner_id")
        mgr, skip = await _manager_chain(session, responsible) if responsible else (None, None)
        title = t.get("title", "task")
        for lvl in range(current + 1, desired + 1):
            if lvl == 1:
                await _enqueue("task", t["id"], [t.get("owner_id"), t.get("assignee_id")], f"Overdue task: {title}")
            elif lvl == 2 and mgr:
                await _enqueue("task", t["id"], [mgr], f"Escalation — overdue task (your report): {title}")
            elif lvl == 3:
                await _enqueue("task", t["id"], [skip], f"Escalation L3 — still overdue: {title}")
            await emit_activity("system", "task.escalated", "task", t["id"],
                                metadata={"level": lvl, "title": title, "hours_overdue": round(hours, 1)})
        await _save_level("task", t["id"], desired)
        count += 1
    return count


async def _escalate_approvals(session, now: datetime) -> int:
    from sqlalchemy import select
    from app.modules.approvals.models import ApprovalRequest, ApprovalStep, STATUS_PENDING
    pending = (await session.execute(select(ApprovalRequest).where(ApprovalRequest.status == STATUS_PENDING))).scalars().all()
    count = 0
    for r in pending:
        step = (await session.execute(select(ApprovalStep).where(
            ApprovalStep.request_id == r.id, ApprovalStep.step_order == r.current_step))).scalar_one_or_none()
        if not step:
            continue
        activated = _parse(step.activated_at)
        if not activated:
            continue
        hours = (now - activated).total_seconds() / 3600.0
        desired = _desired_level(hours, APPROVAL_SLA_HOURS, APPROVAL_SLA_HOURS * 2)
        if desired <= 0:
            continue
        current = await _current_level("approval", r.id)
        if desired <= current:
            continue
        approver = step.approver_user_id
        mgr, skip = await _manager_chain(session, approver) if approver else (None, None)
        lead = await _dept_lead(session, r.department_id)
        for lvl in range(current + 1, desired + 1):
            if lvl == 1 and approver:
                await _enqueue("approval", r.id, [approver], f"Approval overdue: {r.title}")
            elif lvl == 2:
                await _enqueue("approval", r.id, [mgr or lead], f"Escalation — approval awaiting decision: {r.title}")
            elif lvl == 3:
                await _enqueue("approval", r.id, [skip or lead], f"Escalation L3 — approval still pending: {r.title}")
            await emit_activity("system", "approval.escalated", "approval_request", r.id,
                                department_id=r.department_id, metadata={"level": lvl, "title": r.title})
        await _save_level("approval", r.id, desired)
        count += 1
    return count


async def run_escalations(now: Optional[datetime] = None) -> dict:
    """Scan overdue tasks + approvals and escalate any that crossed a new level."""
    now = now or datetime.now(timezone.utc)
    tasks_escalated = approvals_escalated = 0
    if get_engine() is None:
        # No relational store -> only tasks have an owner chain we can't resolve; skip cleanly.
        return {"tasks": 0, "approvals": 0, "skipped": "no_postgres"}
    try:
        async with session_scope() as session:
            tasks_escalated = await _escalate_tasks(session, now)
            approvals_escalated = await _escalate_approvals(session, now)
    except Exception as e:  # noqa: BLE001 - escalation must never crash the scheduler
        log.warning(f"Escalation run error: {e}")
    return {"tasks": tasks_escalated, "approvals": approvals_escalated}
