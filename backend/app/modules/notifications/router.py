"""Dynamic notifications derived from current task state (overdue / due-soon / blocked)."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.core.db_mongo import db
from app.core.security import get_current_user
from app.core.deps import get_lang
from app.core.utils import now_iso

router = APIRouter()


@router.get("/notifications")
async def list_notifications(user=Depends(get_current_user), lang: str = Depends(get_lang)):
    AR = (lang == "ar")
    L_OVERDUE = "مهمة متأخرة" if AR else "Task overdue"
    L_DUE_SOON = "مستحقة خلال ٢٤ ساعة" if AR else "Due within 24h"
    L_BLOCKED = "مهمة معلّقة" if AR else "Task blocked"
    notifications = []
    now = datetime.now(timezone.utc)
    tasks = await db.tasks.find({"owner_id": user["id"], "status": {"$ne": "done"}}, {"_id": 0}).to_list(500)
    for t in tasks:
        if t.get("due_date"):
            try:
                d = datetime.fromisoformat(t["due_date"].replace("Z", "+00:00"))
                if d < now:
                    notifications.append({
                        "id": f"overdue-{t['id']}",
                        "type": "overdue",
                        "title": L_OVERDUE,
                        "message": t["title"],
                        "task_id": t["id"],
                        "created_at": t["due_date"],
                    })
                elif (d - now).total_seconds() < 86400:
                    notifications.append({
                        "id": f"due-{t['id']}",
                        "type": "due_soon",
                        "title": L_DUE_SOON,
                        "message": t["title"],
                        "task_id": t["id"],
                        "created_at": t["due_date"],
                    })
            except Exception:
                pass
    for t in tasks:
        if t.get("status") == "blocked":
            notifications.append({
                "id": f"blocked-{t['id']}",
                "type": "blocked",
                "title": L_BLOCKED,
                "message": t["title"],
                "task_id": t["id"],
                "created_at": t.get("updated_at", now_iso()),
            })
    notifications.sort(key=lambda x: x["created_at"], reverse=True)
    return notifications[:30]
