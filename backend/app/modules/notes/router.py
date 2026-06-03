"""Notes: CRUD with project-scoped access."""
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.core.db_mongo import db
from app.core.security import get_current_user
from app.core.utils import now_iso, new_id, clean
from app.shared.permissions import can_edit, user_visible_project_ids

router = APIRouter()


class NoteIn(BaseModel):
    title: str
    content: str
    project_id: Optional[str] = None
    task_id: Optional[str] = None
    tags: Optional[List[str]] = []


class NoteUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    project_id: Optional[str] = None
    tags: Optional[List[str]] = None
    done: Optional[bool] = None


@router.post("/notes")
async def create_note(body: NoteIn, user=Depends(get_current_user)):
    nid = new_id()
    doc = body.model_dump()
    doc.update({"id": nid, "owner_id": user["id"], "created_at": now_iso(), "updated_at": now_iso(), "done": False, "done_at": None})
    await db.notes.insert_one(doc)
    return clean(doc)


@router.get("/notes")
async def list_notes(project_id: Optional[str] = None, include_done: bool = False, scope: Optional[str] = "mine", user=Depends(get_current_user)):
    uid = user["id"]
    visible_pids = await user_visible_project_ids(uid)
    if scope == "all":
        base: Dict[str, Any] = {"$or": [{"owner_id": uid}, {"project_id": {"$in": visible_pids}}]}
    else:
        base = {"owner_id": uid}
    extra: Dict[str, Any] = {}
    if project_id:
        if project_id not in visible_pids:
            raise HTTPException(403, "No access to this project")
        extra["project_id"] = project_id
    if not include_done:
        extra["done"] = {"$ne": True}
    q = {"$and": [base, extra]} if extra else base
    rows = await db.notes.find(q, {"_id": 0}).sort("updated_at", -1).to_list(300)
    return rows


@router.patch("/notes/{nid}")
async def update_note(nid: str, body: NoteUpdate, user=Depends(get_current_user)):
    uid = user["id"]
    existing = await db.notes.find_one({"id": nid}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Not found")
    allowed = existing.get("owner_id") == uid
    if not allowed and existing.get("project_id"):
        p = await db.projects.find_one({"id": existing["project_id"]}, {"_id": 0})
        allowed = p and can_edit(p, uid)
    if not allowed:
        raise HTTPException(403, "No edit access")
    upd = body.model_dump(exclude_unset=True)
    upd["updated_at"] = now_iso()
    if "done" in upd:
        upd["done_at"] = now_iso() if upd["done"] else None
    await db.notes.update_one({"id": nid}, {"$set": upd})
    return await db.notes.find_one({"id": nid}, {"_id": 0})


@router.delete("/notes/{nid}")
async def delete_note(nid: str, user=Depends(get_current_user)):
    uid = user["id"]
    existing = await db.notes.find_one({"id": nid}, {"_id": 0})
    if not existing:
        return {"ok": True}
    allowed = existing.get("owner_id") == uid
    if not allowed and existing.get("project_id"):
        p = await db.projects.find_one({"id": existing["project_id"]}, {"_id": 0})
        allowed = p and can_edit(p, uid)
    if not allowed:
        raise HTTPException(403, "No delete access")
    await db.notes.delete_one({"id": nid})
    await db.reminders.delete_many({"entity_type": "note", "entity_id": nid})
    return {"ok": True}
