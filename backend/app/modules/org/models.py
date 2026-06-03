"""Organization ORM models (PostgreSQL system of record).

Cross-DB compatible (Postgres + SQLite for tests): string UUID PKs, ISO-string
timestamps, JSON columns. `user_id`/`lead_user_id` reference the Mongo `users.id`
by value (the hybrid model uses UUID references, not cross-store FKs).
"""
from sqlalchemy import String, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db_postgres import Base
from app.core.utils import new_id, now_iso


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    description: Mapped[str] = mapped_column(String(1000), default="")
    parent_department_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("departments.id"), nullable=True)
    lead_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)  # Mongo users.id
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)
    updated_at: Mapped[str] = mapped_column(String(40), default=now_iso)


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)  # Mongo users.id
    position: Mapped[str] = mapped_column(String(160), default="")
    primary_department_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("departments.id"), nullable=True, index=True)
    manager_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("employees.id"), nullable=True)  # reporting line
    employment_status: Mapped[str] = mapped_column(String(40), default="active")  # active|on_leave|terminated
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)
    updated_at: Mapped[str] = mapped_column(String(40), default=now_iso)


class DepartmentMember(Base):
    __tablename__ = "department_members"
    __table_args__ = (UniqueConstraint("department_id", "user_id", name="uq_deptmember"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    department_id: Mapped[str] = mapped_column(String(36), ForeignKey("departments.id"), index=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)  # Mongo users.id
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)
