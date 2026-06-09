"""Data export API (Module 8).

GET /exports/{entity}?format=csv|xlsx — exports only the rows the caller may see (reusing
the same RBAC visibility helpers as the feature modules), gated by export.data, and every
export is written to the Audit Log. CSV always works; XLSX is best-effort (falls back to CSV
if openpyxl is absent).
"""
from typing import List, Tuple, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db_mongo import db as mongo
from app.core.db_postgres import get_session
from app.core.security import get_current_user
from app.shared.rate_limit import limiter, LIMIT_EXPORT
from app.shared.export_util import tabular_response
from app.modules.rbac.resolver import ensure_permission, user_can, get_permission_keys, user_department_ids
from app.modules.audit.service import record_audit

router = APIRouter()

EXPORTABLE = ["tasks", "meetings", "approvals", "reports", "activity",
              "crm_companies", "crm_contacts", "crm_leads", "crm_opportunities", "knowledge"]


async def _tasks(session, user) -> Tuple[List[str], List[dict]]:
    from app.shared.permissions import user_visible_project_ids
    uid = user["id"]
    vpids = await user_visible_project_ids(uid)
    rows = await mongo.tasks.find(
        {"$or": [{"owner_id": uid}, {"assignee_id": uid}, {"project_id": {"$in": vpids}}]}, {"_id": 0}).to_list(5000)
    headers = ["id", "title", "status", "priority", "due_date", "assignee_id", "project_id", "created_at"]
    return headers, rows


async def _meetings(session, user) -> Tuple[List[str], List[dict]]:
    from app.modules.meetings.models import Meeting, MeetingAttendee
    uid = user["id"]
    q = select(Meeting)
    if not (user.get("is_admin") or await user_can(session, user, "meeting.view")):
        attended = (await session.execute(select(MeetingAttendee.meeting_id).where(MeetingAttendee.user_id == uid))).scalars().all()
        q = q.where(or_(Meeting.organizer_id == uid, Meeting.id.in_(attended) if attended else (Meeting.id == "__none__")))
    rows = [{"id": m.id, "title": m.title, "department_id": m.department_id, "organizer_id": m.organizer_id,
             "meeting_at": m.meeting_at, "status": m.status, "created_at": m.created_at}
            for m in (await session.execute(q)).scalars().all()]
    return ["id", "title", "department_id", "organizer_id", "meeting_at", "status", "created_at"], rows


async def _approvals(session, user) -> Tuple[List[str], List[dict]]:
    from app.modules.approvals.models import ApprovalRequest
    q = select(ApprovalRequest)
    if not (user.get("is_admin") or await user_can(session, user, "approval.view")):
        q = q.where(ApprovalRequest.requester_id == user["id"])
    rows = [{"id": r.id, "title": r.title, "status": r.status, "requester_id": r.requester_id,
             "department_id": r.department_id, "current_step": r.current_step, "created_at": r.created_at}
            for r in (await session.execute(q)).scalars().all()]
    return ["id", "title", "status", "requester_id", "department_id", "current_step", "created_at"], rows


async def _reports(session, user) -> Tuple[List[str], List[dict]]:
    if not (user.get("is_admin") or await user_can(session, user, "report.view_company")
            or await user_can(session, user, "report.view_department")):
        raise HTTPException(403, "Missing permission to export reports")
    from app.modules.reporting.models import Report
    rows = [{"id": r.id, "report_type": r.report_type, "scope_type": r.scope_type, "department_id": r.department_id,
             "period_start": r.period_start, "period_end": r.period_end, "created_at": r.created_at}
            for r in (await session.execute(select(Report))).scalars().all()]
    return ["id", "report_type", "scope_type", "department_id", "period_start", "period_end", "created_at"], rows


async def _activity(session, user) -> Tuple[List[str], List[dict]]:
    perms = await get_permission_keys(session, user)
    if "activity.view_all" in perms:
        query: Dict[str, Any] = {}
    elif "activity.view_department" in perms:
        dept_ids = list(await user_department_ids(session, user["id"]))
        query = {"$or": [{"actor_id": user["id"]}, {"department_id": {"$in": dept_ids}}]}
    else:
        query = {"actor_id": user["id"]}
    rows = await mongo.activity_feed.find(query, {"_id": 0}).sort("created_at", -1).to_list(5000)
    return ["id", "actor_name", "verb", "object_type", "object_id", "department_id", "created_at"], rows


def _crm_export(model_name, perm, headers):
    async def _fn(session, user):
        from app.modules.crm import service as crmsvc
        from app.modules.crm import models as M
        Model = getattr(M, model_name)
        can_all, dept_ids = await crmsvc.view_scope(session, user, perm)
        if not (can_all or dept_ids or user.get("is_admin")):
            raise HTTPException(403, f"Missing permission: {perm}")
        q = select(Model)
        vf = crmsvc.visibility_filter(Model, can_all, dept_ids, user["id"])
        if vf is not None:
            q = q.where(vf)
        rows = [{h: getattr(r, h, None) for h in headers} for r in (await session.execute(q)).scalars().all()]
        return headers, rows
    return _fn


async def _knowledge(session, user) -> Tuple[List[str], List[dict]]:
    from app.modules.knowledge import service as kb
    ctx = await kb.view_context(session, user)
    rows = await mongo.knowledge_articles.find(kb.visibility_query(ctx, user["id"]), {"_id": 0}).to_list(5000)
    headers = ["id", "title", "article_type", "category", "department_id", "status", "version", "updated_at"]
    return headers, [{h: r.get(h) for h in headers} for r in rows]


_BUILDERS = {
    "tasks": _tasks, "meetings": _meetings, "approvals": _approvals, "reports": _reports, "activity": _activity,
    "knowledge": _knowledge,
    "crm_companies": _crm_export("CRMCompany", "crm.company.view",
                                 ["id", "name", "industry", "status", "country", "city", "owner_id", "department_id", "created_at"]),
    "crm_contacts": _crm_export("CRMContact", "crm.contact.view",
                                ["id", "full_name", "email", "phone", "position", "company_id", "owner_id", "department_id"]),
    "crm_leads": _crm_export("CRMLead", "crm.lead.view",
                             ["id", "title", "source", "value", "probability", "stage", "status", "owner_id", "department_id"]),
    "crm_opportunities": _crm_export("CRMOpportunity", "crm.opportunity.view",
                                     ["id", "name", "expected_revenue", "probability", "stage", "status", "expected_close_date", "owner_id", "department_id"]),
}


@router.get("/exports")
async def list_exportable(user=Depends(get_current_user)):
    return {"entities": EXPORTABLE, "formats": ["csv", "xlsx"]}


@router.get("/exports/{entity}")
@limiter.limit(LIMIT_EXPORT)
async def export_entity(entity: str, request: Request, format: str = "csv",
                        user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    if entity not in _BUILDERS:
        raise HTTPException(404, f"Unknown export entity. Allowed: {EXPORTABLE}")
    await ensure_permission(session, user, "export.data")
    headers, rows = await _BUILDERS[entity](session, user)
    await record_audit(session, user, f"export.{entity}", "export", entity,
                       after={"format": format, "rows": len(rows)},
                       ip=request.client.host if request.client else None)
    await session.commit()
    return tabular_response(format, f"tabayyun_{entity}", headers, rows)
