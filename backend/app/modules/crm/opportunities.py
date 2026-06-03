"""CRM Opportunities / Deals API (Module 4): pipeline board, forecasting, stage history."""
import re
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db_mongo import db as mongo
from app.core.db_postgres import get_session
from app.core.security import get_current_user
from app.core.utils import now_iso
from app.modules.crm.models import CRMOpportunity, CRMOppStageHistory, CRMLink, OPP_STAGES
from app.modules.crm import service as svc
from app.modules.rbac.resolver import ensure_permission
from app.modules.audit.service import record_audit

router = APIRouter()


def _status_for_stage(stage: str) -> str:
    return "won" if stage == "won" else "lost" if stage == "lost" else "open"


class OppIn(BaseModel):
    name: str
    company_id: Optional[str] = None
    contact_id: Optional[str] = None
    expected_revenue: Optional[float] = 0.0
    probability: Optional[int] = 0
    expected_close_date: Optional[str] = None
    stage: Optional[str] = "prospecting"
    owner_id: Optional[str] = None
    department_id: Optional[str] = None
    notes: Optional[str] = ""


class OppUpdate(BaseModel):
    name: Optional[str] = None
    company_id: Optional[str] = None
    contact_id: Optional[str] = None
    expected_revenue: Optional[float] = None
    probability: Optional[int] = None
    expected_close_date: Optional[str] = None
    stage: Optional[str] = None
    owner_id: Optional[str] = None
    department_id: Optional[str] = None
    notes: Optional[str] = None
    stage_note: Optional[str] = None


def _out(o: CRMOpportunity) -> dict:
    return {"id": o.id, "name": o.name, "company_id": o.company_id, "contact_id": o.contact_id,
            "expected_revenue": o.expected_revenue, "probability": o.probability,
            "expected_close_date": o.expected_close_date, "stage": o.stage, "status": o.status,
            "owner_id": o.owner_id, "department_id": o.department_id, "source_lead_id": o.source_lead_id,
            "notes": o.notes, "weighted_value": round((o.expected_revenue or 0) * (o.probability or 0) / 100.0, 2),
            "created_by": o.created_by, "created_at": o.created_at, "updated_at": o.updated_at}


@router.post("/crm/opportunities")
async def create_opportunity(body: OppIn, request: Request,
                             user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    if not body.name.strip():
        raise HTTPException(400, "name required")
    stage = body.stage or "prospecting"
    if stage not in OPP_STAGES:
        raise HTTPException(400, f"Invalid stage. Allowed: {OPP_STAGES}")
    await ensure_permission(session, user, "crm.opportunity.create", department_id=body.department_id)
    o = CRMOpportunity(name=body.name.strip(), company_id=body.company_id, contact_id=body.contact_id,
                       expected_revenue=body.expected_revenue or 0.0, probability=body.probability or 0,
                       expected_close_date=body.expected_close_date, stage=stage, status=_status_for_stage(stage),
                       owner_id=body.owner_id or user["id"], department_id=body.department_id,
                       notes=body.notes or "", created_by=user["id"])
    session.add(o)
    await session.flush()
    session.add(CRMOppStageHistory(opportunity_id=o.id, from_stage=None, to_stage=stage, changed_by=user["id"]))
    await record_audit(session, user, "crm.opportunity.create", "crm_opportunity", o.id,
                       after={"name": o.name, "stage": stage, "expected_revenue": o.expected_revenue},
                       ip=request.client.host if request.client else None)
    await session.commit()
    await svc.log_activity("opportunity", o.id, "created", f"Opportunity created: {o.name}", user,
                           department_id=o.department_id, feed_verb="crm.opportunity.created", metadata={"stage": stage})
    return _out(o)


@router.get("/crm/opportunities")
async def list_opportunities(q: Optional[str] = None, stage: Optional[str] = None, status: Optional[str] = None,
                             company_id: Optional[str] = None, owner_id: Optional[str] = None,
                             department_id: Optional[str] = None, limit: int = 200,
                             user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    limit = min(max(limit, 1), 1000)
    await ensure_permission(session, user, "crm.opportunity.view")
    can_all, dept_ids = await svc.view_scope(session, user, "crm.opportunity.view")
    query = select(CRMOpportunity).order_by(CRMOpportunity.updated_at.desc())
    vf = svc.visibility_filter(CRMOpportunity, can_all, dept_ids, user["id"])
    if vf is not None:
        query = query.where(vf)
    if stage:
        query = query.where(CRMOpportunity.stage == stage)
    if status:
        query = query.where(CRMOpportunity.status == status)
    if company_id:
        query = query.where(CRMOpportunity.company_id == company_id)
    if owner_id:
        query = query.where(CRMOpportunity.owner_id == owner_id)
    if department_id:
        query = query.where(CRMOpportunity.department_id == department_id)
    rows = (await session.execute(query.limit(limit))).scalars().all()
    out = [_out(o) for o in rows]
    if q:
        rx = re.compile(re.escape(q), re.IGNORECASE)
        out = [o for o in out if rx.search(o["name"])]
    await svc.enrich_users(out)
    return out


# --- Pipeline board + forecast must precede /{oid} ---
async def _scoped_open_opps(session, user, department_id):
    can_all, dept_ids = await svc.view_scope(session, user, "crm.opportunity.view")
    query = select(CRMOpportunity)
    vf = svc.visibility_filter(CRMOpportunity, can_all, dept_ids, user["id"])
    if vf is not None:
        query = query.where(vf)
    if department_id:
        query = query.where(CRMOpportunity.department_id == department_id)
    return (await session.execute(query)).scalars().all()


@router.get("/crm/pipeline")
async def pipeline_board(department_id: Optional[str] = None,
                         user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    await ensure_permission(session, user, "crm.opportunity.view")
    opps = await _scoped_open_opps(session, user, department_id)
    board: Dict[str, Any] = {s: {"count": 0, "value": 0.0, "weighted": 0.0, "items": []} for s in OPP_STAGES}
    for o in opps:
        col = board.setdefault(o.stage, {"count": 0, "value": 0.0, "weighted": 0.0, "items": []})
        col["count"] += 1
        col["value"] += o.expected_revenue or 0
        col["weighted"] += (o.expected_revenue or 0) * (o.probability or 0) / 100.0
        col["items"].append({"id": o.id, "name": o.name, "expected_revenue": o.expected_revenue,
                             "probability": o.probability, "owner_id": o.owner_id})
    for col in board.values():
        col["value"] = round(col["value"], 2)
        col["weighted"] = round(col["weighted"], 2)
    return {"stages": OPP_STAGES, "board": board}


@router.get("/crm/forecast")
async def forecast(department_id: Optional[str] = None,
                   user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    await ensure_permission(session, user, "crm.opportunity.view")
    opps = await _scoped_open_opps(session, user, department_id)
    open_opps = [o for o in opps if o.status == "open"]
    won = [o for o in opps if o.status == "won"]
    lost = [o for o in opps if o.status == "lost"]
    weighted = sum((o.expected_revenue or 0) * (o.probability or 0) / 100.0 for o in open_opps)
    return {
        "open_count": len(open_opps),
        "total_pipeline": round(sum(o.expected_revenue or 0 for o in open_opps), 2),
        "weighted_forecast": round(weighted, 2),
        "won_revenue": round(sum(o.expected_revenue or 0 for o in won), 2),
        "lost_revenue": round(sum(o.expected_revenue or 0 for o in lost), 2),
        "by_stage": {s: round(sum(o.expected_revenue or 0 for o in open_opps if o.stage == s), 2) for s in OPP_STAGES},
    }


@router.get("/crm/opportunities/{oid}")
async def get_opportunity(oid: str, user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    o = (await session.execute(select(CRMOpportunity).where(CRMOpportunity.id == oid))).scalar_one_or_none()
    if not o:
        raise HTTPException(404, "Opportunity not found")
    if not await svc.can_view_row(session, user, "crm.opportunity.view", o):
        raise HTTPException(403, "No access to this opportunity")
    return _out(o)


@router.get("/crm/opportunities/{oid}/history")
async def opp_history(oid: str, user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    o = (await session.execute(select(CRMOpportunity).where(CRMOpportunity.id == oid))).scalar_one_or_none()
    if not o:
        raise HTTPException(404, "Opportunity not found")
    if not await svc.can_view_row(session, user, "crm.opportunity.view", o):
        raise HTTPException(403, "No access to this opportunity")
    rows = (await session.execute(select(CRMOppStageHistory).where(
        CRMOppStageHistory.opportunity_id == oid).order_by(CRMOppStageHistory.changed_at))).scalars().all()
    return [{"id": h.id, "from_stage": h.from_stage, "to_stage": h.to_stage, "note": h.note,
             "changed_by": h.changed_by, "changed_at": h.changed_at} for h in rows]


@router.patch("/crm/opportunities/{oid}")
async def update_opportunity(oid: str, body: OppUpdate, request: Request,
                             user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    o = (await session.execute(select(CRMOpportunity).where(CRMOpportunity.id == oid))).scalar_one_or_none()
    if not o:
        raise HTTPException(404, "Opportunity not found")
    if not await svc.can_modify(session, user, "crm.opportunity.edit", o):
        raise HTTPException(403, "No edit access to this opportunity")
    if body.stage is not None and body.stage not in OPP_STAGES:
        raise HTTPException(400, f"Invalid stage. Allowed: {OPP_STAGES}")
    before_stage = o.stage
    for f in ("name", "company_id", "contact_id", "expected_revenue", "probability",
              "expected_close_date", "owner_id", "department_id", "notes"):
        v = getattr(body, f)
        if v is not None:
            setattr(o, f, v)
    stage_changed = body.stage is not None and body.stage != before_stage
    if stage_changed:
        o.stage = body.stage
        o.status = _status_for_stage(body.stage)
        session.add(CRMOppStageHistory(opportunity_id=oid, from_stage=before_stage, to_stage=body.stage,
                                       note=body.stage_note, changed_by=user["id"]))
    o.updated_at = now_iso()
    await record_audit(session, user, "crm.opportunity.update", "crm_opportunity", oid,
                       before={"stage": before_stage}, after={"stage": o.stage},
                       ip=request.client.host if request.client else None)
    await session.commit()
    if stage_changed:
        verb = "crm.opportunity.won" if o.stage == "won" else "crm.opportunity.lost" if o.stage == "lost" else "crm.opportunity.stage_changed"
        await svc.log_activity("opportunity", oid, "stage_change", f"Stage: {before_stage} → {o.stage}", user,
                               department_id=o.department_id, feed_verb=verb,
                               metadata={"from": before_stage, "to": o.stage})
    return _out(o)


@router.delete("/crm/opportunities/{oid}")
async def delete_opportunity(oid: str, request: Request,
                             user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    o = (await session.execute(select(CRMOpportunity).where(CRMOpportunity.id == oid))).scalar_one_or_none()
    if not o:
        raise HTTPException(404, "Opportunity not found")
    if not await svc.can_delete(session, user, "crm.opportunity.delete", o):
        raise HTTPException(403, "No delete access to this opportunity")
    for h in (await session.execute(select(CRMOppStageHistory).where(CRMOppStageHistory.opportunity_id == oid))).scalars().all():
        await session.delete(h)
    for ln in (await session.execute(select(CRMLink).where(CRMLink.crm_entity_type == "opportunity", CRMLink.crm_entity_id == oid))).scalars().all():
        await session.delete(ln)
    await session.delete(o)
    await record_audit(session, user, "crm.opportunity.delete", "crm_opportunity", oid, before={"name": o.name},
                       ip=request.client.host if request.client else None)
    await session.commit()
    await mongo.crm_activities.delete_many({"crm_entity_type": "opportunity", "crm_entity_id": oid})
    return {"ok": True}
