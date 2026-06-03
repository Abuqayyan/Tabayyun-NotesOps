"""In-app notification fan-out.

`notify()` is the single seam that writes a per-recipient notification into the
persistent Notification Center (`db.notifications`) and pushes a realtime nudge over the
existing websocket. Producers (approvals, escalations, CRM, reminders) call this; the
center's read API lives in app/modules/notifications/center.py. Best-effort: a
notification failure must never break the business operation that triggered it.
"""
import logging
from typing import Iterable, Optional

from app.core.db_mongo import db
from app.core.utils import new_id, now_iso
from app.shared.websocket import broadcast

log = logging.getLogger("opscore.notifications")

CATEGORIES = ("task", "meeting", "approval", "crm", "escalation", "report", "knowledge", "intelligence", "system")


async def notify(user_ids: Iterable[str], category: str, title: str, message: str = "",
                 ref_type: Optional[str] = None, ref_id: Optional[str] = None,
                 actor_name: Optional[str] = None) -> int:
    """Create one notification per recipient. Returns the number created. Never raises."""
    created = 0
    seen = set()
    for uid in user_ids or []:
        if not uid or uid in seen:
            continue
        seen.add(uid)
        try:
            await db.notifications.insert_one({
                "id": new_id(), "user_id": uid, "category": category if category in CATEGORIES else "system",
                "title": title, "message": message, "ref_type": ref_type, "ref_id": ref_id,
                "actor_name": actor_name or "", "read": False, "archived": False, "created_at": now_iso(),
            })
            created += 1
            await broadcast(uid, "notification.new", {"category": category, "title": title})
        except Exception as exc:  # noqa: BLE001
            log.debug(f"notify failed for {uid}: {exc}")
    return created
