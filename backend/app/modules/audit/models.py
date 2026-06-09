"""Audit log ORM model (PostgreSQL). Append-only; before/after stored as JSON."""
from sqlalchemy import String, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db_postgres import Base
from app.core.utils import new_id, now_iso


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    actor_name: Mapped[str] = mapped_column(String(160), default="")
    action: Mapped[str] = mapped_column(String(80), index=True)        # e.g. department.create
    entity_type: Mapped[str] = mapped_column(String(60), index=True)   # department|role|employee|role_assignment
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso, index=True)
