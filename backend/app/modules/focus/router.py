"""Focus sessions (pomodoro / deep work logging)."""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.db_mongo import db
from app.core.security import get_current_user
from app.core.utils import now_iso, new_id, clean

router = APIRouter()


class FocusSessionIn(BaseModel):
    task_id: Optional[str] = None
    duration_minutes: int
    mode: Optional[str] = "pomodoro"
    completed: bool = True
    energy_level: Optional[int] = None


@router.post("/focus/sessions")
async def create_focus_session(body: FocusSessionIn, user=Depends(get_current_user)):
    sid = new_id()
    doc = body.model_dump()
    doc.update({"id": sid, "user_id": user["id"], "created_at": now_iso()})
    await db.focus_sessions.insert_one(doc)
    if body.task_id and body.completed:
        await db.tasks.update_one(
            {"id": body.task_id, "owner_id": user["id"]},
            {"$inc": {"actual_minutes": body.duration_minutes}},
        )
    return clean(doc)


@router.get("/focus/sessions")
async def list_focus_sessions(user=Depends(get_current_user)):
    rows = await db.focus_sessions.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return rows
