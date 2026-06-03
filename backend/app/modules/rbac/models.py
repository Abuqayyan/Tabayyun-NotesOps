"""RBAC ORM models: permissions, roles, role↔permission, and scoped role assignments.

Scope model (the core design): a RoleAssignment binds (user_id, role_id, scope). A scope
is global, a department, or a project. A permission is granted to a user for a resource if
they hold any assignment whose role includes the permission AND whose scope covers the
resource (global covers everything).
"""
from sqlalchemy import String, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db_postgres import Base
from app.core.utils import new_id, now_iso

SCOPE_GLOBAL = "global"
SCOPE_DEPARTMENT = "department"
SCOPE_PROJECT = "project"
SCOPE_TYPES = (SCOPE_GLOBAL, SCOPE_DEPARTMENT, SCOPE_PROJECT)


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    category: Mapped[str] = mapped_column(String(60), default="general")
    description: Mapped[str] = mapped_column(String(400), default="")


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(String(600), default="")
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)  # protected from deletion
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)
    updated_at: Mapped[str] = mapped_column(String(40), default=now_iso)


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_id", name="uq_roleperm"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    role_id: Mapped[str] = mapped_column(String(36), ForeignKey("roles.id", ondelete="CASCADE"), index=True)
    permission_id: Mapped[str] = mapped_column(String(36), ForeignKey("permissions.id", ondelete="CASCADE"), index=True)


class RoleAssignment(Base):
    __tablename__ = "role_assignments"
    __table_args__ = (UniqueConstraint("user_id", "role_id", "scope_type", "scope_id", name="uq_assignment"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(36), index=True)  # Mongo users.id
    role_id: Mapped[str] = mapped_column(String(36), ForeignKey("roles.id", ondelete="CASCADE"), index=True)
    scope_type: Mapped[str] = mapped_column(String(20), default=SCOPE_GLOBAL)  # global|department|project
    scope_id: Mapped[str | None] = mapped_column(String(36), nullable=True)    # dept/project id, null for global
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
