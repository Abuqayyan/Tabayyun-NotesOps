"""Team / membership routes (invite, list invites, members).

PHASE 0 SECURITY FIX — invite privilege escalation:
  Previously ANY authenticated user could call /team/invite, and inviting an existing
  email RESET that user's password + forced must_change_password — enabling account
  takeover / lockout. This is now fixed:
    1. Only admins may invite (hard 403 otherwise).
    2. Inviting an EXISTING user never touches their credentials. No password reset,
       no must_change_password change, no temp password issued.
    3. Temp passwords are issued ONLY when creating a brand-new account.
"""
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, EmailStr

from app.core.db_mongo import db
from app.core.security import pwd_context, get_current_user
from app.core.utils import now_iso, new_id, resolve_lang
from app.shared.email import send_templated_email, resolve_app_url
from app.shared.rate_limit import limiter, LIMIT_INVITE
from security_utils import generate_temp_password, generate_invite_token, now_utc

router = APIRouter()


class InviteIn(BaseModel):
    email: EmailStr
    role: Optional[str] = "viewer"  # editor | viewer
    project_id: Optional[str] = None
    name: Optional[str] = None  # display name for new user


def _require_admin(user: dict) -> None:
    if not user.get("is_admin", False):
        raise HTTPException(403, "Only admins can invite team members")


@router.post("/team/invite")
@limiter.limit(LIMIT_INVITE)
async def invite_team(body: InviteIn, request: Request, user=Depends(get_current_user)):
    _require_admin(user)
    email = body.email.lower()
    existing = await db.users.find_one({"email": email})

    if existing:
        # SECURITY: never modify an existing user's credentials via invite.
        member_id = existing["id"]
        temp_pwd = None
        is_new_account = False
    else:
        member_id = new_id()
        temp_pwd = generate_temp_password()
        await db.users.insert_one({
            "id": member_id,
            "email": email,
            "name": body.name or email.split("@")[0],
            "password_hash": pwd_context.hash(temp_pwd),
            "avatar_url": None,
            "is_admin": False,
            "must_change_password": True,
            "created_at": now_iso(),
            "invited_by": user["id"],
        })
        is_new_account = True

    invite_id = new_id()
    token = generate_invite_token()
    inv = {
        "id": invite_id,
        "invite_token": token,
        "email": email,
        "role": body.role or "viewer",
        "project_id": body.project_id,
        "user_id": member_id,
        "invited_by": user["id"],
        "inviter_name": user["name"],
        "status": "pending",
        "is_new_account": is_new_account,
        "created_at": now_iso(),
        "expires_at": (now_utc() + timedelta(days=14)).isoformat(),
    }
    await db.invites.insert_one(inv)

    # Grant project access if requested (admin must own the project).
    if body.project_id and body.role in ("editor", "viewer"):
        await db.projects.update_one(
            {"id": body.project_id, "owner_id": user["id"]},
            {"$set": {f"roles.{member_id}": body.role}, "$addToSet": {"members": member_id}},
        )

    app_url = await resolve_app_url(request)
    invite_url = f"{app_url}/login?invite={token}&email={email}"
    lang = resolve_lang(request.headers.get("X-Lang"))

    ok = False
    msg = ""
    if is_new_account:
        # New account: send invite with the one-time temp password.
        ok, msg = await send_templated_email(
            "invite",
            email,
            {
                "actor": user.get("name", ""),
                "name": body.name or email.split("@")[0],
                "temp_password": temp_pwd,
                "invite_url": invite_url,
            },
            lang=lang,
        )
    elif body.project_id:
        # Existing account: notify about new project access only (no credentials).
        p = await db.projects.find_one({"id": body.project_id}, {"_id": 0}) or {}
        ok, msg = await send_templated_email(
            "task_assigned",
            email,
            {
                "actor": user.get("name", ""),
                "title": p.get("name", ""),
                "description": p.get("description", ""),
                "due_date": "",
                "url": f"{app_url}/projects/{body.project_id}",
            },
            lang=lang,
        )

    inv.pop("_id", None)
    payload = {**inv, "emailed": ok, "invite_url": invite_url, "existing_user": not is_new_account}
    # Dev convenience: surface temp_password only for NEW accounts when email failed.
    if is_new_account and not ok:
        payload["temp_password"] = temp_pwd
        payload["email_error"] = msg
    return payload


@router.get("/team/invites")
async def list_invites(user=Depends(get_current_user)):
    rows = await db.invites.find({"invited_by": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return rows


@router.delete("/team/invites/{iid}")
async def revoke_invite(iid: str, user=Depends(get_current_user)):
    await db.invites.update_one({"id": iid, "invited_by": user["id"]}, {"$set": {"status": "revoked"}})
    return {"ok": True}


@router.get("/team/members")
async def list_members(user=Depends(get_current_user)):
    projects = await db.projects.find({"$or": [
        {"owner_id": user["id"]},
        {f"roles.{user['id']}": {"$exists": True}},
        {"members": user["id"]},
    ]}, {"_id": 0, "members": 1, "roles": 1, "owner_id": 1}).to_list(500)
    member_ids = set()
    for p in projects:
        member_ids.add(p.get("owner_id"))
        for m in p.get("members", []) or []:
            member_ids.add(m)
        for m in (p.get("roles") or {}).keys():
            member_ids.add(m)
    invitees = await db.users.find({"invited_by": user["id"]}, {"_id": 0, "id": 1}).to_list(500)
    for u in invitees:
        member_ids.add(u["id"])
    member_ids.discard(None)
    rows = await db.users.find({"id": {"$in": list(member_ids)}}, {"_id": 0, "password_hash": 0}).to_list(200)
    for u in rows:
        active = await db.tasks.count_documents({"$or": [{"owner_id": u["id"]}, {"assignee_id": u["id"]}], "status": {"$ne": "done"}})
        u["active_tasks"] = active
    return rows
