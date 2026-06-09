"""Authentication routes: register, login (+ OTP 2FA), password change, invite acceptance."""
import logging
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field, EmailStr

from app.core.config import (
    ALLOW_REGISTRATION, OTP_TTL_MINUTES, OTP_MAX_ATTEMPTS, SESSION_HOURS, APP_NAME,
)
from app.core.db_mongo import db
from app.core.security import pwd_context, make_session_token, get_current_user
from app.core.utils import now_iso, new_id, resolve_lang
from app.shared.email import get_smtp_config, get_email_template, send_email, render
from app.shared.rate_limit import limiter, LIMIT_LOGIN, LIMIT_OTP, LIMIT_PASSWORD
from security_utils import generate_otp, now_utc

log = logging.getLogger("opscore.auth")
router = APIRouter()


# ---- Models ----
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: str


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class OTPVerifyIn(BaseModel):
    otp_id: str
    code: str = Field(min_length=4, max_length=8)


class OTPResendIn(BaseModel):
    otp_id: str


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


class AcceptInviteIn(BaseModel):
    token: str
    temp_password: str


# ---- Routes ----
@router.post("/auth/register")
@limiter.limit(LIMIT_LOGIN)
async def register(body: RegisterIn, request: Request):
    if not ALLOW_REGISTRATION:
        raise HTTPException(403, "Public registration is disabled. Ask an admin to invite you.")
    existing = await db.users.find_one({"email": body.email.lower()})
    if existing:
        raise HTTPException(400, "Email already registered")
    user_id = new_id()
    doc = {
        "id": user_id,
        "email": body.email.lower(),
        "name": body.name,
        "password_hash": pwd_context.hash(body.password),
        "avatar_url": None,
        "created_at": now_iso(),
        "must_change_password": False,
        "is_admin": True,  # first-registered is admin
    }
    await db.users.insert_one(doc)
    token = make_session_token(user_id)
    return {"token": token, "user": {k: v for k, v in doc.items() if k not in ("_id", "password_hash")}}


@router.post("/auth/login")
@limiter.limit(LIMIT_LOGIN)
async def login(body: LoginIn, request: Request):
    user = await db.users.find_one({"email": body.email.lower()})
    if not user or not pwd_context.verify(body.password, user["password_hash"]):
        # generic message; do not leak which factor failed
        raise HTTPException(401, "Invalid credentials")

    # Rate limit OTP requests per user (max 5 active OTPs / 10 min)
    cutoff = now_utc() - timedelta(minutes=OTP_TTL_MINUTES)
    recent_count = await db.otps.count_documents({
        "user_id": user["id"],
        "created_at": {"$gte": cutoff.isoformat()},
    })
    if recent_count >= OTP_MAX_ATTEMPTS:
        raise HTTPException(429, "Too many sign-in attempts. Try again later.")

    # If SMTP not configured, allow direct login without OTP (single-user dev mode)
    smtp_cfg = await get_smtp_config()
    if not smtp_cfg or not smtp_cfg.get("host"):
        token = make_session_token(user["id"])
        u = {k: v for k, v in user.items() if k not in ("_id", "password_hash")}
        return {"token": token, "user": u, "otp_required": False, "session_hours": SESSION_HOURS}

    # Generate OTP
    code = generate_otp(6)
    otp_id = new_id()
    await db.otps.insert_one({
        "id": otp_id,
        "user_id": user["id"],
        "email": user["email"],
        "code_hash": pwd_context.hash(code),
        "expires_at": (now_utc() + timedelta(minutes=OTP_TTL_MINUTES)).isoformat(),
        "created_at": now_iso(),
        "attempts": 0,
        "used": False,
        "ip": (request.client.host if request and request.client else None),
    })

    # Send OTP email
    lang = resolve_lang(request.headers.get("X-Lang"))
    tpl = await get_email_template("otp")
    subject_key = "subject_ar" if lang == "ar" else "subject_en"
    variables = {
        "app_name": APP_NAME,
        "name": user.get("name", ""),
        "email": user["email"],
        "otp": code,
    }
    subject = render(tpl.get(subject_key, tpl["subject_en"]), variables)
    html = render(tpl["html"], variables)
    ok, msg = await send_email(smtp_cfg, user["email"], subject, html, from_name=APP_NAME)
    if not ok:
        log.warning(f"OTP email send failed for {user['email']}: {msg}")
        return {"otp_required": True, "otp_id": otp_id, "email_sent": False, "session_hours": SESSION_HOURS}

    return {"otp_required": True, "otp_id": otp_id, "email_sent": True, "session_hours": SESSION_HOURS}


@router.post("/auth/otp/verify")
@limiter.limit(LIMIT_OTP)
async def verify_otp(body: OTPVerifyIn, request: Request):
    rec = await db.otps.find_one({"id": body.otp_id})
    if not rec:
        raise HTTPException(404, "Invalid OTP")
    if rec.get("used"):
        raise HTTPException(400, "Code already used")
    if rec.get("attempts", 0) >= OTP_MAX_ATTEMPTS:
        raise HTTPException(429, "Too many attempts")
    try:
        from datetime import datetime
        expires_at = datetime.fromisoformat(rec["expires_at"])
        if expires_at < now_utc():
            raise HTTPException(410, "Code expired")
    except (KeyError, ValueError):
        raise HTTPException(400, "Invalid OTP record")

    if not pwd_context.verify(body.code, rec["code_hash"]):
        await db.otps.update_one({"id": body.otp_id}, {"$inc": {"attempts": 1}})
        raise HTTPException(401, "Wrong code")

    await db.otps.update_one({"id": body.otp_id}, {"$set": {"used": True, "used_at": now_iso()}})
    user = await db.users.find_one({"id": rec["user_id"]})
    if not user:
        raise HTTPException(404, "User missing")
    user.pop("_id", None); user.pop("password_hash", None)
    token = make_session_token(user["id"])
    return {"token": token, "user": user, "session_hours": SESSION_HOURS}


@router.post("/auth/otp/resend")
@limiter.limit(LIMIT_OTP)
async def resend_otp(body: OTPResendIn, request: Request):
    rec = await db.otps.find_one({"id": body.otp_id})
    if not rec:
        raise HTTPException(404, "Invalid OTP id")
    user = await db.users.find_one({"id": rec["user_id"]})
    if not user:
        raise HTTPException(404, "User missing")

    smtp_cfg = await get_smtp_config()
    if not smtp_cfg or not smtp_cfg.get("host"):
        raise HTTPException(503, "Email service not configured")

    code = generate_otp(6)
    await db.otps.update_one(
        {"id": body.otp_id},
        {"$set": {
            "code_hash": pwd_context.hash(code),
            "expires_at": (now_utc() + timedelta(minutes=OTP_TTL_MINUTES)).isoformat(),
            "attempts": 0,
        }},
    )
    lang = resolve_lang(request.headers.get("X-Lang"))
    tpl = await get_email_template("otp")
    variables = {"app_name": APP_NAME, "name": user.get("name", ""), "email": user["email"], "otp": code}
    subject = render(tpl["subject_ar" if lang == "ar" else "subject_en"], variables)
    html = render(tpl["html"], variables)
    ok, msg = await send_email(smtp_cfg, user["email"], subject, html, from_name=APP_NAME)
    return {"ok": ok, "detail": msg}


@router.get("/auth/me")
async def me(user=Depends(get_current_user)):
    return user


@router.post("/auth/change-password")
@limiter.limit(LIMIT_PASSWORD)
async def change_password(body: ChangePasswordIn, request: Request, user=Depends(get_current_user)):
    full = await db.users.find_one({"id": user["id"]})
    if not full or not pwd_context.verify(body.current_password, full["password_hash"]):
        raise HTTPException(400, "Current password is incorrect")
    if len(body.new_password) < 8:
        raise HTTPException(400, "New password must be at least 8 characters")
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"password_hash": pwd_context.hash(body.new_password), "must_change_password": False, "updated_at": now_iso()}},
    )
    return {"ok": True}


@router.post("/auth/accept-invite")
@limiter.limit(LIMIT_PASSWORD)
async def accept_invite(body: AcceptInviteIn, request: Request):
    """Member accepts an invite using the provided token and temp password."""
    inv = await db.invites.find_one({"invite_token": body.token})
    if not inv:
        raise HTTPException(404, "Invalid invite")
    if inv.get("status") != "pending":
        raise HTTPException(400, "Invite no longer valid")

    user = await db.users.find_one({"email": inv["email"]})
    if not user:
        raise HTTPException(404, "User account not found")
    if not pwd_context.verify(body.temp_password, user["password_hash"]):
        raise HTTPException(401, "Wrong temporary password")

    await db.invites.update_one({"id": inv["id"]}, {"$set": {"status": "accepted", "accepted_at": now_iso()}})
    token = make_session_token(user["id"])
    user.pop("_id", None); user.pop("password_hash", None)
    return {"token": token, "user": user, "must_change_password": True, "session_hours": SESSION_HOURS}
