"""Daily update ORM model (PostgreSQL system of record).

One row per (user, day) enforced by a unique constraint so an employee submits a
single update per day and edits it in place. department_id is denormalised from the
employee's profile at submit time so reporting/aggregation stays a single-store query.
"""
from sqlalchemy import String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db_postgres import Base
from app.core.utils import new_id, now_iso


class DailyUpdate(Base):
    __tablename__ = "daily_updates"
    __table_args__ = (UniqueConstraint("user_id", "update_date", name="uq_dailyupdate_user_day"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(36), index=True)            # Mongo users.id (Created By)
    department_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    update_date: Mapped[str] = mapped_column(String(10), index=True)        # YYYY-MM-DD
    today: Mapped[str] = mapped_column(Text, default="")                    # completed work
    tomorrow: Mapped[str] = mapped_column(Text, default="")                 # planned work
    blockers: Mapped[str] = mapped_column(Text, default="")                 # issues / dependencies
    status: Mapped[str] = mapped_column(String(20), default="submitted")    # submitted|draft
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)
    updated_at: Mapped[str] = mapped_column(String(40), default=now_iso)
