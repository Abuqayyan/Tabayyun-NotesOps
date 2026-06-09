"""Audit recording helper. Callers add within their own session/transaction."""
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditLog


async def record_audit(
    session: AsyncSession,
    actor: Optional[dict],
    action: str,
    entity_type: str,
    entity_id: Optional[str] = None,
    before: Optional[dict] = None,
    after: Optional[dict] = None,
    ip: Optional[str] = None,
) -> None:
    session.add(AuditLog(
        actor_user_id=(actor or {}).get("id"),
        actor_name=(actor or {}).get("name", "") or "",
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before=before,
        after=after,
        ip=ip,
    ))
