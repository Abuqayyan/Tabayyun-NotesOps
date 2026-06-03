"""Workspace settings: SMTP configuration + editable email templates."""
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, EmailStr

from app.core.config import FERNET, APP_NAME
from app.core.db_mongo import db
from app.core.security import get_current_user
from app.core.utils import now_iso, resolve_lang
from app.shared.email import get_smtp_config, send_email, DEFAULT_TEMPLATES

router = APIRouter()


class SMTPSettingsIn(BaseModel):
    host: Optional[str] = None
    port: Optional[int] = 587
    username: Optional[str] = None
    password: Optional[str] = None  # plain; encrypted on save
    from_email: Optional[str] = None
    use_tls: Optional[bool] = False
    start_tls: Optional[bool] = True
    enabled: Optional[bool] = True


class EmailTemplateIn(BaseModel):
    key: str
    subject_ar: Optional[str] = None
    subject_en: Optional[str] = None
    html: Optional[str] = None


class TestEmailIn(BaseModel):
    to: EmailStr


@router.get("/settings/smtp")
async def get_smtp_settings(user=Depends(get_current_user)):
    s = await db.smtp_settings.find_one({"id": "default"}, {"_id": 0}) or {}
    s.pop("password_encrypted", None)
    s.pop("password", None)
    return {
        "host": s.get("host", ""),
        "port": s.get("port", 587),
        "username": s.get("username", ""),
        "from_email": s.get("from_email", ""),
        "use_tls": s.get("use_tls", False),
        "start_tls": s.get("start_tls", True),
        "enabled": s.get("enabled", True),
        "has_password": bool(s.get("has_password")),
        "updated_at": s.get("updated_at"),
    }


@router.put("/settings/smtp")
async def update_smtp_settings(body: SMTPSettingsIn, user=Depends(get_current_user)):
    upd: Dict[str, Any] = {"updated_at": now_iso()}
    for k in ("host", "port", "username", "from_email", "use_tls", "start_tls", "enabled"):
        v = getattr(body, k, None)
        if v is not None:
            upd[k] = v
    if body.password is not None:
        if body.password == "":
            upd["password_encrypted"] = None
            upd["has_password"] = False
        else:
            upd["password_encrypted"] = FERNET.encrypt(body.password.encode()).decode()
            upd["has_password"] = True
    await db.smtp_settings.update_one(
        {"id": "default"},
        {"$set": upd, "$setOnInsert": {"id": "default", "created_at": now_iso()}},
        upsert=True,
    )
    return await get_smtp_settings(user)


@router.post("/settings/smtp/test")
async def test_smtp(body: TestEmailIn, request: Request, user=Depends(get_current_user)):
    cfg = await get_smtp_config()
    if not cfg or not cfg.get("host"):
        raise HTTPException(400, "SMTP not configured")
    lang = resolve_lang(request.headers.get("X-Lang"))
    subject = "OpsCore — SMTP test" if lang == "en" else "OpsCore — اختبار SMTP"
    html = f"<div style='font-family:sans-serif;padding:24px'><h2>SMTP works</h2><p>This is a test message from {APP_NAME}. Sent at {now_iso()}.</p></div>"
    ok, msg = await send_email(cfg, body.to, subject, html, from_name=APP_NAME)
    return {"ok": ok, "detail": msg}


@router.get("/settings/email-templates")
async def list_email_templates(user=Depends(get_current_user)):
    out = {}
    for key, default in DEFAULT_TEMPLATES.items():
        row = await db.email_templates.find_one({"key": key}, {"_id": 0}) or {}
        out[key] = {
            "key": key,
            "subject_ar": row.get("subject_ar", default.get("subject_ar", "")),
            "subject_en": row.get("subject_en", default.get("subject_en", "")),
            "html": row.get("html", default.get("html", "")),
            "is_default": not bool(row),
        }
    return out


@router.put("/settings/email-templates")
async def update_email_template(body: EmailTemplateIn, user=Depends(get_current_user)):
    if body.key not in DEFAULT_TEMPLATES:
        raise HTTPException(400, f"Unknown template '{body.key}'")
    upd = {"key": body.key, "updated_at": now_iso()}
    for k in ("subject_ar", "subject_en", "html"):
        v = getattr(body, k, None)
        if v is not None:
            upd[k] = v
    await db.email_templates.update_one(
        {"key": body.key},
        {"$set": upd, "$setOnInsert": {"created_at": now_iso()}},
        upsert=True,
    )
    return upd


@router.post("/settings/email-templates/{key}/reset")
async def reset_email_template(key: str, user=Depends(get_current_user)):
    if key not in DEFAULT_TEMPLATES:
        raise HTTPException(400, "Unknown template")
    await db.email_templates.delete_one({"key": key})
    return {"ok": True, "key": key}
