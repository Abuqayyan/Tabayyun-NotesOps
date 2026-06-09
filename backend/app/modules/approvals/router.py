"""Approval Workflows API: templates (configurable steps) + request lifecycle.

Lifecycle: submit -> engine instantiates step chain & activates step 1 -> assigned
approver decides (approve advances to the next step / rejects ends it) -> final approval.
Every decision is audited, emits an activity event, and notifies the next approver via the
reminder engine. SLA escalation of overdue approvals is handled by the escalation engine.
"""
from typing import List, Optional, Any, Dict

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db_mongo import db as mongo
from app.core.db_postgres import get_session
from app.core.security import get_current_user
from app.core.utils import now_iso, new_id
from app.modules.approvals.models import (
    ApprovalTemplate, ApprovalTemplateStep, ApprovalRequest, ApprovalStep,
    APPROVER_TYPES, STATUS_PENDING, STATUS_CANCELLED,
)
from app.modules.approvals import service as engine
from app.modules.rbac.resolver import get_permission_keys, user_can, ensure_permission, require_permission
from app.modules.audit.service import record_audit
from app.shared.activity import emit_activity
from app.shared.websocket import broadcast
from app.shared.notifications import notify

router = APIRouter()


# ---- Schemas ----
class StepIn(BaseModel):
    name: Optional[str] = ""
    approver_type: str
    approver_value: Optional[str] = None
    step_order: Optional[int] = None


class TemplateIn(BaseModel):
    key: str
    name: str
    description: Optional[str] = ""
    category: Optional[str] = "generic"
    is_active: Optional[bool] = True
    steps: List[StepIn] = []


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    is_active: Optional[bool] = None
    steps: Optional[List[StepIn]] = None


class RequestIn(BaseModel):
    template_id: str
    title: Optional[str] = ""
    department_id: Optional[str] = None
    form_data: Optional[Dict[str, Any]] = {}


class DecisionIn(BaseModel):
    decision: str  # approve|reject
    comment: Optional[str] = None


# ---- Serializers ----
def _template_out(t: ApprovalTemplate, steps: List[ApprovalTemplateStep]) -> dict:
    return {
        "id": t.id, "key": t.key, "name": t.name, "description": t.description,
        "category": t.category, "is_active": t.is_active,
        "created_at": t.created_at, "updated_at": t.updated_at,
        "steps": [{"id": s.id, "step_order": s.step_order, "name": s.name,
                   "approver_type": s.approver_type, "approver_value": s.approver_value} for s in steps],
    }


def _step_out(s: ApprovalStep) -> dict:
    return {"id": s.id, "step_order": s.step_order, "name": s.name, "approver_type": s.approver_type,
            "approver_value": s.approver_value, "approver_user_id": s.approver_user_id,
            "status": s.status, "comment": s.comment, "decided_by": s.decided_by, "decided_at": s.decided_at}


def _request_out(r: ApprovalRequest, steps: List[ApprovalStep] = None) -> dict:
    out = {"id": r.id, "template_id": r.template_id, "requester_id": r.requester_id,
           "department_id": r.department_id, "title": r.title, "status": r.status,
           "current_step": r.current_step, "form_data": r.form_data or {},
           "created_at": r.created_at, "updated_at": r.updated_at, "decided_at": r.decided_at}
    if steps is not None:
        out["steps"] = [_step_out(s) for s in sorted(steps, key=lambda x: x.step_order)]
    return out


async def _notify_approver(request_obj: ApprovalRequest, step: ApprovalStep, session: AsyncSession) -> None:
    """Enqueue an immediate reminder to the step's approver(s) via the reminder engine."""
    recipients: List[str] = []
    if step.approver_user_id:
        recipients = [step.approver_user_id]
    elif step.approver_type == "role" and step.approver_value:
        recipients = list(await engine._users_with_role(session, step.approver_value, request_obj.department_id))
    if not recipients:
        return
    await mongo.reminders.insert_one({
        "id": new_id(), "entity_type": "approval", "entity_id": request_obj.id,
        "user_id": request_obj.requester_id, "recipient_ids": recipients,
        "fire_at": now_iso(), "offset_minutes": None,
        "message": f"Approval needed: {request_obj.title}", "channel": "email",
        "enabled": True, "sent": False, "sent_at": None, "created_at": now_iso(), "source": "approval",
    })
    for uid in recipients:
        await broadcast(uid, "approval.assigned", {"request_id": request_obj.id, "title": request_obj.title})
    await notify(recipients, "approval", f"Approval needed: {request_obj.title}",
                 message="A request is awaiting your decision.", ref_type="approval", ref_id=request_obj.id)


# ============ TEMPLATES ============
@router.post("/approvals/templates")
async def create_template(body: TemplateIn, request: Request,
                          user=Depends(require_permission("approval.manage")), session: AsyncSession = Depends(get_session)):
    if not body.steps:
        raise HTTPException(400, "A template needs at least one step")
    for s in body.steps:
        if s.approver_type not in APPROVER_TYPES:
            raise HTTPException(400, f"Invalid approver_type: {s.approver_type}")
    dup = (await session.execute(select(ApprovalTemplate).where(ApprovalTemplate.key == body.key))).scalar_one_or_none()
    if dup:
        raise HTTPException(400, "Template key already exists")
    t = ApprovalTemplate(key=body.key.strip(), name=body.name.strip(), description=body.description or "",
                         category=body.category or "generic", is_active=bool(body.is_active), created_by=user["id"])
    session.add(t)
    await session.flush()
    steps = []
    for i, s in enumerate(body.steps):
        ts = ApprovalTemplateStep(template_id=t.id, step_order=s.step_order or (i + 1),
                                  name=s.name or "", approver_type=s.approver_type, approver_value=s.approver_value)
        session.add(ts)
        steps.append(ts)
    await record_audit(session, user, "approval_template.create", "approval_template", t.id,
                       after={"key": t.key, "steps": len(steps)}, ip=request.client.host if request.client else None)
    await session.commit()
    return _template_out(t, steps)


@router.get("/approvals/templates")
async def list_templates(user=Depends(require_permission("approval.view")), session: AsyncSession = Depends(get_session)):
    tpls = (await session.execute(select(ApprovalTemplate).order_by(ApprovalTemplate.name))).scalars().all()
    out = []
    for t in tpls:
        steps = (await session.execute(select(ApprovalTemplateStep).where(
            ApprovalTemplateStep.template_id == t.id).order_by(ApprovalTemplateStep.step_order))).scalars().all()
        out.append(_template_out(t, steps))
    return out


@router.get("/approvals/templates/{tid}")
async def get_template(tid: str, user=Depends(require_permission("approval.view")), session: AsyncSession = Depends(get_session)):
    t = (await session.execute(select(ApprovalTemplate).where(ApprovalTemplate.id == tid))).scalar_one_or_none()
    if not t:
        raise HTTPException(404, "Template not found")
    steps = (await session.execute(select(ApprovalTemplateStep).where(
        ApprovalTemplateStep.template_id == tid).order_by(ApprovalTemplateStep.step_order))).scalars().all()
    return _template_out(t, steps)


@router.patch("/approvals/templates/{tid}")
async def update_template(tid: str, body: TemplateUpdate, request: Request,
                          user=Depends(require_permission("approval.manage")), session: AsyncSession = Depends(get_session)):
    t = (await session.execute(select(ApprovalTemplate).where(ApprovalTemplate.id == tid))).scalar_one_or_none()
    if not t:
        raise HTTPException(404, "Template not found")
    for f in ("name", "description", "category", "is_active"):
        v = getattr(body, f)
        if v is not None:
            setattr(t, f, v)
    t.updated_at = now_iso()
    if body.steps is not None:
        for old in (await session.execute(select(ApprovalTemplateStep).where(ApprovalTemplateStep.template_id == tid))).scalars().all():
            await session.delete(old)
        await session.flush()
        for i, s in enumerate(body.steps):
            if s.approver_type not in APPROVER_TYPES:
                raise HTTPException(400, f"Invalid approver_type: {s.approver_type}")
            session.add(ApprovalTemplateStep(template_id=tid, step_order=s.step_order or (i + 1),
                                             name=s.name or "", approver_type=s.approver_type, approver_value=s.approver_value))
    await record_audit(session, user, "approval_template.update", "approval_template", tid,
                       ip=request.client.host if request.client else None)
    await session.commit()
    steps = (await session.execute(select(ApprovalTemplateStep).where(
        ApprovalTemplateStep.template_id == tid).order_by(ApprovalTemplateStep.step_order))).scalars().all()
    return _template_out(t, steps)


@router.delete("/approvals/templates/{tid}")
async def delete_template(tid: str, request: Request,
                          user=Depends(require_permission("approval.manage")), session: AsyncSession = Depends(get_session)):
    t = (await session.execute(select(ApprovalTemplate).where(ApprovalTemplate.id == tid))).scalar_one_or_none()
    if not t:
        raise HTTPException(404, "Template not found")
    for old in (await session.execute(select(ApprovalTemplateStep).where(ApprovalTemplateStep.template_id == tid))).scalars().all():
        await session.delete(old)
    await session.delete(t)
    await record_audit(session, user, "approval_template.delete", "approval_template", tid,
                       before={"key": t.key}, ip=request.client.host if request.client else None)
    await session.commit()
    return {"ok": True}


# ============ REQUESTS ============
@router.post("/approvals/requests")
async def create_request(body: RequestIn, request: Request,
                         user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    await ensure_permission(session, user, "approval.create", department_id=body.department_id)
    t = (await session.execute(select(ApprovalTemplate).where(ApprovalTemplate.id == body.template_id))).scalar_one_or_none()
    if not t or not t.is_active:
        raise HTTPException(404, "Active template not found")
    try:
        req, steps = await engine.instantiate_request(
            session, t, user["id"], body.department_id, body.title or t.name, body.form_data or {})
    except ValueError as e:
        raise HTTPException(400, str(e))
    await record_audit(session, user, "approval.submit", "approval_request", req.id,
                       after={"template": t.key, "title": req.title}, ip=request.client.host if request.client else None)
    await session.commit()
    await emit_activity(user["id"], "approval.submitted", "approval_request", req.id, department_id=req.department_id,
                        actor_name=user.get("name"), metadata={"title": req.title, "template": t.key})
    first = await engine.active_step(session, req)
    if first:
        await _notify_approver(req, first, session)
    all_steps = (await session.execute(select(ApprovalStep).where(ApprovalStep.request_id == req.id))).scalars().all()
    return _request_out(req, all_steps)


@router.get("/approvals/requests")
async def list_requests(status: Optional[str] = None, mine: Optional[str] = None, limit: int = 100,
                        user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    limit = min(max(limit, 1), 500)
    perms = await get_permission_keys(session, user)
    rows = (await session.execute(select(ApprovalRequest).order_by(ApprovalRequest.created_at.desc()).limit(500))).scalars().all()

    # Precompute the active step per request for approver visibility / to_approve filter.
    out = []
    for r in rows:
        if status and r.status != status:
            continue
        is_requester = r.requester_id == user["id"]
        active = await engine.active_step(session, r) if r.status == STATUS_PENDING else None
        can_decide = bool(active) and await engine.can_user_decide(session, user, active, r)
        broad = ("approval.view" in perms) or await user_can(session, user, "approval.view", department_id=r.department_id)
        visible = is_requester or can_decide or broad
        if not visible:
            continue
        if mine == "requested" and not is_requester:
            continue
        if mine == "to_approve" and not can_decide:
            continue
        item = _request_out(r)
        item["can_decide"] = can_decide
        item["active_step"] = _step_out(active) if active else None
        out.append(item)
        if len(out) >= limit:
            break
    return out


@router.get("/approvals/requests/{rid}")
async def get_request(rid: str, user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    r = (await session.execute(select(ApprovalRequest).where(ApprovalRequest.id == rid))).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "Request not found")
    steps = (await session.execute(select(ApprovalStep).where(ApprovalStep.request_id == rid))).scalars().all()
    active = next((s for s in steps if s.step_order == r.current_step and r.status == STATUS_PENDING), None)
    can_decide = bool(active) and await engine.can_user_decide(session, user, active, r)
    if r.requester_id != user["id"] and not can_decide:
        if not await user_can(session, user, "approval.view", department_id=r.department_id):
            raise HTTPException(403, "No access to this request")
    out = _request_out(r, steps)
    out["can_decide"] = can_decide
    return out


@router.post("/approvals/requests/{rid}/decision")
async def decide(rid: str, body: DecisionIn, request: Request,
                 user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    if body.decision not in ("approve", "reject"):
        raise HTTPException(400, "decision must be 'approve' or 'reject'")
    r = (await session.execute(select(ApprovalRequest).where(ApprovalRequest.id == rid))).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "Request not found")
    if r.status != STATUS_PENDING:
        raise HTTPException(400, f"Request is already {r.status}")
    step = await engine.active_step(session, r)
    if not step:
        raise HTTPException(400, "No active step")
    allowed = await engine.can_user_decide(session, user, step, r)
    if not allowed and not await user_can(session, user, "approval.manage", department_id=r.department_id):
        raise HTTPException(403, "You are not the approver for the current step")

    step.status = "approved" if body.decision == "approve" else "rejected"
    step.comment = body.comment
    step.decided_by = user["id"]
    step.decided_at = now_iso()

    next_step = None
    if body.decision == "approve":
        next_step = await engine.advance_after_approval(session, r)
    else:
        r.status = "rejected"
        r.decided_at = now_iso()
        r.updated_at = now_iso()

    await record_audit(session, user, f"approval.{body.decision}", "approval_request", rid,
                       before={"step": step.step_order, "current_status": "pending"},
                       after={"decision": body.decision, "comment": body.comment, "result_status": r.status},
                       ip=request.client.host if request.client else None)
    await session.commit()

    await emit_activity(user["id"], f"approval.{body.decision}d" if body.decision == "approve" else "approval.rejected",
                        "approval_request", rid, department_id=r.department_id, actor_name=user.get("name"),
                        metadata={"title": r.title, "step": step.step_order, "result": r.status})
    # Notify next approver, or close the loop back to the requester.
    if next_step:
        await _notify_approver(r, next_step, session)
    else:
        await broadcast(r.requester_id, "approval.decided", {"request_id": rid, "status": r.status})
    steps = (await session.execute(select(ApprovalStep).where(ApprovalStep.request_id == rid))).scalars().all()
    return _request_out(r, steps)


@router.post("/approvals/requests/{rid}/cancel")
async def cancel_request(rid: str, request: Request,
                         user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    r = (await session.execute(select(ApprovalRequest).where(ApprovalRequest.id == rid))).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "Request not found")
    if r.requester_id != user["id"] and not await user_can(session, user, "approval.manage", department_id=r.department_id):
        raise HTTPException(403, "Only the requester or an approval manager can cancel")
    if r.status != STATUS_PENDING:
        raise HTTPException(400, f"Request is already {r.status}")
    r.status = STATUS_CANCELLED
    r.decided_at = now_iso()
    r.updated_at = now_iso()
    await record_audit(session, user, "approval.cancel", "approval_request", rid,
                       ip=request.client.host if request.client else None)
    await session.commit()
    await emit_activity(user["id"], "approval.cancelled", "approval_request", rid, department_id=r.department_id,
                        actor_name=user.get("name"), metadata={"title": r.title})
    return _request_out(r)
