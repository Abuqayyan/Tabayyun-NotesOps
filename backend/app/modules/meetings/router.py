"""Meetings + MOM + Action Items API.

Action items are the critical integration: creating one spawns a real task (Mongo) owned
by the action owner, with a reminder, and a two-way link (task.source_meeting_id ⇄
action_item.task_id). The action item's displayed status reflects its linked task so the
meeting always shows live progress.
"""
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db_mongo import db as mongo
from app.core.db_postgres import get_session
from app.core.security import get_current_user
from app.core.utils import now_iso, new_id
from app.modules.meetings.models import Meeting, MeetingAttendee, ActionItem
from app.modules.rbac.resolver import (
    get_permission_keys, user_can, ensure_permission, user_department_ids,
)
from app.modules.audit.service import record_audit
from app.shared.activity import emit_activity
from app.shared.websocket import broadcast

router = APIRouter()


# ---- Schemas ----
class MeetingIn(BaseModel):
    title: str
    department_id: Optional[str] = None
    meeting_at: Optional[str] = None
    duration_minutes: Optional[int] = 30
    agenda: Optional[str] = ""
    attendee_ids: Optional[List[str]] = []


class MeetingUpdate(BaseModel):
    title: Optional[str] = None
    department_id: Optional[str] = None
    meeting_at: Optional[str] = None
    duration_minutes: Optional[int] = None
    agenda: Optional[str] = None
    status: Optional[str] = None


class MomIn(BaseModel):
    notes: Optional[str] = None
    decisions: Optional[List[Any]] = None
    discussion_points: Optional[List[Any]] = None


class AttendeeIn(BaseModel):
    user_id: str
    attendance_status: Optional[str] = "invited"


class AttachmentIn(BaseModel):
    filename: str
    url: str


class ActionItemIn(BaseModel):
    title: str
    owner_user_id: Optional[str] = None
    due_date: Optional[str] = None
    due_in_days: Optional[int] = None  # convenience: "Due Date: 7 Days"


class ActionItemUpdate(BaseModel):
    title: Optional[str] = None
    owner_user_id: Optional[str] = None
    due_date: Optional[str] = None
    status: Optional[str] = None


# ---- Helpers ----
def _meeting_out(m: Meeting, include_mom: bool = True) -> dict:
    out = {
        "id": m.id, "title": m.title, "department_id": m.department_id, "organizer_id": m.organizer_id,
        "meeting_at": m.meeting_at, "duration_minutes": m.duration_minutes, "agenda": m.agenda,
        "attachments": m.attachments or [], "status": m.status,
        "created_by": m.created_by, "created_at": m.created_at, "updated_at": m.updated_at,
    }
    if include_mom:
        out.update({"notes": m.notes, "decisions": m.decisions or [], "discussion_points": m.discussion_points or []})
    return out


async def _enrich_users(rows: List[dict], key: str = "user_id") -> None:
    ids = list({r[key] for r in rows if r.get(key)})
    if not ids:
        return
    users = await mongo.users.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "name": 1, "email": 1}).to_list(1000)
    by_id = {u["id"]: u for u in users}
    for r in rows:
        u = by_id.get(r.get(key)) or {}
        r["user_name"] = u.get("name")
        r["user_email"] = u.get("email")


async def _load_meeting(session: AsyncSession, mid: str) -> Meeting:
    m = (await session.execute(select(Meeting).where(Meeting.id == mid))).scalar_one_or_none()
    if not m:
        raise HTTPException(404, "Meeting not found")
    return m


async def _attendee_user_ids(session: AsyncSession, mid: str) -> List[str]:
    return list((await session.execute(
        select(MeetingAttendee.user_id).where(MeetingAttendee.meeting_id == mid))).scalars().all())


async def _ensure_meeting_action(session: AsyncSession, user: dict, m: Meeting, permission: str) -> None:
    """Organizer may always act on their meeting; otherwise require the permission in scope."""
    if m.organizer_id == user["id"] or user.get("is_admin"):
        return
    await ensure_permission(session, user, permission, department_id=m.department_id)


def _normalize_dt(value: str) -> str:
    """Ensure an ISO datetime string (add a default time if only a date was given)."""
    if "T" not in value:
        value = value + "T09:00:00+00:00"
    return value


# ============ MEETINGS ============
@router.post("/meetings")
async def create_meeting(body: MeetingIn, request: Request,
                         user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    if not body.title.strip():
        raise HTTPException(400, "title required")
    await ensure_permission(session, user, "meeting.create", department_id=body.department_id)
    m = Meeting(
        title=body.title.strip(), department_id=body.department_id, organizer_id=user["id"],
        meeting_at=body.meeting_at, duration_minutes=body.duration_minutes or 30,
        agenda=body.agenda or "", decisions=[], discussion_points=[], attachments=[],
        created_by=user["id"],
    )
    session.add(m)
    await session.flush()
    for uid in dict.fromkeys(body.attendee_ids or []):
        if await mongo.users.find_one({"id": uid}, {"_id": 0, "id": 1}):
            session.add(MeetingAttendee(meeting_id=m.id, user_id=uid))
    await record_audit(session, user, "meeting.create", "meeting", m.id, after=_meeting_out(m, include_mom=False),
                       ip=request.client.host if request.client else None)
    await session.commit()
    await emit_activity(user["id"], "meeting.created", "meeting", m.id, department_id=m.department_id,
                        actor_name=user.get("name"), metadata={"title": m.title})
    return _meeting_out(m)


@router.get("/meetings")
async def list_meetings(department_id: Optional[str] = None, status: Optional[str] = None,
                        scope: Optional[str] = None, limit: int = 100,
                        user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    limit = min(max(limit, 1), 500)
    perms = await get_permission_keys(session, user)
    q = select(Meeting).order_by(Meeting.created_at.desc())

    if "meeting.view" not in perms and scope != "mine":
        # Restrict to meetings the user organizes/attends + departments where they hold scoped meeting.view.
        attended = await _attendee_user_ids_for_user(session, user["id"])
        view_depts = []
        for d in await user_department_ids(session, user["id"]):
            if await user_can(session, user, "meeting.view", department_id=d):
                view_depts.append(d)
        clauses = [Meeting.organizer_id == user["id"]]
        if attended:
            clauses.append(Meeting.id.in_(attended))
        if view_depts:
            clauses.append(Meeting.department_id.in_(view_depts))
        q = q.where(or_(*clauses))
    elif scope == "mine":
        attended = await _attendee_user_ids_for_user(session, user["id"])
        clauses = [Meeting.organizer_id == user["id"]]
        if attended:
            clauses.append(Meeting.id.in_(attended))
        q = q.where(or_(*clauses))

    if department_id:
        q = q.where(Meeting.department_id == department_id)
    if status:
        q = q.where(Meeting.status == status)
    rows = (await session.execute(q.limit(limit))).scalars().all()
    return [_meeting_out(m, include_mom=False) for m in rows]


async def _attendee_user_ids_for_user(session: AsyncSession, user_id: str) -> List[str]:
    return list((await session.execute(
        select(MeetingAttendee.meeting_id).where(MeetingAttendee.user_id == user_id))).scalars().all())


@router.get("/meetings/{mid}")
async def get_meeting(mid: str, user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    m = await _load_meeting(session, mid)
    if m.organizer_id != user["id"] and not user.get("is_admin"):
        attendees = await _attendee_user_ids(session, mid)
        if user["id"] not in attendees:
            await ensure_permission(session, user, "meeting.view", department_id=m.department_id)
    out = _meeting_out(m)
    att = [{"user_id": uid} for uid in await _attendee_user_ids(session, mid)]
    await _enrich_users(att)
    out["attendees"] = att
    out["action_items_count"] = len((await session.execute(
        select(ActionItem.id).where(ActionItem.meeting_id == mid))).scalars().all())
    return out


@router.patch("/meetings/{mid}")
async def update_meeting(mid: str, body: MeetingUpdate, request: Request,
                         user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    m = await _load_meeting(session, mid)
    await _ensure_meeting_action(session, user, m, "meeting.edit")
    before = _meeting_out(m, include_mom=False)
    for f in ("title", "department_id", "meeting_at", "duration_minutes", "agenda", "status"):
        v = getattr(body, f)
        if v is not None:
            setattr(m, f, v)
    m.updated_at = now_iso()
    await record_audit(session, user, "meeting.update", "meeting", mid, before=before, after=_meeting_out(m, include_mom=False),
                       ip=request.client.host if request.client else None)
    await session.commit()
    return _meeting_out(m)


@router.post("/meetings/{mid}/cancel")
async def cancel_meeting(mid: str, request: Request,
                         user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    m = await _load_meeting(session, mid)
    await _ensure_meeting_action(session, user, m, "meeting.cancel")
    m.status = "cancelled"
    m.updated_at = now_iso()
    await record_audit(session, user, "meeting.cancel", "meeting", mid, after={"status": "cancelled"},
                       ip=request.client.host if request.client else None)
    await session.commit()
    await emit_activity(user["id"], "meeting.cancelled", "meeting", mid, department_id=m.department_id,
                        actor_name=user.get("name"), metadata={"title": m.title})
    return _meeting_out(m, include_mom=False)


# ---- Attendees ----
@router.get("/meetings/{mid}/attendees")
async def list_attendees(mid: str, user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    m = await _load_meeting(session, mid)
    if m.organizer_id != user["id"] and not user.get("is_admin"):
        await ensure_permission(session, user, "meeting.view", department_id=m.department_id)
    rows = (await session.execute(select(MeetingAttendee).where(MeetingAttendee.meeting_id == mid))).scalars().all()
    out = [{"id": a.id, "user_id": a.user_id, "attendance_status": a.attendance_status} for a in rows]
    await _enrich_users(out)
    return out


@router.post("/meetings/{mid}/attendees")
async def add_attendee(mid: str, body: AttendeeIn, request: Request,
                       user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    m = await _load_meeting(session, mid)
    await _ensure_meeting_action(session, user, m, "meeting.edit")
    if not await mongo.users.find_one({"id": body.user_id}, {"_id": 0, "id": 1}):
        raise HTTPException(404, "user_id not found")
    dup = (await session.execute(select(MeetingAttendee).where(
        MeetingAttendee.meeting_id == mid, MeetingAttendee.user_id == body.user_id))).scalar_one_or_none()
    if dup:
        raise HTTPException(400, "Already an attendee")
    a = MeetingAttendee(meeting_id=mid, user_id=body.user_id, attendance_status=body.attendance_status or "invited")
    session.add(a)
    await session.commit()
    return {"id": a.id, "user_id": a.user_id, "attendance_status": a.attendance_status}


@router.delete("/meetings/{mid}/attendees/{uid}")
async def remove_attendee(mid: str, uid: str,
                          user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    m = await _load_meeting(session, mid)
    await _ensure_meeting_action(session, user, m, "meeting.edit")
    a = (await session.execute(select(MeetingAttendee).where(
        MeetingAttendee.meeting_id == mid, MeetingAttendee.user_id == uid))).scalar_one_or_none()
    if not a:
        raise HTTPException(404, "Attendee not found")
    await session.delete(a)
    await session.commit()
    return {"ok": True}


# ---- Attachments (metadata) ----
@router.post("/meetings/{mid}/attachments")
async def add_attachment(mid: str, body: AttachmentIn,
                         user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    m = await _load_meeting(session, mid)
    await _ensure_meeting_action(session, user, m, "meeting.edit")
    att = list(m.attachments or [])
    att.append({"id": new_id(), "filename": body.filename, "url": body.url,
                "uploaded_by": user["id"], "uploaded_at": now_iso()})
    m.attachments = att
    m.updated_at = now_iso()
    await session.commit()
    return {"attachments": att}


# ============ MOM (Module 3) ============
@router.get("/meetings/{mid}/mom")
async def get_mom(mid: str, user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    m = await _load_meeting(session, mid)
    if m.organizer_id != user["id"] and not user.get("is_admin"):
        attendees = await _attendee_user_ids(session, mid)
        if user["id"] not in attendees:
            await ensure_permission(session, user, "meeting.mom.view", department_id=m.department_id)
    return {"meeting_id": m.id, "notes": m.notes, "decisions": m.decisions or [],
            "discussion_points": m.discussion_points or []}


@router.put("/meetings/{mid}/mom")
async def edit_mom(mid: str, body: MomIn, request: Request,
                   user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    m = await _load_meeting(session, mid)
    await _ensure_meeting_action(session, user, m, "meeting.mom.edit")
    before = {"notes": m.notes, "decisions": m.decisions, "discussion_points": m.discussion_points}
    if body.notes is not None:
        m.notes = body.notes
    if body.decisions is not None:
        m.decisions = body.decisions
    if body.discussion_points is not None:
        m.discussion_points = body.discussion_points
    m.updated_at = now_iso()
    await record_audit(session, user, "meeting.mom.update", "meeting", mid, before=before,
                       after={"notes": m.notes, "decisions": m.decisions, "discussion_points": m.discussion_points},
                       ip=request.client.host if request.client else None)
    await session.commit()
    await emit_activity(user["id"], "meeting.mom_updated", "meeting", mid, department_id=m.department_id,
                        actor_name=user.get("name"), metadata={"title": m.title})
    return {"meeting_id": m.id, "notes": m.notes, "decisions": m.decisions or [],
            "discussion_points": m.discussion_points or []}


# ============ ACTION ITEMS (Module 4) ============
_TASK_TO_AI_STATUS = {"done": "done", "in_progress": "in_progress", "blocked": "in_progress", "todo": "open"}


async def _action_item_out(session: AsyncSession, ai: ActionItem) -> dict:
    out = {
        "id": ai.id, "meeting_id": ai.meeting_id, "title": ai.title,
        "owner_user_id": ai.owner_user_id, "department_id": ai.department_id,
        "due_date": ai.due_date, "status": ai.status, "task_id": ai.task_id,
        "created_at": ai.created_at, "updated_at": ai.updated_at,
    }
    # Reflect the live linked-task status so the meeting always shows real progress.
    if ai.task_id:
        t = await mongo.tasks.find_one({"id": ai.task_id}, {"_id": 0, "status": 1})
        if t:
            out["task_status"] = t.get("status")
            out["status"] = _TASK_TO_AI_STATUS.get(t.get("status"), ai.status)
    return out


@router.get("/meetings/{mid}/action-items")
async def list_action_items(mid: str, user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    m = await _load_meeting(session, mid)
    if m.organizer_id != user["id"] and not user.get("is_admin"):
        attendees = await _attendee_user_ids(session, mid)
        if user["id"] not in attendees:
            await ensure_permission(session, user, "meeting.view", department_id=m.department_id)
    rows = (await session.execute(select(ActionItem).where(ActionItem.meeting_id == mid).order_by(ActionItem.created_at))).scalars().all()
    out = [await _action_item_out(session, ai) for ai in rows]
    await _enrich_users(out, key="owner_user_id")
    return out


@router.post("/meetings/{mid}/action-items")
async def create_action_item(mid: str, body: ActionItemIn, request: Request,
                             user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    m = await _load_meeting(session, mid)
    await _ensure_meeting_action(session, user, m, "meeting.edit")
    if not body.title.strip():
        raise HTTPException(400, "title required")
    owner = body.owner_user_id or user["id"]
    if not await mongo.users.find_one({"id": owner}, {"_id": 0, "id": 1}):
        raise HTTPException(404, "owner_user_id not found")

    due = body.due_date
    if not due and body.due_in_days is not None:
        due = (datetime.now(timezone.utc) + timedelta(days=max(0, body.due_in_days))).replace(microsecond=0).isoformat()

    ai = ActionItem(meeting_id=mid, title=body.title.strip(), owner_user_id=owner,
                    department_id=m.department_id, due_date=due, status="open", created_by=user["id"])
    session.add(ai)
    await session.flush()

    # --- Spawn the linked task (Mongo execution layer) ---
    task_id = new_id()
    task_doc = {
        "id": task_id, "title": ai.title,
        "description": f"Action item from meeting: {m.title}",
        "project_id": None, "status": "todo", "priority": "medium", "complexity": "medium",
        "estimated_minutes": 30, "actual_minutes": 0,
        "start_date": None, "end_date": None, "due_date": due, "scheduled_for": None,
        "tags": ["meeting", "action-item"], "dependencies": [], "subtasks": [],
        "owner_id": owner, "assignee_id": owner, "parent_task_id": None,
        # Two-way link back to the originating meeting:
        "source_type": "meeting", "source_meeting_id": mid, "action_item_id": ai.id,
        "created_at": now_iso(), "updated_at": now_iso(), "completed_at": None,
    }
    await mongo.tasks.insert_one(task_doc)
    ai.task_id = task_id

    # --- Reminder via the existing reminder engine ---
    if due:
        await mongo.reminders.insert_one({
            "id": new_id(), "entity_type": "task", "entity_id": task_id,
            "user_id": user["id"], "recipient_ids": [owner],
            "fire_at": _normalize_dt(due), "offset_minutes": None,
            "message": f"Action item due: {ai.title}", "channel": "email",
            "enabled": True, "sent": False, "sent_at": None, "created_at": now_iso(),
            "source": "meeting_action_item",
        })

    await record_audit(session, user, "action_item.create", "action_item", ai.id,
                       after={"title": ai.title, "owner_user_id": owner, "meeting_id": mid, "task_id": task_id},
                       ip=request.client.host if request.client else None)
    await session.commit()
    await emit_activity(user["id"], "action_item.created", "action_item", ai.id, department_id=m.department_id,
                        actor_name=user.get("name"), metadata={"title": ai.title, "meeting_id": mid, "task_id": task_id})
    await emit_activity(user["id"], "task.created", "task", task_id, department_id=m.department_id,
                        actor_name=user.get("name"), metadata={"title": ai.title, "source": "meeting"})
    if owner != user["id"]:
        await broadcast(owner, "task.created", {"id": task_id})
    return await _action_item_out(session, ai)


@router.patch("/action-items/{aid}")
async def update_action_item(aid: str, body: ActionItemUpdate, request: Request,
                             user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    ai = (await session.execute(select(ActionItem).where(ActionItem.id == aid))).scalar_one_or_none()
    if not ai:
        raise HTTPException(404, "Action item not found")
    m = await _load_meeting(session, ai.meeting_id)
    # Owner of the action item may update it; otherwise require meeting.edit in scope.
    if ai.owner_user_id != user["id"]:
        await _ensure_meeting_action(session, user, m, "meeting.edit")
    before = {"title": ai.title, "owner_user_id": ai.owner_user_id, "due_date": ai.due_date, "status": ai.status}
    for f in ("title", "owner_user_id", "due_date", "status"):
        v = getattr(body, f)
        if v is not None:
            setattr(ai, f, v)
    ai.updated_at = now_iso()
    # Sync the linked task status when the action item status changes.
    if body.status is not None and ai.task_id:
        task_status = {"open": "todo", "in_progress": "in_progress", "done": "done", "cancelled": "done"}.get(body.status)
        if task_status:
            upd: Dict[str, Any] = {"status": task_status, "updated_at": now_iso()}
            if task_status == "done":
                upd["completed_at"] = now_iso()
            await mongo.tasks.update_one({"id": ai.task_id}, {"$set": upd})
    await record_audit(session, user, "action_item.update", "action_item", aid, before=before,
                       after={"title": ai.title, "status": ai.status, "owner_user_id": ai.owner_user_id},
                       ip=request.client.host if request.client else None)
    await session.commit()
    return await _action_item_out(session, ai)


@router.delete("/action-items/{aid}")
async def delete_action_item(aid: str, request: Request,
                             user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    ai = (await session.execute(select(ActionItem).where(ActionItem.id == aid))).scalar_one_or_none()
    if not ai:
        raise HTTPException(404, "Action item not found")
    m = await _load_meeting(session, ai.meeting_id)
    await _ensure_meeting_action(session, user, m, "meeting.edit")
    await session.delete(ai)
    await record_audit(session, user, "action_item.delete", "action_item", aid,
                       before={"title": ai.title, "task_id": ai.task_id},
                       ip=request.client.host if request.client else None)
    await session.commit()
    return {"ok": True}
