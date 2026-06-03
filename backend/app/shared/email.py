"""SMTP/email orchestration shared across modules.

Low-level send + templates live in the existing top-level email_service module; this
layer adds DB-backed config resolution, template overrides, and templated send.
"""
from typing import Optional
from cryptography.fernet import InvalidToken
from fastapi import Request

from app.core.config import FERNET, APP_NAME, PUBLIC_APP_URL
from app.core.db_mongo import db
# email_service.py is a top-level backend module (kept in place for Phase 0).
from email_service import DEFAULT_TEMPLATES, send_email, render

__all__ = [
    "DEFAULT_TEMPLATES", "send_email", "render",
    "get_smtp_config", "get_email_template", "send_templated_email", "resolve_app_url",
]


async def get_smtp_config() -> Optional[dict]:
    """Returns the active SMTP config (singleton document) with password decrypted."""
    s = await db.smtp_settings.find_one({"id": "default"}, {"_id": 0})
    if not s or not s.get("enabled", True):
        return None
    cfg = dict(s)
    if cfg.get("password_encrypted"):
        try:
            cfg["password"] = FERNET.decrypt(cfg["password_encrypted"].encode()).decode()
        except InvalidToken:
            cfg["password"] = None
    return cfg


async def get_email_template(key: str) -> dict:
    """Returns active template (DB override merged over DEFAULT_TEMPLATES)."""
    row = await db.email_templates.find_one({"key": key}, {"_id": 0})
    default = DEFAULT_TEMPLATES.get(key, {})
    if not row:
        return default
    merged = dict(default)
    for k in ("subject_ar", "subject_en", "html"):
        if row.get(k):
            merged[k] = row[k]
    return merged


async def send_templated_email(
    template_key: str,
    to_email: str,
    variables: dict,
    lang: str = "ar",
) -> tuple[bool, str]:
    """Renders a template and sends via configured SMTP."""
    cfg = await get_smtp_config()
    if not cfg or not cfg.get("host"):
        return False, "SMTP not configured"
    tpl = await get_email_template(template_key)
    if not tpl:
        return False, f"Template '{template_key}' missing"
    variables = {"app_name": APP_NAME, **variables}
    subject_key = "subject_ar" if lang == "ar" else "subject_en"
    subject = render(tpl.get(subject_key, tpl.get("subject_en", "")), variables)
    html = render(tpl.get("html", ""), variables)
    return await send_email(cfg, to_email, subject, html, from_name=APP_NAME)


async def resolve_app_url(request: Optional[Request] = None) -> str:
    if PUBLIC_APP_URL:
        return PUBLIC_APP_URL
    if request:
        return f"{request.url.scheme}://{request.headers.get('host', '')}"
    return ""
