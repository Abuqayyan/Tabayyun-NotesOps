"""Global search engine — permission-aware, ranked, resilient.

Each entity type is searched only within the caller's RBAC scope (reusing the same
visibility helpers the feature modules use), scored by match quality, and capped. A
failure in one source never breaks the whole search (each source is isolated).
"""
import re
import logging
from typing import List, Dict, Any, Optional, Set

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db_mongo import db as mongo
from app.modules.rbac.resolver import user_can, get_permission_keys, user_department_ids

log = logging.getLogger("opscore.search")

ALL_TYPES = ["employee", "department", "task", "project", "meeting", "approval",
             "knowledge", "crm_company", "crm_contact", "crm_opportunity", "report", "activity"]
_PER_TYPE = 8


def _score(q: str, *texts: str) -> int:
    ql = q.lower().strip()
    best = 0
    for t in texts:
        if not t:
            continue
        tl = t.lower()
        if tl == ql:
            best = max(best, 100)
        elif tl.startswith(ql):
            best = max(best, 85)
        elif re.search(r"\b" + re.escape(ql), tl):
            best = max(best, 65)
        elif ql in tl:
            best = max(best, 45)
    return best


def _rx(q: str):
    return re.compile(re.escape(q), re.IGNORECASE)


def _hit(rtype, rid, title, subtitle, q, *texts, **extra):
    s = _score(q, title or "", *texts)
    if s == 0 and not extra.get("force"):
        return None
    return {"type": rtype, "id": rid, "title": title, "subtitle": subtitle, "score": s, **extra.get("ref", {})}


async def _search_crm(session, user, q, want) -> List[Dict[str, Any]]:
    from app.modules.crm import service as crmsvc
    from app.modules.crm.models import CRMCompany, CRMContact, CRMOpportunity
    out: List[Dict[str, Any]] = []
    plans = [("crm_company", CRMCompany, "crm.company.view", lambda r: (r.name, r.industry)),
             ("crm_contact", CRMContact, "crm.contact.view", lambda r: (r.full_name, r.email)),
             ("crm_opportunity", CRMOpportunity, "crm.opportunity.view", lambda r: (r.name, r.stage))]
    for rtype, Model, perm, fields in plans:
        if rtype not in want:
            continue
        can_all, dept_ids = await crmsvc.view_scope(session, user, perm)
        if not (can_all or dept_ids or user.get("is_admin")):
            continue
        query = select(Model)
        vf = crmsvc.visibility_filter(Model, can_all, dept_ids, user["id"])
        if vf is not None:
            query = query.where(vf)
        rows = (await session.execute(query.limit(200))).scalars().all()
        for r in rows:
            title, sub = fields(r)
            hit = _hit(rtype, r.id, title, sub, q)
            if hit:
                out.append(hit)
    return out


async def _search_knowledge(session, user, q, want) -> List[Dict[str, Any]]:
    if "knowledge" not in want:
        return []
    from app.modules.knowledge import service as kb
    ctx = await kb.view_context(session, user)
    query = dict(kb.visibility_query(ctx, user["id"]))
    rx = _rx(q)
    query = {"$and": [query, {"$or": [{"title": rx}, {"tags": rx}]}]} if query else {"$or": [{"title": rx}, {"tags": rx}]}
    rows = await mongo.knowledge_articles.find(query, {"_id": 0, "id": 1, "title": 1, "article_type": 1}).to_list(50)
    return [h for h in (_hit("knowledge", r["id"], r.get("title"), r.get("article_type"), q) for r in rows) if h]


async def _search_tasks_projects(session, user, q, want) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    from app.shared.permissions import user_visible_project_ids
    uid = user["id"]
    rx = _rx(q)
    if "task" in want:
        vpids = await user_visible_project_ids(uid)
        rows = await mongo.tasks.find(
            {"title": rx, "$or": [{"owner_id": uid}, {"assignee_id": uid}, {"project_id": {"$in": vpids}}]},
            {"_id": 0, "id": 1, "title": 1, "status": 1}).to_list(50)
        out += [h for h in (_hit("task", r["id"], r.get("title"), r.get("status"), q) for r in rows) if h]
    if "project" in want:
        rows = await mongo.projects.find({"members": uid, "name": rx}, {"_id": 0, "id": 1, "name": 1, "status": 1}).to_list(50)
        out += [h for h in (_hit("project", r["id"], r.get("name"), r.get("status"), q) for r in rows) if h]
    return out


async def _search_meetings_approvals(session, user, q, want) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    uid = user["id"]
    if "meeting" in want:
        from app.modules.meetings.models import Meeting, MeetingAttendee
        attended = (await session.execute(select(MeetingAttendee.meeting_id).where(MeetingAttendee.user_id == uid))).scalars().all()
        can_view = user.get("is_admin") or await user_can(session, user, "meeting.view")
        query = select(Meeting)
        if not can_view:
            query = query.where(or_(Meeting.organizer_id == uid, Meeting.id.in_(attended) if attended else (Meeting.id == "__none__")))
        rows = (await session.execute(query.limit(200))).scalars().all()
        out += [h for h in (_hit("meeting", m.id, m.title, m.status, q) for m in rows) if h]
    if "approval" in want:
        from app.modules.approvals.models import ApprovalRequest
        can_view = user.get("is_admin") or await user_can(session, user, "approval.view")
        query = select(ApprovalRequest)
        if not can_view:
            query = query.where(ApprovalRequest.requester_id == uid)
        rows = (await session.execute(query.limit(200))).scalars().all()
        out += [h for h in (_hit("approval", r.id, r.title, r.status, q) for r in rows) if h]
    return out


async def _search_org(session, user, q, want) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if "department" in want and (user.get("is_admin") or await user_can(session, user, "department.view")):
        from app.modules.org.models import Department
        rows = (await session.execute(select(Department))).scalars().all()
        out += [h for h in (_hit("department", d.id, d.name, "department", q) for d in rows) if h]
    if "employee" in want and (user.get("is_admin") or await user_can(session, user, "employee.view")):
        rx = _rx(q)
        rows = await mongo.users.find({"$or": [{"name": rx}, {"email": rx}]}, {"_id": 0, "id": 1, "name": 1, "email": 1}).to_list(50)
        out += [h for h in (_hit("employee", r["id"], r.get("name"), r.get("email"), q) for r in rows) if h]
    return out


async def _search_reports_activity(session, user, q, want) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if "report" in want and (user.get("is_admin") or await user_can(session, user, "report.view_company")
                             or await user_can(session, user, "report.view_department")):
        from app.modules.reporting.models import Report
        rows = (await session.execute(select(Report).order_by(Report.created_at.desc()).limit(100))).scalars().all()
        for r in rows:
            hit = _hit("report", r.id, r.report_type, f"{r.period_start}..{r.period_end}", q, r.scope_type)
            if hit:
                out.append(hit)
    if "activity" in want:
        perms = await get_permission_keys(session, user)
        rx = _rx(q)
        if "activity.view_all" in perms:
            query: Dict[str, Any] = {"$or": [{"verb": rx}, {"metadata.title": rx}]}
        else:
            dept_ids = list(await user_department_ids(session, user["id"]))
            scope = [{"actor_id": user["id"]}]
            if "activity.view_department" in perms and dept_ids:
                scope.append({"department_id": {"$in": dept_ids}})
            query = {"$and": [{"$or": scope}, {"$or": [{"verb": rx}, {"metadata.title": rx}]}]}
        rows = await mongo.activity_feed.find(query, {"_id": 0}).sort("created_at", -1).to_list(50)
        for r in rows:
            title = (r.get("metadata") or {}).get("title") or r.get("verb")
            hit = _hit("activity", r.get("id"), title, r.get("verb"), q, force=True)
            if hit:
                out.append(hit)
    return out


async def global_search(session: AsyncSession, user: dict, q: str, types: Optional[List[str]] = None,
                        limit: int = 30) -> Dict[str, Any]:
    q = (q or "").strip()
    if len(q) < 2:
        return {"query": q, "count": 0, "results": [], "by_type": {}}
    want: Set[str] = set(types) if types else set(ALL_TYPES)
    sources = [_search_crm, _search_knowledge, _search_tasks_projects,
               _search_meetings_approvals, _search_org, _search_reports_activity]
    results: List[Dict[str, Any]] = []
    for src in sources:
        try:
            results += await src(session, user, q, want)
        except Exception as exc:  # noqa: BLE001 - one bad source must not kill search
            log.warning(f"search source {src.__name__} failed: {exc}")
    # Rank: score desc, cap per type, then overall.
    results.sort(key=lambda r: -r.get("score", 0))
    per_type_count: Dict[str, int] = {}
    capped: List[Dict[str, Any]] = []
    for r in results:
        c = per_type_count.get(r["type"], 0)
        if c < _PER_TYPE:
            capped.append(r)
            per_type_count[r["type"]] = c + 1
    capped = capped[:min(max(limit, 1), 100)]
    by_type: Dict[str, int] = {}
    for r in capped:
        by_type[r["type"]] = by_type.get(r["type"], 0) + 1
    return {"query": q, "count": len(capped), "results": capped, "by_type": by_type}
