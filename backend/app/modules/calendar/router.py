"""Internal calendar events (+ synthetic task-derived events)."""
from datetime import datetime
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.core.db_mongo import db
from app.core.security import get_current_user
from app.core.utils import now_iso, new_id, clean
from app.shared.permissions import user_visible_project_ids

router = APIRouter()


class CalendarEventIn(BaseModel):
    title: str
    start: str
    end: str
    type: Optional[str] = "event"
    project_id: Optional[str] = None
    task_id: Optional[str] = None
    color: Optional[str] = None
    notes: Optional[str] = ""


class CalendarEventUpdate(BaseModel):
    title: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None
    type: Optional[str] = None
    project_id: Optional[str] = None
    task_id: Optional[str] = None
    color: Optional[str] = None
    notes: Optional[str] = None


@router.post("/calendar/events")
async def create_event(body: CalendarEventIn, user=Depends(get_current_user)):
    try:
        if datetime.fromisoformat(body.end.replace("Z", "+00:00")) < datetime.fromisoformat(body.start.replace("Z", "+00:00")):
            raise HTTPException(400, "Event end must be after start")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, "Invalid start/end datetime")
    doc = body.model_dump()
    doc.update({"id": new_id(), "user_id": user["id"], "created_at": now_iso(), "updated_at": now_iso()})
    await db.calendar_events.insert_one(doc)
    return clean(doc)


@router.get("/calendar/events")
async def list_events(start: Optional[str] = None, end: Optional[str] = None, user=Depends(get_current_user)):
    uid = user["id"]
    visible_pids = await user_visible_project_ids(uid)
    base = {"$or": [{"user_id": uid}, {"project_id": {"$in": visible_pids}}]}
    q: Dict[str, Any] = base
    extras = []
    if start:
        extras.append({"end": {"$gte": start}})
    if end:
        extras.append({"start": {"$lte": end}})
    if extras:
        q = {"$and": [base] + extras}
    rows = await db.calendar_events.find(q, {"_id": 0}).sort("start", 1).to_list(1000)

    tasks = await db.tasks.find({"$or": [{"owner_id": uid}, {"assignee_id": uid}], "status": {"$ne": "done"}}, {"_id": 0}).to_list(500)
    for t in tasks:
        sched = t.get("scheduled_for")
        due = t.get("due_date")
        if not sched and not due:
            continue
        ev_date = sched or (due[:10] if due else None)
        if not ev_date:
            continue
        try:
            datetime.fromisoformat(ev_date + "T00:00:00+00:00")
        except Exception:
            continue
        rows.append({
            "id": f"task-{t['id']}",
            "title": t.get("title"),
            "start": f"{ev_date}T09:00:00+00:00",
            "end": f"{ev_date}T10:00:00+00:00",
            "type": "task",
            "task_id": t["id"],
            "project_id": t.get("project_id"),
            "color": "#FF4500",
            "synthetic": True,
        })
    rows.sort(key=lambda r: r.get("start", ""))
    return rows


@router.patch("/calendar/events/{eid}")
async def update_event(eid: str, body: CalendarEventUpdate, user=Depends(get_current_user)):
    if eid.startswith("task-"):
        raise HTTPException(400, "Synthetic task events are edited via /api/tasks")
    upd = body.model_dump(exclude_unset=True)
    upd["updated_at"] = now_iso()
    if upd.get("start") and upd.get("end"):
        try:
            if datetime.fromisoformat(upd["end"].replace("Z", "+00:00")) < datetime.fromisoformat(upd["start"].replace("Z", "+00:00")):
                raise HTTPException(400, "Event end must be after start")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(400, "Invalid start/end datetime")
    res = await db.calendar_events.update_one({"id": eid, "user_id": user["id"]}, {"$set": upd})
    if not res.matched_count:
        raise HTTPException(404, "Not found")
    return await db.calendar_events.find_one({"id": eid}, {"_id": 0})


@router.delete("/calendar/events/{eid}")
async def delete_event(eid: str, user=Depends(get_current_user)):
    await db.calendar_events.delete_one({"id": eid, "user_id": user["id"]})
    return {"ok": True}
