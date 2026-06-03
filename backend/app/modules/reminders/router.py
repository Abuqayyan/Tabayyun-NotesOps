"""Reminders: CRUD, send-now, and reminder settings (workspace + personal)."""
import re
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel

from app.core.db_mongo import db
from app.core.security import get_current_user
from app.core.utils import now_iso, new_id, clean
from app.modules.reminders.service import (
    DEFAULT_WORKSPACE_REMINDER_SETTINGS, get_workspace_reminder_settings,
    resolve_reminder_targets, compute_fire_at, fire_reminder_payload,
)

router = APIRouter()


class ReminderIn(BaseModel):
    entity_type: str
    entity_id: str
    fire_at: Optional[str] = None
    offset_minutes: Optional[int] = None
    message: Optional[str] = None
    channel: Optional[str] = "email"
    recipient_ids: Optional[List[str]] = None


class ReminderUpdate(BaseModel):
    fire_at: Optional[str] = None
    message: Optional[str] = None
    enabled: Optional[bool] = None
    recipient_ids: Optional[List[str]] = None


class SendNowIn(BaseModel):
    reminder_id: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    recipient_ids: Optional[List[str]] = None
    message: Optional[str] = None


class WorkspaceReminderSettingsIn(BaseModel):
    overdue_digest_enabled: Optional[bool] = None
    overdue_digest_time: Optional[str] = None
    digest_lookahead_hours: Optional[int] = None
    default_offsets_minutes: Optional[List[int]] = None


class UserReminderPrefsIn(BaseModel):
    digest_opted_out: Optional[bool] = None
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None


@router.post("/reminders")
async def create_reminder(body: ReminderIn, user=Depends(get_current_user)):
    entity, default_recipients = await resolve_reminder_targets(user["id"], body.entity_type, body.entity_id)
    fire_at = compute_fire_at(entity, body.offset_minutes, body.fire_at)

    recipients = body.recipient_ids if body.recipient_ids is not None else default_recipients
    if not recipients:
        recipients = [user["id"]]
    valid_users = await db.users.find({"id": {"$in": recipients}}, {"_id": 0, "id": 1}).to_list(50)
    recipients = [u["id"] for u in valid_users]
    if not recipients:
        recipients = [user["id"]]

    doc = {
        "id": new_id(),
        "entity_type": body.entity_type,
        "entity_id": body.entity_id,
        "user_id": user["id"],
        "recipient_ids": recipients,
        "fire_at": fire_at,
        "offset_minutes": body.offset_minutes,
        "message": body.message,
        "channel": body.channel or "email",
        "enabled": True,
        "sent": False,
        "sent_at": None,
        "created_at": now_iso(),
    }
    await db.reminders.insert_one(doc)
    return clean(doc)


@router.get("/reminders")
async def list_reminders(entity_type: Optional[str] = None, entity_id: Optional[str] = None, user=Depends(get_current_user)):
    q: Dict[str, Any] = {"$or": [{"user_id": user["id"]}, {"recipient_ids": user["id"]}]}
    extras: Dict[str, Any] = {}
    if entity_type:
        extras["entity_type"] = entity_type
    if entity_id:
        extras["entity_id"] = entity_id
    final = {"$and": [q, extras]} if extras else q
    rows = await db.reminders.find(final, {"_id": 0}).sort("fire_at", 1).to_list(200)
    return rows


@router.patch("/reminders/{rid}")
async def update_reminder(rid: str, body: ReminderUpdate, user=Depends(get_current_user)):
    rec = await db.reminders.find_one({"id": rid, "user_id": user["id"]}, {"_id": 0})
    if not rec:
        raise HTTPException(404, "Not found")
    upd = body.model_dump(exclude_unset=True)
    upd["updated_at"] = now_iso()
    if "fire_at" in upd:
        upd["sent"] = False
        upd["sent_at"] = None
    await db.reminders.update_one({"id": rid}, {"$set": upd})
    return await db.reminders.find_one({"id": rid}, {"_id": 0})


@router.delete("/reminders/{rid}")
async def delete_reminder(rid: str, user=Depends(get_current_user)):
    await db.reminders.delete_one({"id": rid, "user_id": user["id"]})
    return {"ok": True}


@router.post("/reminders/send-now")
async def send_now(body: SendNowIn, request: Request, user=Depends(get_current_user)):
    if body.reminder_id:
        rec = await db.reminders.find_one({"id": body.reminder_id}, {"_id": 0})
        if not rec or (rec.get("user_id") != user["id"] and user["id"] not in (rec.get("recipient_ids") or [])):
            raise HTTPException(404, "Reminder not found")
        entity_type, entity_id = rec["entity_type"], rec["entity_id"]
        recipients = rec.get("recipient_ids") or [rec["user_id"]]
        message = body.message or rec.get("message")
    else:
        if not body.entity_type or not body.entity_id:
            raise HTTPException(400, "Provide reminder_id OR entity_type+entity_id")
        entity, defaults = await resolve_reminder_targets(user["id"], body.entity_type, body.entity_id)
        entity_type, entity_id = body.entity_type, body.entity_id
        recipients = body.recipient_ids or defaults or [user["id"]]
        message = body.message

    ok_count, fail_count = await fire_reminder_payload(entity_type, entity_id, recipients, message, user.get("name") or "Someone", request)
    if body.reminder_id and ok_count > 0:
        await db.reminders.update_one({"id": body.reminder_id}, {"$set": {"sent": True, "sent_at": now_iso(), "send_ok_count": ok_count}})
    elif body.reminder_id:
        await db.reminders.update_one({"id": body.reminder_id}, {"$inc": {"attempts": 1}, "$set": {"last_attempt_at": now_iso(), "send_fail_count": fail_count}})
    return {"ok": ok_count > 0, "sent_to": ok_count, "failed": fail_count}


# ---- Reminder settings ----
@router.get("/settings/reminders")
async def get_reminder_settings(user=Depends(get_current_user)):
    ws = await get_workspace_reminder_settings()
    user_row = await db.user_settings.find_one({"user_id": user["id"]}, {"_id": 0}) or {}
    return {
        "workspace": ws,
        "personal": {
            "digest_opted_out": bool(user_row.get("digest_opted_out", False)),
            "quiet_hours_start": user_row.get("quiet_hours_start"),
            "quiet_hours_end": user_row.get("quiet_hours_end"),
        },
        "is_admin": bool(user.get("is_admin", False)),
    }


@router.put("/settings/reminders/workspace")
async def update_workspace_reminder_settings(body: WorkspaceReminderSettingsIn, user=Depends(get_current_user)):
    if not user.get("is_admin", False):
        raise HTTPException(403, "Only admins can change workspace reminder settings")
    upd: Dict[str, Any] = {"updated_at": now_iso()}
    for k in DEFAULT_WORKSPACE_REMINDER_SETTINGS.keys():
        v = getattr(body, k, None)
        if v is not None:
            upd[k] = v
    if "overdue_digest_time" in upd:
        if not isinstance(upd["overdue_digest_time"], str) or not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", upd["overdue_digest_time"]):
            raise HTTPException(400, "overdue_digest_time must be 'HH:MM' (00:00 - 23:59)")
    await db.workspace_settings.update_one(
        {"id": "reminders"},
        {"$set": upd, "$setOnInsert": {"id": "reminders", "created_at": now_iso()}},
        upsert=True,
    )
    return await get_workspace_reminder_settings()


@router.put("/settings/reminders/personal")
async def update_personal_reminder_prefs(body: UserReminderPrefsIn, user=Depends(get_current_user)):
    HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"
    upd: Dict[str, Any] = {"updated_at": now_iso()}
    for k in ("digest_opted_out", "quiet_hours_start", "quiet_hours_end"):
        v = getattr(body, k, None)
        if v is not None:
            if k in ("quiet_hours_start", "quiet_hours_end") and v and not re.match(HHMM, v):
                raise HTTPException(400, f"{k} must be 'HH:MM'")
            upd[k] = v
    await db.user_settings.update_one(
        {"user_id": user["id"]},
        {"$set": upd, "$setOnInsert": {"user_id": user["id"], "created_at": now_iso()}},
        upsert=True,
    )
    return await get_reminder_settings(user)
