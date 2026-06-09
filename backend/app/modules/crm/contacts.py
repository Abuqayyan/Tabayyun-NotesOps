"""CRM Contacts API (Module 2): CRUD, search, links to companies (timeline via /crm/timeline)."""
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
from app.modules.crm.models import CRMContact, CRMCompany, CRMLink
from app.modules.crm import service as svc
from app.modules.rbac.resolver import ensure_permission
from app.modules.audit.service import record_audit

router = APIRouter()


class ContactIn(BaseModel):
    full_name: str
    email: Optional[str] = ""
    phone: Optional[str] = ""
    position: Optional[str] = ""
    company_id: Optional[str] = None
    department_id: Optional[str] = None
    owner_id: Optional[str] = None
    notes: Optional[str] = ""
    tags: Optional[List[str]] = []


class ContactUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    position: Optional[str] = None
    company_id: Optional[str] = None
    department_id: Optional[str] = None
    owner_id: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None


def _out(c: CRMContact) -> dict:
    return {"id": c.id, "full_name": c.full_name, "email": c.email, "phone": c.phone, "position": c.position,
            "company_id": c.company_id, "department_id": c.department_id, "owner_id": c.owner_id,
            "notes": c.notes, "tags": c.tags or [], "created_by": c.created_by,
            "created_at": c.created_at, "updated_at": c.updated_at}


@router.post("/crm/contacts")
async def create_contact(body: ContactIn, request: Request,
                         user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    if not body.full_name.strip():
        raise HTTPException(400, "full_name required")
    await ensure_permission(session, user, "crm.contact.create", department_id=body.department_id)
    if body.company_id and not (await session.execute(select(CRMCompany).where(CRMCompany.id == body.company_id))).scalar_one_or_none():
        raise HTTPException(404, "company_id not found")
    c = CRMContact(full_name=body.full_name.strip(), email=(body.email or "").lower(), phone=body.phone or "",
                   position=body.position or "", company_id=body.company_id, department_id=body.department_id,
                   owner_id=body.owner_id or user["id"], notes=body.notes or "",
                   tags=[t.strip() for t in (body.tags or []) if t.strip()], created_by=user["id"])
    session.add(c)
    await session.flush()
    await record_audit(session, user, "crm.contact.create", "crm_contact", c.id,
                       after={"full_name": c.full_name, "company_id": c.company_id},
                       ip=request.client.host if request.client else None)
    await session.commit()
    await svc.log_activity("contact", c.id, "created", f"Contact created: {c.full_name}", user,
                           department_id=c.department_id, feed_verb="crm.contact.created")
    return _out(c)


@router.get("/crm/contacts")
async def list_contacts(q: Optional[str] = None, company_id: Optional[str] = None,
                        department_id: Optional[str] = None, owner_id: Optional[str] = None, limit: int = 100,
                        user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    limit = min(max(limit, 1), 500)
    await ensure_permission(session, user, "crm.contact.view")
    can_all, dept_ids = await svc.view_scope(session, user, "crm.contact.view")
    query = select(CRMContact).order_by(CRMContact.updated_at.desc())
    vf = svc.visibility_filter(CRMContact, can_all, dept_ids, user["id"])
    if vf is not None:
        query = query.where(vf)
    if company_id:
        query = query.where(CRMContact.company_id == company_id)
    if department_id:
        query = query.where(CRMContact.department_id == department_id)
    if owner_id:
        query = query.where(CRMContact.owner_id == owner_id)
    rows = (await session.execute(query.limit(limit))).scalars().all()
    out = [_out(c) for c in rows]
    if q:
        rx = re.compile(re.escape(q), re.IGNORECASE)
        out = [c for c in out if rx.search(c["full_name"]) or rx.search(c["email"] or "") or rx.search(c["position"] or "")]
    await svc.enrich_users(out)
    return out


@router.get("/crm/contacts/{cid}")
async def get_contact(cid: str, user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    c = (await session.execute(select(CRMContact).where(CRMContact.id == cid))).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Contact not found")
    if not await svc.can_view_row(session, user, "crm.contact.view", c):
        raise HTTPException(403, "No access to this contact")
    return _out(c)


@router.patch("/crm/contacts/{cid}")
async def update_contact(cid: str, body: ContactUpdate, request: Request,
                         user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    c = (await session.execute(select(CRMContact).where(CRMContact.id == cid))).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Contact not found")
    if not await svc.can_modify(session, user, "crm.contact.edit", c):
        raise HTTPException(403, "No edit access to this contact")
    before = _out(c)
    for f in ("full_name", "email", "phone", "position", "company_id", "department_id", "owner_id", "notes", "tags"):
        v = getattr(body, f)
        if v is not None:
            setattr(c, f, v.lower() if f == "email" and isinstance(v, str) else v)
    c.updated_at = now_iso()
    await record_audit(session, user, "crm.contact.update", "crm_contact", cid, before=before,
                       ip=request.client.host if request.client else None)
    await session.commit()
    await svc.log_activity("contact", cid, "updated", f"Contact updated: {c.full_name}", user,
                           department_id=c.department_id, feed_verb="crm.contact.updated")
    return _out(c)


@router.delete("/crm/contacts/{cid}")
async def delete_contact(cid: str, request: Request,
                         user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    c = (await session.execute(select(CRMContact).where(CRMContact.id == cid))).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Contact not found")
    if not await svc.can_delete(session, user, "crm.contact.delete", c):
        raise HTTPException(403, "No delete access to this contact")
    # Detach leads/opportunities that reference this contact (FK) to avoid orphan violations.
    from app.modules.crm.models import CRMLead, CRMOpportunity
    for ld in (await session.execute(select(CRMLead).where(CRMLead.contact_id == cid))).scalars().all():
        ld.contact_id = None
    for op in (await session.execute(select(CRMOpportunity).where(CRMOpportunity.contact_id == cid))).scalars().all():
        op.contact_id = None
    await session.flush()
    for ln in (await session.execute(select(CRMLink).where(CRMLink.crm_entity_type == "contact", CRMLink.crm_entity_id == cid))).scalars().all():
        await session.delete(ln)
    await session.delete(c)
    await record_audit(session, user, "crm.contact.delete", "crm_contact", cid, before={"full_name": c.full_name},
                       ip=request.client.host if request.client else None)
    await session.commit()
    await mongo.crm_activities.delete_many({"crm_entity_type": "contact", "crm_entity_id": cid})
    return {"ok": True}
