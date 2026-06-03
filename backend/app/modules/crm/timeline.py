"""CRM Client Activities + linking (Modules 5, 6, 7).

A unified, chronological timeline per CRM entity that merges manually-logged activities
(calls/emails/notes), linked meetings (with their AI summaries), linked/created tasks,
linked approvals, and stage history. Linking reuses the existing Meetings/Tasks/Approvals
modules untouched via the polymorphic `crm_links` table (rule 9 preserved).
"""
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db_mongo import db as mongo
from app.core.db_postgres import get_session
from app.core.security import get_current_user
from app.core.utils import now_iso, new_id
from app.modules.crm.models import (
    CRMCompany, CRMContact, CRMLead, CRMOpportunity, CRMLink, LINK_TARGET_TYPES,
)
from app.modules.crm import service as svc
from app.modules.meetings.models import Meeting
from app.modules.approvals.models import ApprovalRequest
from app.modules.rbac.resolver import ensure_permission
from app.modules.audit.service import record_audit
from app.shared.activity import emit_activity
from app.shared.websocket import broadcast

router = APIRouter()

# entity_type -> (Model, view_perm, edit_perm)
_ENTITIES = {
    "company": (CRMCompany, "crm.company.view", "crm.company.edit"),
    "contact": (CRMContact, "crm.contact.view", "crm.contact.edit"),
    "lead": (CRMLead, "crm.lead.view", "crm.lead.edit"),
    "opportunity": (CRMOpportunity, "crm.opportunity.view", "crm.opportunity.edit"),
}


class ActivityIn(BaseModel):
    activity_type: str  # call|email|note|status_change|...
    title: str
    body: Optional[str] = ""
    metadata: Optional[Dict[str, Any]] = {}


class LinkIn(BaseModel):
    target_type: str  # meeting|task|approval|note
    target_id: str


class CrmTaskIn(BaseModel):
    title: str
    description: Optional[str] = ""
    due_date: Optional[str] = None
    assignee_id: Optional[str] = None
    priority: Optional[str] = "medium"


class CrmMeetingIn(BaseModel):
    title: str
    meeting_at: Optional[str] = None
    agenda: Optional[str] = ""
    attendee_ids: Optional[list] = []


async def _load(session: AsyncSession, entity_type: str, entity_id: str):
    if entity_type not in _ENTITIES:
        raise HTTPException(400, f"Invalid entity_type. Allowed: {list(_ENTITIES)}")
    Model, view_perm, edit_perm = _ENTITIES[entity_type]
    row = (await session.execute(select(Model).where(Model.id == entity_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(404, f"{entity_type} not found")
    return row, view_perm, edit_perm


async def _ensure_view(session, user, entity_type, row, view_perm):
    if not await svc.can_view_row(session, user, view_perm, row):
        raise HTTPException(403, f"No access to this {entity_type}")


async def _ensure_edit(session, user, entity_type, row, edit_perm):
    if not await svc.can_modify(session, user, edit_perm, row):
        raise HTTPException(403, f"No edit access to this {entity_type}")


@router.get("/crm/{entity_type}/{entity_id}/timeline")
async def get_timeline(entity_type: str, entity_id: str, limit: int = 100,
                       user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    row, view_perm, _ = await _load(session, entity_type, entity_id)
    await _ensure_view(session, user, entity_type, row, view_perm)
    return await svc.build_timeline(session, entity_type, entity_id, limit=min(max(limit, 1), 500))


@router.post("/crm/{entity_type}/{entity_id}/activities")
async def log_client_activity(entity_type: str, entity_id: str, body: ActivityIn, request: Request,
                              user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    row, view_perm, _ = await _load(session, entity_type, entity_id)
    await _ensure_view(session, user, entity_type, row, view_perm)
    if not body.title.strip():
        raise HTTPException(400, "title required")
    doc = await svc.log_activity(entity_type, entity_id, body.activity_type, body.title.strip(), user,
                                 department_id=getattr(row, "department_id", None), body=body.body or "",
                                 metadata=body.metadata or {}, feed_verb=f"crm.activity.{body.activity_type}")
    await record_audit(session, user, "crm.activity.log", f"crm_{entity_type}", entity_id,
                       after={"activity_type": body.activity_type, "title": body.title},
                       ip=request.client.host if request.client else None)
    await session.commit()
    return doc


@router.post("/crm/{entity_type}/{entity_id}/link")
async def link_target(entity_type: str, entity_id: str, body: LinkIn, request: Request,
                      user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    row, _, edit_perm = await _load(session, entity_type, entity_id)
    await _ensure_edit(session, user, entity_type, row, edit_perm)
    if body.target_type not in LINK_TARGET_TYPES:
        raise HTTPException(400, f"Invalid target_type. Allowed: {LINK_TARGET_TYPES}")
    # Validate the target exists (meeting/approval in Postgres, task in Mongo).
    if body.target_type == "meeting":
        if not (await session.execute(select(Meeting).where(Meeting.id == body.target_id))).scalar_one_or_none():
            raise HTTPException(404, "meeting not found")
    elif body.target_type == "approval":
        if not (await session.execute(select(ApprovalRequest).where(ApprovalRequest.id == body.target_id))).scalar_one_or_none():
            raise HTTPException(404, "approval not found")
    elif body.target_type == "task":
        if not await mongo.tasks.find_one({"id": body.target_id}, {"_id": 0, "id": 1}):
            raise HTTPException(404, "task not found")
    dup = (await session.execute(select(CRMLink).where(
        CRMLink.crm_entity_type == entity_type, CRMLink.crm_entity_id == entity_id,
        CRMLink.target_type == body.target_type, CRMLink.target_id == body.target_id))).scalar_one_or_none()
    if dup:
        raise HTTPException(400, "Already linked")
    dept = getattr(row, "department_id", None)
    ln = CRMLink(crm_entity_type=entity_type, crm_entity_id=entity_id, target_type=body.target_type,
                 target_id=body.target_id, department_id=dept, created_by=user["id"])
    session.add(ln)
    # Mirror the link onto the Mongo task doc (schemaless — no migration needed).
    if body.target_type == "task":
        await mongo.tasks.update_one({"id": body.target_id},
                                     {"$set": {"crm_entity_type": entity_type, "crm_entity_id": entity_id}})
    await svc.log_activity(entity_type, entity_id, body.target_type, f"Linked {body.target_type}", user,
                           department_id=dept, metadata={"target_id": body.target_id},
                           feed_verb="crm.linked", emit_feed=False)
    await record_audit(session, user, "crm.link", f"crm_{entity_type}", entity_id,
                       after={"target_type": body.target_type, "target_id": body.target_id},
                       ip=request.client.host if request.client else None)
    await session.commit()
    return {"id": ln.id, "crm_entity_type": entity_type, "crm_entity_id": entity_id,
            "target_type": body.target_type, "target_id": body.target_id}


@router.delete("/crm/links/{link_id}")
async def unlink(link_id: str, user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    ln = (await session.execute(select(CRMLink).where(CRMLink.id == link_id))).scalar_one_or_none()
    if not ln:
        raise HTTPException(404, "Link not found")
    row, _, edit_perm = await _load(session, ln.crm_entity_type, ln.crm_entity_id)
    await _ensure_edit(session, user, ln.crm_entity_type, row, edit_perm)
    await session.delete(ln)
    await session.commit()
    return {"ok": True}


# ---- Module 7: create a task linked to a CRM entity ----
@router.post("/crm/{entity_type}/{entity_id}/tasks")
async def create_crm_task(entity_type: str, entity_id: str, body: CrmTaskIn, request: Request,
                          user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    row, _, edit_perm = await _load(session, entity_type, entity_id)
    await _ensure_edit(session, user, entity_type, row, edit_perm)
    if not body.title.strip():
        raise HTTPException(400, "title required")
    dept = getattr(row, "department_id", None)
    owner = body.assignee_id or getattr(row, "owner_id", None) or user["id"]
    tid = new_id()
    task_doc = {
        "id": tid, "title": body.title.strip(), "description": body.description or "",
        "project_id": None, "status": "todo", "priority": body.priority or "medium", "complexity": "medium",
        "estimated_minutes": 30, "actual_minutes": 0, "start_date": None, "end_date": None,
        "due_date": body.due_date, "scheduled_for": None, "tags": ["crm", entity_type],
        "dependencies": [], "subtasks": [], "owner_id": owner, "assignee_id": owner, "parent_task_id": None,
        "source_type": "crm", "crm_entity_type": entity_type, "crm_entity_id": entity_id,
        "created_at": now_iso(), "updated_at": now_iso(), "completed_at": None,
    }
    await mongo.tasks.insert_one(task_doc)
    session.add(CRMLink(crm_entity_type=entity_type, crm_entity_id=entity_id, target_type="task",
                        target_id=tid, department_id=dept, created_by=user["id"]))
    await svc.log_activity(entity_type, entity_id, "task", f"Task created: {body.title.strip()}", user,
                           department_id=dept, metadata={"task_id": tid}, feed_verb="crm.task.created")
    await record_audit(session, user, "crm.task.create", f"crm_{entity_type}", entity_id,
                       after={"task_id": tid}, ip=request.client.host if request.client else None)
    await session.commit()
    await emit_activity(user["id"], "task.created", "task", tid, department_id=dept,
                        actor_name=user.get("name"), metadata={"title": body.title.strip(), "source": "crm"})
    if owner != user["id"]:
        await broadcast(owner, "task.created", {"id": tid})
        from app.shared.notifications import notify
        await notify([owner], "task", f"Task assigned: {body.title.strip()}",
                     message=f"From {entity_type} record.", ref_type="task", ref_id=tid, actor_name=user.get("name"))
    return {"task_id": tid, "crm_entity_type": entity_type, "crm_entity_id": entity_id}


# ---- Module 6: create a meeting linked to a CRM entity ----
@router.post("/crm/{entity_type}/{entity_id}/meetings")
async def create_crm_meeting(entity_type: str, entity_id: str, body: CrmMeetingIn, request: Request,
                             user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    row, _, edit_perm = await _load(session, entity_type, entity_id)
    await _ensure_edit(session, user, entity_type, row, edit_perm)
    dept = getattr(row, "department_id", None)
    await ensure_permission(session, user, "meeting.create", department_id=dept)
    if not body.title.strip():
        raise HTTPException(400, "title required")
    from app.modules.meetings.models import MeetingAttendee
    m = Meeting(title=body.title.strip(), department_id=dept, organizer_id=user["id"],
                meeting_at=body.meeting_at, agenda=body.agenda or "", decisions=[], discussion_points=[],
                attachments=[], created_by=user["id"])
    session.add(m)
    await session.flush()
    for uid in dict.fromkeys(body.attendee_ids or []):
        if await mongo.users.find_one({"id": uid}, {"_id": 0, "id": 1}):
            session.add(MeetingAttendee(meeting_id=m.id, user_id=uid))
    session.add(CRMLink(crm_entity_type=entity_type, crm_entity_id=entity_id, target_type="meeting",
                        target_id=m.id, department_id=dept, created_by=user["id"]))
    await svc.log_activity(entity_type, entity_id, "meeting", f"Meeting scheduled: {m.title}", user,
                           department_id=dept, metadata={"meeting_id": m.id}, feed_verb="crm.meeting.created")
    await record_audit(session, user, "crm.meeting.create", f"crm_{entity_type}", entity_id,
                       after={"meeting_id": m.id}, ip=request.client.host if request.client else None)
    await session.commit()
    await emit_activity(user["id"], "meeting.created", "meeting", m.id, department_id=dept,
                        actor_name=user.get("name"), metadata={"title": m.title, "source": "crm"})
    return {"meeting_id": m.id, "crm_entity_type": entity_type, "crm_entity_id": entity_id}
