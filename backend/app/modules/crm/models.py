"""CRM relational models (PostgreSQL system of record).

Cross-DB compatible (string UUID PKs, ISO timestamps, JSON). owner_id references Mongo
users.id; department_id references departments.id — both by value (hybrid model, no
cross-store FKs). The polymorphic `crm_links` table connects any CRM entity to existing
Company-OS objects (meetings/tasks/approvals/notes) WITHOUT altering those modules.
"""
from sqlalchemy import String, Text, Integer, Float, JSON, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db_postgres import Base
from app.core.utils import new_id, now_iso

# Lead lifecycle stages (Module 3)
LEAD_STAGES = ["new", "contacted", "qualified", "proposal", "negotiation", "won", "lost"]
# Opportunity pipeline stages (Module 4)
OPP_STAGES = ["prospecting", "qualification", "proposal", "negotiation", "won", "lost"]
CRM_ENTITY_TYPES = ("company", "contact", "lead", "opportunity")
LINK_TARGET_TYPES = ("meeting", "task", "approval", "note")


class CRMCompany(Base):
    __tablename__ = "crm_companies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(255), index=True)
    industry: Mapped[str] = mapped_column(String(120), default="")
    website: Mapped[str] = mapped_column(String(255), default="")
    address: Mapped[str] = mapped_column(String(400), default="")
    country: Mapped[str] = mapped_column(String(80), default="")
    city: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(40), default="prospect")  # prospect|active|inactive|churned
    owner_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)        # Mongo users.id
    department_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list | None] = mapped_column(JSON, default=list)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)
    updated_at: Mapped[str] = mapped_column(String(40), default=now_iso)


class CRMContact(Base):
    __tablename__ = "crm_contacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    full_name: Mapped[str] = mapped_column(String(255), index=True)
    email: Mapped[str] = mapped_column(String(255), default="", index=True)
    phone: Mapped[str] = mapped_column(String(60), default="")
    position: Mapped[str] = mapped_column(String(160), default="")
    company_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("crm_companies.id"), nullable=True, index=True)
    department_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)  # department owner
    owner_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list | None] = mapped_column(JSON, default=list)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)
    updated_at: Mapped[str] = mapped_column(String(40), default=now_iso)


class CRMLead(Base):
    __tablename__ = "crm_leads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(255), default="")
    source: Mapped[str] = mapped_column(String(120), default="")
    value: Mapped[float] = mapped_column(Float, default=0.0)
    probability: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    stage: Mapped[str] = mapped_column(String(40), default="new", index=True)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)  # open|won|lost
    owner_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    department_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    company_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("crm_companies.id"), nullable=True, index=True)
    contact_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("crm_contacts.id"), nullable=True, index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    converted_opportunity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)  # set on conversion
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso, index=True)
    updated_at: Mapped[str] = mapped_column(String(40), default=now_iso)


class CRMLeadStageHistory(Base):
    __tablename__ = "crm_lead_stage_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    lead_id: Mapped[str] = mapped_column(String(36), ForeignKey("crm_leads.id", ondelete="CASCADE"), index=True)
    from_stage: Mapped[str | None] = mapped_column(String(40), nullable=True)
    to_stage: Mapped[str] = mapped_column(String(40))
    note: Mapped[str | None] = mapped_column(String(400), nullable=True)
    changed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    changed_at: Mapped[str] = mapped_column(String(40), default=now_iso)


class CRMOpportunity(Base):
    __tablename__ = "crm_opportunities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(255), index=True)
    company_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("crm_companies.id"), nullable=True, index=True)
    contact_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("crm_contacts.id"), nullable=True, index=True)
    expected_revenue: Mapped[float] = mapped_column(Float, default=0.0)
    probability: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    expected_close_date: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    stage: Mapped[str] = mapped_column(String(40), default="prospecting", index=True)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)  # open|won|lost
    owner_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    department_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    source_lead_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso, index=True)
    updated_at: Mapped[str] = mapped_column(String(40), default=now_iso)


class CRMOppStageHistory(Base):
    __tablename__ = "crm_opp_stage_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    opportunity_id: Mapped[str] = mapped_column(String(36), ForeignKey("crm_opportunities.id", ondelete="CASCADE"), index=True)
    from_stage: Mapped[str | None] = mapped_column(String(40), nullable=True)
    to_stage: Mapped[str] = mapped_column(String(40))
    note: Mapped[str | None] = mapped_column(String(400), nullable=True)
    changed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    changed_at: Mapped[str] = mapped_column(String(40), default=now_iso)


class CRMLink(Base):
    """Polymorphic link: a CRM entity <-> an existing Company-OS object (meeting/task/...)."""
    __tablename__ = "crm_links"
    __table_args__ = (
        UniqueConstraint("crm_entity_type", "crm_entity_id", "target_type", "target_id", name="uq_crmlink"),
        Index("ix_crmlink_entity", "crm_entity_type", "crm_entity_id"),
        Index("ix_crmlink_target", "target_type", "target_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    crm_entity_type: Mapped[str] = mapped_column(String(20))   # company|contact|lead|opportunity
    crm_entity_id: Mapped[str] = mapped_column(String(36))
    target_type: Mapped[str] = mapped_column(String(20))       # meeting|task|approval|note
    target_id: Mapped[str] = mapped_column(String(36))
    department_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)
