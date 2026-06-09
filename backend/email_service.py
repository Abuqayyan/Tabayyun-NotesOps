"""SMTP email sender with template substitution.
Reads SMTP config from db.smtp_settings (singleton per workspace, scoped to user_id).
"""
import os
import logging
import aiosmtplib
from email.message import EmailMessage
from typing import Optional
from cryptography.fernet import Fernet, InvalidToken

log = logging.getLogger("opscore.email")


# Default templates (HTML + plain). Variables: {app_name}, {name}, {email}, {otp}, {actor}, {title}, {description}, {due_date}, {url}, {temp_password}, {invite_url}
DEFAULT_TEMPLATES = {
    "otp": {
        "subject_ar": "{app_name} — رمز الدخول {otp}",
        "subject_en": "{app_name} — Sign-in code {otp}",
        "html": """<!doctype html><html><body style="margin:0;background:#0a0a0a;font-family:'IBM Plex Sans Arabic',system-ui,sans-serif;color:#e5e5e5">
<div style="max-width:520px;margin:32px auto;background:#141414;border:1px solid #262626;border-radius:8px;overflow:hidden">
  <div style="padding:20px 24px;border-bottom:1px solid #262626;display:flex;align-items:center;gap:8px">
    <div style="width:24px;height:24px;background:#FF4500;border-radius:4px;display:inline-block"></div>
    <strong style="font-size:14px;letter-spacing:-0.01em">{app_name}</strong>
  </div>
  <div style="padding:32px 24px">
    <div style="font-size:11px;letter-spacing:0.12em;color:#737373;text-transform:uppercase;margin-bottom:8px">Sign-in code</div>
    <h2 style="margin:0 0 16px;font-size:22px;font-weight:500;color:#fafafa">Hi {name},</h2>
    <p style="margin:0 0 24px;font-size:14px;line-height:1.7;color:#a3a3a3">Use this code to complete your sign-in. It expires in 10 minutes.</p>
    <div style="font-family:'JetBrains Mono',monospace;font-size:36px;letter-spacing:0.4em;font-weight:600;color:#FF4500;background:#0a0a0a;border:1px solid #262626;padding:20px;text-align:center;border-radius:6px;margin-bottom:24px">{otp}</div>
    <p style="margin:0;font-size:12px;color:#737373">If you didn't request this code, ignore this email.</p>
  </div>
</div></body></html>""",
    },
    "invite": {
        "subject_ar": "{actor} يدعوك إلى {app_name}",
        "subject_en": "{actor} invited you to {app_name}",
        "html": """<!doctype html><html><body style="margin:0;background:#0a0a0a;font-family:'IBM Plex Sans Arabic',system-ui,sans-serif;color:#e5e5e5">
<div style="max-width:520px;margin:32px auto;background:#141414;border:1px solid #262626;border-radius:8px;overflow:hidden">
  <div style="padding:20px 24px;border-bottom:1px solid #262626">
    <strong style="font-size:14px">{app_name}</strong>
  </div>
  <div style="padding:32px 24px">
    <div style="font-size:11px;letter-spacing:0.12em;color:#737373;text-transform:uppercase;margin-bottom:8px">Invitation</div>
    <h2 style="margin:0 0 16px;font-size:22px;font-weight:500;color:#fafafa">{actor} invited you</h2>
    <p style="margin:0 0 12px;font-size:14px;line-height:1.7;color:#a3a3a3">You've been invited to join <strong style="color:#fafafa">{app_name}</strong> as a teammate.</p>
    <p style="margin:0 0 12px;font-size:13px;color:#a3a3a3">Your temporary password:</p>
    <div style="font-family:'JetBrains Mono',monospace;font-size:18px;color:#FF4500;background:#0a0a0a;border:1px solid #262626;padding:14px;border-radius:6px;margin-bottom:24px">{temp_password}</div>
    <a href="{invite_url}" style="display:inline-block;background:#FF4500;color:white;text-decoration:none;padding:12px 24px;border-radius:6px;font-weight:500;font-size:14px">Accept & sign in</a>
    <p style="margin:24px 0 0;font-size:12px;color:#737373">You'll be asked to set your own password after first login.</p>
  </div>
</div></body></html>""",
    },
    "task_assigned": {
        "subject_ar": "تم تعيين مهمة لك من {actor}: {title}",
        "subject_en": "{actor} assigned you a task: {title}",
        "html": """<!doctype html><html><body style="margin:0;background:#0a0a0a;font-family:'IBM Plex Sans Arabic',system-ui,sans-serif;color:#e5e5e5">
<div style="max-width:560px;margin:32px auto;background:#141414;border:1px solid #262626;border-radius:8px;overflow:hidden">
  <div style="padding:20px 24px;border-bottom:1px solid #262626">
    <strong style="font-size:14px">{app_name}</strong>
  </div>
  <div style="padding:32px 24px">
    <div style="font-size:11px;letter-spacing:0.12em;color:#737373;text-transform:uppercase;margin-bottom:8px">Task assigned</div>
    <h2 style="margin:0 0 8px;font-size:22px;font-weight:500;color:#fafafa">{title}</h2>
    <p style="margin:0 0 20px;font-size:13px;color:#a3a3a3">Assigned to you by <strong style="color:#fafafa">{actor}</strong></p>
    <div style="background:#0a0a0a;border:1px solid #262626;padding:16px;border-radius:6px;margin-bottom:24px;font-size:14px;color:#d4d4d4;line-height:1.7">{description}</div>
    <div style="font-size:12px;color:#737373;margin-bottom:24px">Due: <strong style="color:#fafafa">{due_date}</strong></div>
    <a href="{url}" style="display:inline-block;background:#FF4500;color:white;text-decoration:none;padding:12px 24px;border-radius:6px;font-weight:500;font-size:14px">Open task</a>
  </div>
</div></body></html>""",
    },
    "task_reminder": {
        "subject_ar": "تذكير: {title}",
        "subject_en": "Reminder: {title}",
        "html": """<!doctype html><html><body style="margin:0;background:#0a0a0a;font-family:'IBM Plex Sans Arabic',system-ui,sans-serif;color:#e5e5e5">
<div style="max-width:560px;margin:32px auto;background:#141414;border:1px solid #262626;border-radius:8px;overflow:hidden">
  <div style="padding:20px 24px;border-bottom:1px solid #262626">
    <strong style="font-size:14px">{app_name}</strong>
  </div>
  <div style="padding:32px 24px">
    <div style="font-size:11px;letter-spacing:0.12em;color:#737373;text-transform:uppercase;margin-bottom:8px">Reminder</div>
    <h2 style="margin:0 0 16px;font-size:22px;font-weight:500;color:#fafafa">{title}</h2>
    <div style="background:#0a0a0a;border:1px solid #262626;padding:16px;border-radius:6px;margin-bottom:24px;font-size:14px;color:#d4d4d4;line-height:1.7">{description}</div>
    <a href="{url}" style="display:inline-block;background:#FF4500;color:white;text-decoration:none;padding:12px 24px;border-radius:6px;font-weight:500;font-size:14px">Open in {app_name}</a>
  </div>
</div></body></html>""",
    },
}


def decrypt_value(fernet: Fernet, encrypted: Optional[str]) -> Optional[str]:
    if not encrypted:
        return None
    try:
        return fernet.decrypt(encrypted.encode()).decode()
    except InvalidToken:
        return None


def render(template: str, variables: dict) -> str:
    """Safe placeholder substitution. Missing vars become empty strings."""
    try:
        return template.format_map({**{k: "" for k in [
            "app_name", "name", "email", "otp", "actor", "title", "description",
            "due_date", "url", "temp_password", "invite_url"
        ]}, **variables})
    except Exception as e:
        log.error(f"Template render error: {e}")
        return template


async def send_email(
    smtp_cfg: dict,
    to_email: str,
    subject: str,
    html_body: str,
    plain_body: Optional[str] = None,
    from_name: Optional[str] = None,
) -> tuple[bool, str]:
    """Sends an email via SMTP. Returns (ok, message)."""
    if not smtp_cfg or not smtp_cfg.get("host"):
        return False, "SMTP not configured"

    msg = EmailMessage()
    from_email = smtp_cfg.get("from_email") or smtp_cfg.get("username")
    msg["From"] = f"{from_name} <{from_email}>" if from_name else from_email
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(plain_body or "View this email in HTML.")
    msg.add_alternative(html_body, subtype="html")

    try:
        await aiosmtplib.send(
            msg,
            hostname=smtp_cfg["host"],
            port=int(smtp_cfg.get("port", 587)),
            username=smtp_cfg.get("username") or None,
            password=smtp_cfg.get("password") or None,
            use_tls=bool(smtp_cfg.get("use_tls", False)),  # SMTPS implicit TLS (port 465)
            start_tls=bool(smtp_cfg.get("start_tls", True)) and not bool(smtp_cfg.get("use_tls", False)),
            timeout=20,
        )
        return True, "sent"
    except Exception as e:
        log.error(f"SMTP send failed: {e}")
        return False, str(e)[:200]
