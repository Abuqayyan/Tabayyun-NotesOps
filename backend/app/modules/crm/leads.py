"""CRM Leads API (Module 3): stages, stage history, activity tracking, conversion to deals."""
import re
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db_mongo import db as mongo
from app.core.db_postgres import get_session
from app.core.security import get_current_user
from app.core.utils import now_iso
from app.modules.crm.models import CRMLead, CRMLeadStageHistory, CRMOpportunity, CRMOppStageHistory, CRMLink, LEAD_STAGES
from app.modules.crm import service as svc
from app.modules.rbac.resolver import ensure_permission
from app.modules.audit.service import record_audit

router = APIRouter()


def _status_for_stage(stage: str) -> str:
    return "won" if stage == "won" else "lost" if stage == "lost" else "open"


class LeadIn(BaseModel):
    title: Optional[str] = ""
    source: Optional[str] = ""
    value: Optional[float] = 0.0
    probability: Optional[int] = 0
    stage: Optional[str] = "new"
    owner_id: Optional[str] = None
    department_id: Optional[str] = None
    company_id: Optional[str] = None
    contact_id: Optional[str] = None
    notes: Optional[str] = ""


class LeadUpdate(BaseModel):
    title: Optional[str] = None
    source: Optional[str] = None
    value: Optional[float] = None
    probability: Optional[int] = None
    stage: Optional[str] = None
    owner_id: Optional[str] = None
    department_id: Optional[str] = None
    company_id: Optional[str] = None
    contact_id: Optional[str] = None
    notes: Optional[str] = None
    stage_note: Optional[str] = None


class ConvertIn(BaseModel):
    name: Optional[str] = None
    expected_revenue: Optional[float] = None
    expected_close_date: Optional[str] = None
    stage: Optional[str] = "qualification"


def _out(l: CRMLead) -> dict:
    return {"id": l.id, "title": l.title, "source": l.source, "value": l.value, "probability": l.probability,
            "stage": l.stage, "status": l.status, "owner_id": l.owner_id, "department_id": l.department_id,
            "company_id": l.company_id, "contact_id": l.contact_id, "notes": l.notes,
            "converted_opportunity_id": l.converted_opportunity_id,
            "created_by": l.created_by, "created_at": l.created_at, "updated_at": l.updated_at}


@router.post("/crm/leads")
async def create_lead(body: LeadIn, request: Request,
                      user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    stage = body.stage or "new"
    if stage not in LEAD_STAGES:
        raise HTTPException(400, f"Invalid stage. Allowed: {LEAD_STAGES}")
    await ensure_permission(session, user, "crm.lead.create", department_id=body.department_id)
    l = CRMLead(title=body.title or "", source=body.source or "", value=body.value or 0.0,
                probability=body.probability or 0, stage=stage, status=_status_for_stage(stage),
                owner_id=body.owner_id or user["id"], department_id=body.department_id,
                company_id=body.company_id, contact_id=body.contact_id, notes=body.notes or "", created_by=user["id"])
    session.add(l)
    await session.flush()
    session.add(CRMLeadStageHistory(lead_id=l.id, from_stage=None, to_stage=stage, changed_by=user["id"]))
    await record_audit(session, user, "crm.lead.create", "crm_lead", l.id,
                       after={"title": l.title, "stage": stage, "value": l.value},
                       ip=request.client.host if request.client else None)
    await session.commit()
    await svc.log_activity("lead", l.id, "created", f"Lead created ({stage})", user,
                           department_id=l.department_id, feed_verb="crm.lead.created", metadata={"stage": stage})
    return _out(l)


@router.get("/crm/leads")
async def list_leads(q: Optional[str] = None, stage: Optional[str] = None, status: Optional[str] = None,
                     company_id: Optional[str] = None, owner_id: Optional[str] = None,
                     department_id: Optional[str] = None, limit: int = 200,
                     user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    limit = min(max(limit, 1), 1000)
    await ensure_permission(session, user, "crm.lead.view")
    can_all, dept_ids = await svc.view_scope(session, user, "crm.lead.view")
    query = select(CRMLead).order_by(CRMLead.updated_at.desc())
    vf = svc.visibility_filter(CRMLead, can_all, dept_ids, user["id"])
    if vf is not None:
        query = query.where(vf)
    if stage:
        query = query.where(CRMLead.stage == stage)
    if status:
        query = query.where(CRMLead.status == status)
    if company_id:
        query = query.where(CRMLead.company_id == company_id)
    if owner_id:
        query = query.where(CRMLead.owner_id == owner_id)
    if department_id:
        query = query.where(CRMLead.department_id == department_id)
    rows = (await session.execute(query.limit(limit))).scalars().all()
    out = [_out(l) for l in rows]
    if q:
        rx = re.compile(re.escape(q), re.IGNORECASE)
        out = [l for l in out if rx.search(l["title"] or "") or rx.search(l["source"] or "")]
    await svc.enrich_users(out)
    return out


@router.get("/crm/leads/{lid}")
async def get_lead(lid: str, user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    l = (await session.execute(select(CRMLead).where(CRMLead.id == lid))).scalar_one_or_none()
    if not l:
        raise HTTPException(404, "Lead not found")
    if not await svc.can_view_row(session, user, "crm.lead.view", l):
        raise HTTPException(403, "No access to this lead")
    return _out(l)


@router.get("/crm/leads/{lid}/history")
async def lead_history(lid: str, user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    l = (await session.execute(select(CRMLead).where(CRMLead.id == lid))).scalar_one_or_none()
    if not l:
        raise HTTPException(404, "Lead not found")
    if not await svc.can_view_row(session, user, "crm.lead.view", l):
        raise HTTPException(403, "No access to this lead")
    rows = (await session.execute(select(CRMLeadStageHistory).where(
        CRMLeadStageHistory.lead_id == lid).order_by(CRMLeadStageHistory.changed_at))).scalars().all()
    return [{"id": h.id, "from_stage": h.from_stage, "to_stage": h.to_stage, "note": h.note,
             "changed_by": h.changed_by, "changed_at": h.changed_at} for h in rows]


@router.patch("/crm/leads/{lid}")
async def update_lead(lid: str, body: LeadUpdate, request: Request,
                      user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    l = (await session.execute(select(CRMLead).where(CRMLead.id == lid))).scalar_one_or_none()
    if not l:
        raise HTTPException(404, "Lead not found")
    if not await svc.can_modify(session, user, "crm.lead.edit", l):
        raise HTTPException(403, "No edit access to this lead")
    if body.stage is not None and body.stage not in LEAD_STAGES:
        raise HTTPException(400, f"Invalid stage. Allowed: {LEAD_STAGES}")
    before_stage = l.stage
    for f in ("title", "source", "value", "probability", "owner_id", "department_id", "company_id", "contact_id", "notes"):
        v = getattr(body, f)
        if v is not None:
            setattr(l, f, v)
    stage_changed = body.stage is not None and body.stage != before_stage
    if stage_changed:
        l.stage = body.stage
        l.status = _status_for_stage(body.stage)
        session.add(CRMLeadStageHistory(lead_id=lid, from_stage=before_stage, to_stage=body.stage,
                                        note=body.stage_note, changed_by=user["id"]))
    l.updated_at = now_iso()
    await record_audit(session, user, "crm.lead.update", "crm_lead", lid,
                       before={"stage": before_stage}, after={"stage": l.stage},
                       ip=request.client.host if request.client else None)
    await session.commit()
    if stage_changed:
        await svc.log_activity("lead", lid, "stage_change", f"Stage: {before_stage} → {l.stage}", user,
                               department_id=l.department_id, feed_verb="crm.lead.stage_changed",
                               metadata={"from": before_stage, "to": l.stage})
    return _out(l)


@router.post("/crm/leads/{lid}/convert")
async def convert_lead(lid: str, body: ConvertIn, request: Request,
                       user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    l = (await session.execute(select(CRMLead).where(CRMLead.id == lid))).scalar_one_or_none()
    if not l:
        raise HTTPException(404, "Lead not found")
    if not await svc.can_modify(session, user, "crm.lead.edit", l):
        raise HTTPException(403, "No edit access to this lead")
    await ensure_permission(session, user, "crm.opportunity.create", department_id=l.department_id)
    if l.converted_opportunity_id:
        raise HTTPException(400, "Lead already converted")
    opp = CRMOpportunity(
        name=body.name or l.title or "Opportunity", company_id=l.company_id, contact_id=l.contact_id,
        expected_revenue=body.expected_revenue if body.expected_revenue is not None else l.value,
        probability=l.probability, expected_close_date=body.expected_close_date,
        stage=body.stage or "qualification", status="open", owner_id=l.owner_id,
        department_id=l.department_id, source_lead_id=l.id, created_by=user["id"])
    session.add(opp)
    await session.flush()
    session.add(CRMOppStageHistory(opportunity_id=opp.id, from_stage=None, to_stage=opp.stage, changed_by=user["id"]))
    # Mark the lead converted/won.
    l.converted_opportunity_id = opp.id
    if l.stage != "won":
        session.add(CRMLeadStageHistory(lead_id=lid, from_stage=l.stage, to_stage="won",
                                        note="Converted to opportunity", changed_by=user["id"]))
    l.stage, l.status, l.updated_at = "won", "won", now_iso()
    await record_audit(session, user, "crm.lead.convert", "crm_lead", lid,
                       after={"opportunity_id": opp.id}, ip=request.client.host if request.client else None)
    await session.commit()
    await svc.log_activity("lead", lid, "converted", f"Converted to opportunity: {opp.name}", user,
                           department_id=l.department_id, feed_verb="crm.lead.converted",
                           metadata={"opportunity_id": opp.id})
    await svc.log_activity("opportunity", opp.id, "created", f"Opportunity from lead: {opp.name}", user,
                           department_id=opp.department_id, feed_verb="crm.opportunity.created",
                           metadata={"source_lead_id": lid})
    return {"lead": _out(l), "opportunity_id": opp.id}


@router.delete("/crm/leads/{lid}")
async def delete_lead(lid: str, request: Request,
                      user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    l = (await session.execute(select(CRMLead).where(CRMLead.id == lid))).scalar_one_or_none()
    if not l:
        raise HTTPException(404, "Lead not found")
    if not await svc.can_delete(session, user, "crm.lead.delete", l):
        raise HTTPException(403, "No delete access to this lead")
    for h in (await session.execute(select(CRMLeadStageHistory).where(CRMLeadStageHistory.lead_id == lid))).scalars().all():
        await session.delete(h)
    for ln in (await session.execute(select(CRMLink).where(CRMLink.crm_entity_type == "lead", CRMLink.crm_entity_id == lid))).scalars().all():
        await session.delete(ln)
    await session.delete(l)
    await record_audit(session, user, "crm.lead.delete", "crm_lead", lid, before={"title": l.title},
                       ip=request.client.host if request.client else None)
    await session.commit()
    await mongo.crm_activities.delete_many({"crm_entity_type": "lead", "crm_entity_id": lid})
    return {"ok": True}
