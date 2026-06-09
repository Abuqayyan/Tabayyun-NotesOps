"""Report ORM model (PostgreSQL) — the reporting foundation.

Phase 2 stores computed (non-AI) metrics in `data`. The `summary` column is reserved for
the Phase 3 AI narrative and is intentionally left empty here. A report is an immutable
snapshot of a (scope, period) so trends can be compared over time.
"""
from sqlalchemy import String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db_postgres import Base
from app.core.utils import new_id, now_iso


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    report_type: Mapped[str] = mapped_column(String(40), index=True)   # weekly_department|monthly_department|weekly_company|monthly_company|executive
    scope_type: Mapped[str] = mapped_column(String(20), default="company")  # company|department
    department_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    period_start: Mapped[str] = mapped_column(String(10))               # YYYY-MM-DD
    period_end: Mapped[str] = mapped_column(String(10))
    data: Mapped[dict | None] = mapped_column(JSON, default=dict)       # computed metrics
    summary: Mapped[str] = mapped_column(Text, default="")              # reserved for Phase 3 AI narrative
    status: Mapped[str] = mapped_column(String(20), default="generated")  # generated|draft
    generated_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso, index=True)
