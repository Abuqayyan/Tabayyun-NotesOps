"""Reminder domain helpers shared between the router and the background scheduler."""
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import HTTPException, Request

from app.core.config import PUBLIC_APP_URL
from app.core.db_mongo import db
from app.shared.email import send_templated_email
from app.shared.websocket import broadcast

DEFAULT_WORKSPACE_REMINDER_SETTINGS = {
    "overdue_digest_enabled": False,
    "overdue_digest_time": "09:00",
    "digest_lookahead_hours": 24,
    "default_offsets_minutes": [0, 15, 60, 1440],  # now, 15m, 1h, 1d
}


async def get_workspace_reminder_settings() -> dict:
    row = await db.workspace_settings.find_one({"id": "reminders"}, {"_id": 0}) or {}
    out = {**DEFAULT_WORKSPACE_REMINDER_SETTINGS}
    out.update({k: v for k, v in row.items() if k in DEFAULT_WORKSPACE_REMINDER_SETTINGS and v is not None})
    return out


async def resolve_reminder_targets(uid: str, entity_type: str, entity_id: str) -> tuple[Optional[dict], List[str]]:
    """Returns (entity_doc, default_recipient_ids), enforcing access."""
    from app.shared.permissions import can_view  # local import avoids cycle at import time
    if entity_type == "task":
        t = await db.tasks.find_one({"id": entity_id}, {"_id": 0})
        if not t:
            raise HTTPException(404, "Task not found")
        allowed = t.get("owner_id") == uid or t.get("assignee_id") == uid
        if not allowed and t.get("project_id"):
            p = await db.projects.find_one({"id": t["project_id"]}, {"_id": 0})
            allowed = p and can_view(p, uid)
        if not allowed:
            raise HTTPException(403, "No access to this task")
        defaults = [x for x in [t.get("assignee_id") or t.get("owner_id")] if x]
        return t, defaults
    if entity_type == "note":
        n = await db.notes.find_one({"id": entity_id}, {"_id": 0})
        if not n:
            raise HTTPException(404, "Note not found")
        allowed = n.get("owner_id") == uid
        if not allowed and n.get("project_id"):
            p = await db.projects.find_one({"id": n["project_id"]}, {"_id": 0})
            allowed = p and can_view(p, uid)
        if not allowed:
            raise HTTPException(403, "No access to this note")
        return n, [n.get("owner_id")] if n.get("owner_id") else []
    raise HTTPException(400, "entity_type must be 'task' or 'note'")


def compute_fire_at(entity: dict, offset_minutes: Optional[int], explicit_fire_at: Optional[str]) -> str:
    """Either uses explicit ISO fire_at OR subtracts offset_minutes from entity due/end date."""
    if explicit_fire_at:
        return explicit_fire_at
    if offset_minutes is None:
        raise HTTPException(400, "fire_at or offset_minutes is required")
    anchor = entity.get("due_date") or entity.get("end_date") or entity.get("scheduled_for")
    if not anchor:
        raise HTTPException(400, "Entity has no due_date/end_date for offset reminders")
    try:
        if "T" not in anchor:
            anchor = anchor + "T09:00:00+00:00"
        d = datetime.fromisoformat(anchor.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(400, "Invalid anchor datetime on entity")
    fire = d - timedelta(minutes=max(0, offset_minutes))
    return fire.isoformat()


_ENTITY_URL_SUFFIX = {
    "task": "/tasks?focus={id}",
    "note": "/notes?focus={id}",
    "meeting": "/meetings?focus={id}",
    "action_item": "/meetings?action={id}",
    "approval": "/approvals?focus={id}",
}


async def fire_reminder_payload(
    entity_type: str,
    entity_id: str,
    recipient_ids: List[str],
    custom_message: Optional[str],
    actor_name: str,
    request: Optional[Request] = None,
) -> tuple[int, int]:
    """Sends the reminder email to each recipient. Returns (sent_count, failed_count).

    task/note look up the entity for a rich title/description. Other entity types
    (approval, meeting, action_item — used by approvals & the escalation engine) send a
    generic notification driven by `custom_message`, so the one reminder engine serves
    every Phase 2 module without per-type send code.
    """
    if entity_type == "task":
        entity = await db.tasks.find_one({"id": entity_id}, {"_id": 0})
        if not entity:
            return 0, len(recipient_ids)
        title = custom_message or entity.get("title", "Reminder")
        desc = (entity.get("description") or "")[:400]
    elif entity_type == "note":
        entity = await db.notes.find_one({"id": entity_id}, {"_id": 0})
        if not entity:
            return 0, len(recipient_ids)
        title = custom_message or entity.get("title", "Reminder")
        desc = (entity.get("content") or "")[:400]
    else:
        # Generic notification (approval / meeting / action_item / escalation).
        title = custom_message or "Notification"
        desc = ""

    url_suffix = _ENTITY_URL_SUFFIX.get(entity_type, "/").format(id=entity_id)
    app_url = PUBLIC_APP_URL or (f"{request.url.scheme}://{request.headers.get('host', '')}" if request else "")

    ok = fail = 0
    for uid in recipient_ids:
        target = await db.users.find_one({"id": uid})
        if not target:
            fail += 1
            continue
        sent, _ = await send_templated_email(
            "task_reminder",
            target["email"],
            {
                "title": title,
                "description": desc,
                "url": f"{app_url}{url_suffix}",
                "actor": actor_name,
                "name": target.get("name") or "",
            },
            lang="ar",
        )
        if sent:
            ok += 1
            await broadcast(uid, "reminder.fire", {"entity_type": entity_type, "entity_id": entity_id, "title": title})
        else:
            fail += 1
    return ok, fail
