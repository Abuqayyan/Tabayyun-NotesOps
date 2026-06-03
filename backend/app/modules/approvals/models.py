"""Approval workflow ORM models (PostgreSQL — needs transactional integrity).

A template declares ordered steps whose approver is resolved BY RULE, not a fixed person
(manager_of_requester / department_lead / role / user). On submission the engine snapshots
the steps into per-request instances and resolves the concrete approver for the active step
from the live org structure (employees.manager_id reporting chain) and RBAC roles.
"""
from sqlalchemy import String, Text, Integer, Boolean, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db_postgres import Base
from app.core.utils import new_id, now_iso

# Approver resolution rules for a step.
APPROVER_MANAGER = "manager"                 # direct manager of the requester
APPROVER_SKIP_LEVEL = "manager_of_manager"   # the requester's manager's manager
APPROVER_DEPARTMENT_LEAD = "department_lead"  # lead_user_id of the request's department
APPROVER_ROLE = "role"                       # any user holding role <approver_value>
APPROVER_USER = "user"                       # a specific user <approver_value>
APPROVER_TYPES = (APPROVER_MANAGER, APPROVER_SKIP_LEVEL, APPROVER_DEPARTMENT_LEAD, APPROVER_ROLE, APPROVER_USER)

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_CANCELLED = "cancelled"


class ApprovalTemplate(Base):
    __tablename__ = "approval_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(600), default="")
    category: Mapped[str] = mapped_column(String(60), default="generic")  # leave|purchase|budget|hiring|generic
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)
    updated_at: Mapped[str] = mapped_column(String(40), default=now_iso)


class ApprovalTemplateStep(Base):
    __tablename__ = "approval_template_steps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    template_id: Mapped[str] = mapped_column(String(36), ForeignKey("approval_templates.id", ondelete="CASCADE"), index=True)
    step_order: Mapped[int] = mapped_column(Integer, default=1)
    name: Mapped[str] = mapped_column(String(120), default="")          # label e.g. "Manager", "Director", "CEO"
    approver_type: Mapped[str] = mapped_column(String(40), default=APPROVER_MANAGER)
    approver_value: Mapped[str | None] = mapped_column(String(120), nullable=True)  # role_id/user_id depending on type


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    template_id: Mapped[str] = mapped_column(String(36), ForeignKey("approval_templates.id"), index=True)
    requester_id: Mapped[str] = mapped_column(String(36), index=True)   # Mongo users.id
    department_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(300), default="")
    status: Mapped[str] = mapped_column(String(20), default=STATUS_PENDING, index=True)
    current_step: Mapped[int] = mapped_column(Integer, default=1)
    form_data: Mapped[dict | None] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso, index=True)
    updated_at: Mapped[str] = mapped_column(String(40), default=now_iso)
    decided_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class ApprovalStep(Base):
    __tablename__ = "approval_steps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    request_id: Mapped[str] = mapped_column(String(36), ForeignKey("approval_requests.id", ondelete="CASCADE"), index=True)
    step_order: Mapped[int] = mapped_column(Integer, default=1)
    name: Mapped[str] = mapped_column(String(120), default="")
    approver_type: Mapped[str] = mapped_column(String(40), default=APPROVER_MANAGER)
    approver_value: Mapped[str | None] = mapped_column(String(120), nullable=True)
    approver_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)  # resolved concrete approver
    status: Mapped[str] = mapped_column(String(20), default=STATUS_PENDING)  # pending|approved|rejected|skipped
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    decided_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    activated_at: Mapped[str | None] = mapped_column(String(40), nullable=True)  # when it became the active step (SLA anchor)
