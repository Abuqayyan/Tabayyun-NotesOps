"""Audit log read API (permission-gated): search, filters, and CSV/XLSX export."""
from typing import Optional

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db_postgres import get_session
from app.shared.export_util import tabular_response
from app.modules.audit.models import AuditLog
from app.modules.rbac.resolver import require_permission

router = APIRouter()


def _filtered_query(action, entity_type, actor_user_id, q, date_from, date_to):
    query = select(AuditLog).order_by(AuditLog.created_at.desc())
    if action:
        query = query.where(AuditLog.action == action)
    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)
    if actor_user_id:
        query = query.where(AuditLog.actor_user_id == actor_user_id)
    if q:
        like = f"%{q}%"
        query = query.where(or_(AuditLog.action.ilike(like), AuditLog.actor_name.ilike(like),
                                AuditLog.entity_type.ilike(like), AuditLog.entity_id.ilike(like)))
    if date_from:
        query = query.where(AuditLog.created_at >= date_from)
    if date_to:
        query = query.where(AuditLog.created_at <= date_to)
    return query


def _row(a: AuditLog) -> dict:
    return {"id": a.id, "actor_user_id": a.actor_user_id, "actor_name": a.actor_name, "action": a.action,
            "entity_type": a.entity_type, "entity_id": a.entity_id, "before": a.before, "after": a.after,
            "ip": a.ip, "created_at": a.created_at}


@router.get("/audit")
async def list_audit(
    action: Optional[str] = None,
    entity_type: Optional[str] = None,
    actor_user_id: Optional[str] = None,
    q: Optional[str] = None,                # free-text search across action/actor/entity
    date_from: Optional[str] = None,        # ISO; created_at >= date_from
    date_to: Optional[str] = None,
    limit: int = 100,
    user=Depends(require_permission("audit.view")),
    session: AsyncSession = Depends(get_session),
):
    query = _filtered_query(action, entity_type, actor_user_id, q, date_from, date_to)
    rows = (await session.execute(query.limit(min(max(limit, 1), 1000)))).scalars().all()
    return [_row(a) for a in rows]


@router.get("/audit/export")
async def export_audit(
    request: Request, format: str = "csv",
    action: Optional[str] = None, entity_type: Optional[str] = None, actor_user_id: Optional[str] = None,
    q: Optional[str] = None, date_from: Optional[str] = None, date_to: Optional[str] = None,
    user=Depends(require_permission("audit.view")), session: AsyncSession = Depends(get_session),
):
    query = _filtered_query(action, entity_type, actor_user_id, q, date_from, date_to)
    rows = [_row(a) for a in (await session.execute(query.limit(10000))).scalars().all()]
    headers = ["id", "created_at", "actor_name", "actor_user_id", "action", "entity_type", "entity_id", "ip"]
    return tabular_response(format, "tabayyun_audit", headers, rows)
