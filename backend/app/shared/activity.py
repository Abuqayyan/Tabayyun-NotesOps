"""Company activity feed producer (Mongo, append-only).

emit_activity is the single seam mutation sites call. It is fire-and-forget: a feed
write must never break the underlying business operation. The read API
(app/modules/activity/router.py) applies permission-based visibility filtering.
"""
import logging
from typing import Optional

from app.core.db_mongo import db
from app.core.utils import new_id, now_iso

log = logging.getLogger("opscore.activity")


async def emit_activity(
    actor_id: str,
    verb: str,
    object_type: str,
    object_id: str,
    department_id: Optional[str] = None,
    project_id: Optional[str] = None,
    metadata: Optional[dict] = None,
    actor_name: Optional[str] = None,
) -> None:
    """Append one event to the activity feed. Never raises."""
    try:
        await db.activity_feed.insert_one({
            "id": new_id(),
            "actor_id": actor_id,
            "actor_name": actor_name or "",
            "verb": verb,
            "object_type": object_type,
            "object_id": object_id,
            "department_id": department_id,
            "project_id": project_id,
            "metadata": metadata or {},
            "created_at": now_iso(),
        })
    except Exception as exc:  # noqa: BLE001
        log.warning(f"activity emit failed ({verb}): {exc}")
