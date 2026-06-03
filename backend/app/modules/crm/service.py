"""CRM shared services: visibility scoping, modification checks, activity timeline.

Visibility reuses the RBAC resolver's scope-aware `permission_scopes`: a row is visible if
the viewer holds the relevant crm.*.view globally, holds it scoped to the row's department,
owns the row, or is an admin. Client activities are appended to Mongo `crm_activities`
(per-entity timeline) AND emitted to the global activity feed.
"""
from typing import Optional, Tuple, Set, List, Dict, Any

from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db_mongo import db as mongo
from app.core.utils import new_id, now_iso
from app.modules.rbac.resolver import permission_scopes, user_can
from app.shared.activity import emit_activity


async def view_scope(session: AsyncSession, user: dict, view_perm: str) -> Tuple[bool, Set[str]]:
    """(can_see_all, accessible_department_ids) for a crm.*.view permission."""
    if user.get("is_admin"):
        return True, set()
    held_global, dept_ids = await permission_scopes(session, user, view_perm)
    return held_global, dept_ids


def visibility_filter(model, can_all: bool, dept_ids: Set[str], uid: str):
    """SQLAlchemy WHERE clause limiting `model` rows to what the user may see (None = all)."""
    if can_all:
        return None
    clauses = [model.owner_id == uid, model.created_by == uid]
    if dept_ids:
        clauses.append(model.department_id.in_(list(dept_ids)))
    return or_(*clauses)


async def can_view_row(session: AsyncSession, user: dict, view_perm: str, row) -> bool:
    if user.get("is_admin") or getattr(row, "owner_id", None) == user["id"] or getattr(row, "created_by", None) == user["id"]:
        return True
    can_all, dept_ids = await view_scope(session, user, view_perm)
    if can_all:
        return True
    return getattr(row, "department_id", None) in dept_ids


async def can_modify(session: AsyncSession, user: dict, perm: str, row) -> bool:
    """Edit access: the owner OR a holder of the edit permission in the row's scope."""
    if user.get("is_admin") or getattr(row, "owner_id", None) == user["id"]:
        return True
    return await user_can(session, user, perm, department_id=getattr(row, "department_id", None))


async def can_delete(session: AsyncSession, user: dict, perm: str, row) -> bool:
    """Delete access is privileged: it requires the explicit delete permission (or admin),
    NOT mere ownership. Owners can create/edit their records but not hard-delete them."""
    if user.get("is_admin"):
        return True
    return await user_can(session, user, perm, department_id=getattr(row, "department_id", None))


async def log_activity(crm_entity_type: str, crm_entity_id: str, activity_type: str, title: str,
                       actor: dict, department_id: Optional[str] = None, body: str = "",
                       metadata: Optional[dict] = None, emit_feed: bool = True,
                       feed_verb: Optional[str] = None) -> dict:
    """Append a client-activity timeline event (Mongo) and mirror it to the global feed."""
    doc = {
        "id": new_id(), "crm_entity_type": crm_entity_type, "crm_entity_id": crm_entity_id,
        "activity_type": activity_type, "title": title, "body": body,
        "actor_id": actor.get("id"), "actor_name": actor.get("name", ""),
        "department_id": department_id, "metadata": metadata or {}, "created_at": now_iso(),
    }
    await mongo.crm_activities.insert_one(dict(doc))
    if emit_feed:
        await emit_activity(actor.get("id"), feed_verb or f"crm.{activity_type}", crm_entity_type, crm_entity_id,
                            department_id=department_id, actor_name=actor.get("name"),
                            metadata={"title": title, **(metadata or {})})
    doc.pop("_id", None)
    return doc


async def build_timeline(session: AsyncSession, crm_entity_type: str, crm_entity_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    """Unified, chronological timeline: client activities + linked meetings/tasks/approvals + stage history."""
    from sqlalchemy import select
    from app.modules.crm.models import CRMLink, CRMLeadStageHistory, CRMOppStageHistory
    from app.modules.meetings.models import Meeting
    from app.modules.approvals.models import ApprovalRequest

    events: List[Dict[str, Any]] = []

    # 1. Client activities (calls/emails/notes/status changes/...)
    acts = await mongo.crm_activities.find(
        {"crm_entity_type": crm_entity_type, "crm_entity_id": crm_entity_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(500)
    for a in acts:
        events.append({"kind": "activity", "activity_type": a.get("activity_type"), "title": a.get("title"),
                       "body": a.get("body"), "actor_id": a.get("actor_id"), "actor_name": a.get("actor_name"),
                       "at": a.get("created_at"), "ref": {"type": a.get("activity_type"), "id": a.get("id")}})

    # 2. Linked objects (meetings/tasks/approvals/notes)
    links = (await session.execute(select(CRMLink).where(
        CRMLink.crm_entity_type == crm_entity_type, CRMLink.crm_entity_id == crm_entity_id))).scalars().all()
    for ln in links:
        if ln.target_type == "meeting":
            m = (await session.execute(select(Meeting).where(Meeting.id == ln.target_id))).scalar_one_or_none()
            summary = await mongo.ai_summaries.find_one({"summary_type": "meeting", "subject_id": ln.target_id}, {"_id": 0, "narrative": 1})
            events.append({"kind": "meeting", "title": m.title if m else ln.target_id,
                           "status": m.status if m else None, "at": (m.meeting_at or m.created_at) if m else ln.created_at,
                           "summary": (summary or {}).get("narrative"), "ref": {"type": "meeting", "id": ln.target_id}})
        elif ln.target_type == "task":
            t = await mongo.tasks.find_one({"id": ln.target_id}, {"_id": 0, "title": 1, "status": 1, "due_date": 1, "created_at": 1})
            events.append({"kind": "task", "title": (t or {}).get("title", ln.target_id),
                           "status": (t or {}).get("status"), "at": (t or {}).get("created_at", ln.created_at),
                           "ref": {"type": "task", "id": ln.target_id}})
        elif ln.target_type == "approval":
            r = (await session.execute(select(ApprovalRequest).where(ApprovalRequest.id == ln.target_id))).scalar_one_or_none()
            events.append({"kind": "approval", "title": r.title if r else ln.target_id,
                           "status": r.status if r else None, "at": r.created_at if r else ln.created_at,
                           "ref": {"type": "approval", "id": ln.target_id}})
        else:
            events.append({"kind": ln.target_type, "title": ln.target_id, "at": ln.created_at,
                           "ref": {"type": ln.target_type, "id": ln.target_id}})

    # 3. Stage history (leads/opportunities)
    if crm_entity_type == "lead":
        for h in (await session.execute(select(CRMLeadStageHistory).where(CRMLeadStageHistory.lead_id == crm_entity_id))).scalars().all():
            events.append({"kind": "stage_change", "title": f"{h.from_stage or '—'} → {h.to_stage}",
                           "actor_id": h.changed_by, "at": h.changed_at, "note": h.note,
                           "ref": {"type": "stage", "id": h.id}})
    elif crm_entity_type == "opportunity":
        for h in (await session.execute(select(CRMOppStageHistory).where(CRMOppStageHistory.opportunity_id == crm_entity_id))).scalars().all():
            events.append({"kind": "stage_change", "title": f"{h.from_stage or '—'} → {h.to_stage}",
                           "actor_id": h.changed_by, "at": h.changed_at, "note": h.note,
                           "ref": {"type": "stage", "id": h.id}})

    events.sort(key=lambda e: e.get("at") or "", reverse=True)
    return events[:limit]


async def enrich_users(rows: List[dict], keys=("owner_id",)) -> None:
    ids = set()
    for r in rows:
        for k in keys:
            if r.get(k):
                ids.add(r[k])
    if not ids:
        return
    users = await mongo.users.find({"id": {"$in": list(ids)}}, {"_id": 0, "id": 1, "name": 1, "email": 1}).to_list(1000)
    by_id = {u["id"]: u for u in users}
    for r in rows:
        if r.get("owner_id"):
            r["owner_name"] = (by_id.get(r["owner_id"]) or {}).get("name")
