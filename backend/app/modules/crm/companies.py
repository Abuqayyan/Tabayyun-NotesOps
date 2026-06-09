"""CRM Companies API (Module 1): CRUD, search, filters, ownership, department scope."""
import re
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db_mongo import db as mongo
from app.core.db_postgres import get_session
from app.core.security import get_current_user
from app.core.utils import now_iso
from app.modules.crm.models import CRMCompany, CRMContact, CRMLead, CRMOpportunity, CRMLink
from app.modules.crm import service as svc
from app.modules.rbac.resolver import ensure_permission
from app.modules.audit.service import record_audit

router = APIRouter()


class CompanyIn(BaseModel):
    name: str
    industry: Optional[str] = ""
    website: Optional[str] = ""
    address: Optional[str] = ""
    country: Optional[str] = ""
    city: Optional[str] = ""
    status: Optional[str] = "prospect"
    owner_id: Optional[str] = None
    department_id: Optional[str] = None
    notes: Optional[str] = ""
    tags: Optional[List[str]] = []


class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    industry: Optional[str] = None
    website: Optional[str] = None
    address: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    status: Optional[str] = None
    owner_id: Optional[str] = None
    department_id: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None


def _out(c: CRMCompany) -> dict:
    return {"id": c.id, "name": c.name, "industry": c.industry, "website": c.website, "address": c.address,
            "country": c.country, "city": c.city, "status": c.status, "owner_id": c.owner_id,
            "department_id": c.department_id, "notes": c.notes, "tags": c.tags or [],
            "created_by": c.created_by, "created_at": c.created_at, "updated_at": c.updated_at}


@router.post("/crm/companies")
async def create_company(body: CompanyIn, request: Request,
                         user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    if not body.name.strip():
        raise HTTPException(400, "name required")
    await ensure_permission(session, user, "crm.company.create", department_id=body.department_id)
    c = CRMCompany(name=body.name.strip(), industry=body.industry or "", website=body.website or "",
                   address=body.address or "", country=body.country or "", city=body.city or "",
                   status=body.status or "prospect", owner_id=body.owner_id or user["id"],
                   department_id=body.department_id, notes=body.notes or "",
                   tags=[t.strip() for t in (body.tags or []) if t.strip()], created_by=user["id"])
    session.add(c)
    await session.flush()
    await record_audit(session, user, "crm.company.create", "crm_company", c.id,
                       after={"name": c.name, "department_id": c.department_id},
                       ip=request.client.host if request.client else None)
    await session.commit()
    await svc.log_activity("company", c.id, "created", f"Company created: {c.name}", user,
                           department_id=c.department_id, feed_verb="crm.company.created")
    return _out(c)


@router.get("/crm/companies")
async def list_companies(q: Optional[str] = None, status: Optional[str] = None, industry: Optional[str] = None,
                         department_id: Optional[str] = None, owner_id: Optional[str] = None, limit: int = 100,
                         user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    limit = min(max(limit, 1), 500)
    await ensure_permission(session, user, "crm.company.view")
    can_all, dept_ids = await svc.view_scope(session, user, "crm.company.view")
    query = select(CRMCompany).order_by(CRMCompany.updated_at.desc())
    vf = svc.visibility_filter(CRMCompany, can_all, dept_ids, user["id"])
    if vf is not None:
        query = query.where(vf)
    if status:
        query = query.where(CRMCompany.status == status)
    if industry:
        query = query.where(CRMCompany.industry == industry)
    if department_id:
        query = query.where(CRMCompany.department_id == department_id)
    if owner_id:
        query = query.where(CRMCompany.owner_id == owner_id)
    rows = (await session.execute(query.limit(limit))).scalars().all()
    out = [_out(c) for c in rows]
    if q:
        rx = re.compile(re.escape(q), re.IGNORECASE)
        out = [c for c in out if rx.search(c["name"]) or rx.search(c["industry"] or "") or rx.search(c["country"] or "")]
    await svc.enrich_users(out)
    return out


@router.get("/crm/companies/{cid}")
async def get_company(cid: str, user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    c = (await session.execute(select(CRMCompany).where(CRMCompany.id == cid))).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Company not found")
    if not await svc.can_view_row(session, user, "crm.company.view", c):
        raise HTTPException(403, "No access to this company")
    out = _out(c)
    out["contacts"] = len((await session.execute(select(CRMContact.id).where(CRMContact.company_id == cid))).scalars().all())
    out["opportunities"] = len((await session.execute(select(CRMOpportunity.id).where(CRMOpportunity.company_id == cid))).scalars().all())
    return out


@router.patch("/crm/companies/{cid}")
async def update_company(cid: str, body: CompanyUpdate, request: Request,
                         user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    c = (await session.execute(select(CRMCompany).where(CRMCompany.id == cid))).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Company not found")
    if not await svc.can_modify(session, user, "crm.company.edit", c):
        raise HTTPException(403, "No edit access to this company")
    before = _out(c)
    for f in ("name", "industry", "website", "address", "country", "city", "status", "owner_id", "department_id", "notes", "tags"):
        v = getattr(body, f)
        if v is not None:
            setattr(c, f, v)
    c.updated_at = now_iso()
    await record_audit(session, user, "crm.company.update", "crm_company", cid, before=before, after=_out(c),
                       ip=request.client.host if request.client else None)
    await session.commit()
    await svc.log_activity("company", cid, "updated", f"Company updated: {c.name}", user,
                           department_id=c.department_id, feed_verb="crm.company.updated")
    return _out(c)


@router.delete("/crm/companies/{cid}")
async def delete_company(cid: str, request: Request,
                         user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    c = (await session.execute(select(CRMCompany).where(CRMCompany.id == cid))).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Company not found")
    if not await svc.can_delete(session, user, "crm.company.delete", c):
        raise HTTPException(403, "No delete access to this company")
    # Detach dependents (keep contacts/leads/opps, null the FK) to avoid orphan FK violations.
    for ct in (await session.execute(select(CRMContact).where(CRMContact.company_id == cid))).scalars().all():
        ct.company_id = None
    for ld in (await session.execute(select(CRMLead).where(CRMLead.company_id == cid))).scalars().all():
        ld.company_id = None
    for op in (await session.execute(select(CRMOpportunity).where(CRMOpportunity.company_id == cid))).scalars().all():
        op.company_id = None
    await session.flush()
    for ln in (await session.execute(select(CRMLink).where(CRMLink.crm_entity_type == "company", CRMLink.crm_entity_id == cid))).scalars().all():
        await session.delete(ln)
    await session.delete(c)
    await record_audit(session, user, "crm.company.delete", "crm_company", cid, before={"name": c.name},
                       ip=request.client.host if request.client else None)
    await session.commit()
    await mongo.crm_activities.delete_many({"crm_entity_type": "company", "crm_entity_id": cid})
    return {"ok": True}
