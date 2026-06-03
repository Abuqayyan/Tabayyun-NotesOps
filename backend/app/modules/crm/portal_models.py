"""Client Portal foundation (Module 10) — SCHEMA ONLY.

Future-ready entities for an external client portal. No routers, no endpoints, no frontend
in Phase 4 — these tables are created by create_all so later phases can build on a stable
schema. Intentionally minimal.
"""
from sqlalchemy import String, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db_postgres import Base
from app.core.utils import new_id, now_iso


class ClientAccount(Base):
    __tablename__ = "client_accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("crm_companies.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(40), default="active")  # active|suspended|closed
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)


class PortalUser(Base):
    __tablename__ = "portal_users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    client_account_id: Mapped[str] = mapped_column(String(36), ForeignKey("client_accounts.id", ondelete="CASCADE"), index=True)
    contact_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("crm_contacts.id"), nullable=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    full_name: Mapped[str] = mapped_column(String(255), default="")
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)


class SharedDocument(Base):
    __tablename__ = "shared_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    client_account_id: Mapped[str] = mapped_column(String(36), ForeignKey("client_accounts.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(400))
    url: Mapped[str] = mapped_column(String(600), default="")
    shared_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)


class ClientRequest(Base):
    __tablename__ = "client_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    client_account_id: Mapped[str] = mapped_column(String(36), ForeignKey("client_accounts.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40), default="open")  # open|in_progress|resolved|closed
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)


class ClientTicket(Base):
    __tablename__ = "client_tickets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    client_account_id: Mapped[str] = mapped_column(String(36), ForeignKey("client_accounts.id", ondelete="CASCADE"), index=True)
    subject: Mapped[str] = mapped_column(String(300))
    priority: Mapped[str] = mapped_column(String(20), default="medium")  # low|medium|high|urgent
    status: Mapped[str] = mapped_column(String(40), default="open")
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)
