"""Meeting ORM models (PostgreSQL).

A meeting carries scheduling fields plus its minutes (MOM): free-text `notes` and the
structured `decisions` / `discussion_points` JSON lists. Attachments are stored as a
JSON list of {filename, url, ...} metadata (binary upload reuses the files module).
Action items are first-class rows that link back to the originating meeting AND forward
to the Mongo task they spawn (`task_id`), so each side can show the other's status.
"""
from sqlalchemy import String, Text, Integer, JSON, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db_postgres import Base
from app.core.utils import new_id, now_iso


class Meeting(Base):
    __tablename__ = "meetings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(300))
    department_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    organizer_id: Mapped[str] = mapped_column(String(36), index=True)        # Mongo users.id
    meeting_at: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)  # ISO datetime
    duration_minutes: Mapped[int] = mapped_column(Integer, default=30)
    agenda: Mapped[str] = mapped_column(Text, default="")
    # --- Minutes of meeting (MOM) ---
    notes: Mapped[str] = mapped_column(Text, default="")
    decisions: Mapped[list | None] = mapped_column(JSON, default=list)
    discussion_points: Mapped[list | None] = mapped_column(JSON, default=list)
    attachments: Mapped[list | None] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="scheduled")     # scheduled|completed|cancelled
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)
    updated_at: Mapped[str] = mapped_column(String(40), default=now_iso)


class MeetingAttendee(Base):
    __tablename__ = "meeting_attendees"
    __table_args__ = (UniqueConstraint("meeting_id", "user_id", name="uq_meeting_attendee"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    meeting_id: Mapped[str] = mapped_column(String(36), ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)             # Mongo users.id
    attendance_status: Mapped[str] = mapped_column(String(20), default="invited")  # invited|attended|declined
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)


class ActionItem(Base):
    __tablename__ = "action_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    meeting_id: Mapped[str] = mapped_column(String(36), ForeignKey("meetings.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(400))
    owner_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)  # Mongo users.id
    department_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    due_date: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open")          # open|in_progress|done|cancelled
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)  # linked Mongo task
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)
    updated_at: Mapped[str] = mapped_column(String(40), default=now_iso)
