"""Settings & Configuration Center (Module 9).

Centralizes company branding, notification, security, and CRM-default settings in one
permission-controlled place (settings.manage). Reads are available to any authenticated
user (so the UI can theme itself / read defaults); writes require settings.manage and are
audited. Reminder/escalation + SMTP settings keep their existing endpoints (linked here).
"""
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel

from app.core.config import APP_NAME
from app.core.db_mongo import db
from app.core.db_postgres import get_session
from app.core.security import get_current_user
from app.core.utils import now_iso
from app.modules.rbac.resolver import ensure_permission
from app.modules.audit.service import record_audit

router = APIRouter()

_SECTIONS = {
    "company": {"name": "Tabayyun NotesOps", "logo_url": "", "primary_color": "#FF4500",
                "locale": "en", "timezone": "UTC"},
    "notifications": {"email_enabled": True, "in_app_enabled": True, "digest_frequency": "weekly"},
    "security": {"session_hours": 6, "jwt_expire_days": 30, "password_min_length": 8,
                 "otp_required": True, "otp_ttl_minutes": 10},
    "crm": {"default_lead_stage": "new", "default_lead_probability": 0,
            "default_opportunity_stage": "prospecting", "currency": "USD"},
}


class SettingsIn(BaseModel):
    values: Dict[str, Any]


async def _get_section(section: str) -> dict:
    defaults = _SECTIONS[section]
    row = await db.company_settings.find_one({"id": section}, {"_id": 0}) or {}
    merged = {**defaults}
    merged.update({k: v for k, v in row.items() if k in defaults})
    return merged


@router.get("/settings/center")
async def get_all_settings(user=Depends(get_current_user)):
    """All configuration sections (defaults overlaid with stored overrides)."""
    out = {s: await _get_section(s) for s in _SECTIONS}
    out["app_name"] = APP_NAME
    out["sections"] = list(_SECTIONS)
    return out


@router.get("/settings/center/{section}")
async def get_section(section: str, user=Depends(get_current_user)):
    if section not in _SECTIONS:
        raise HTTPException(404, f"Unknown section. Allowed: {list(_SECTIONS)}")
    return await _get_section(section)


@router.put("/settings/center/{section}")
async def update_section(section: str, body: SettingsIn, request: Request,
                         user=Depends(get_current_user), session=Depends(get_session)):
    if section not in _SECTIONS:
        raise HTTPException(404, f"Unknown section. Allowed: {list(_SECTIONS)}")
    await ensure_permission(session, user, "settings.manage")
    allowed = set(_SECTIONS[section])
    upd = {k: v for k, v in (body.values or {}).items() if k in allowed}
    if not upd:
        raise HTTPException(400, f"No valid keys for '{section}'. Allowed: {sorted(allowed)}")
    upd["updated_at"] = now_iso()
    upd["updated_by"] = user["id"]
    await db.company_settings.update_one(
        {"id": section}, {"$set": upd, "$setOnInsert": {"id": section, "created_at": now_iso()}}, upsert=True)
    await record_audit(session, user, "settings.update", "settings", section, after=upd,
                       ip=request.client.host if request.client else None)
    await session.commit()
    return await _get_section(section)
