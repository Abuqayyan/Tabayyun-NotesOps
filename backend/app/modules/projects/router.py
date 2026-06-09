"""Projects: CRUD, sharing/members, and the weekly schedule view."""
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel

from app.core.db_mongo import db
from app.core.security import get_current_user
from app.core.utils import now_iso, new_id, clean, resolve_lang
from app.shared.email import send_templated_email, resolve_app_url
from app.shared.activity import emit_activity
from app.shared.permissions import (
    load_project_or_403, user_visible_project_ids, project_role,
    can_view, can_edit, can_admin,
)

router = APIRouter()


class ProjectIn(BaseModel):
    name: str
    description: Optional[str] = ""
    color: Optional[str] = "#FF4500"
    status: Optional[str] = "active"
    priority: Optional[str] = "medium"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    due_date: Optional[str] = None
    milestones: Optional[List[Dict[str, Any]]] = []
    weekly_days: Optional[List[int]] = []


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    due_date: Optional[str] = None
    milestones: Optional[List[Dict[str, Any]]] = None
    weekly_days: Optional[List[int]] = None


class ProjectShareIn(BaseModel):
    email: str
    role: str = "viewer"


class ProjectMemberUpdate(BaseModel):
    role: str


@router.post("/projects")
async def create_project(body: ProjectIn, user=Depends(get_current_user)):
    pid = new_id()
    doc = body.model_dump()
    doc.update({
        "id": pid,
        "owner_id": user["id"],
        "members": [user["id"]],
        "roles": {user["id"]: "owner"},
        "progress": 0,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    })
    await db.projects.insert_one(doc)
    await emit_activity(user["id"], "project.created", "project", pid, project_id=pid,
                        actor_name=user.get("name"), metadata={"name": doc.get("name")})
    return clean(doc)


@router.get("/projects")
async def list_projects(user=Depends(get_current_user)):
    rows = await db.projects.find(
        {"$or": [
            {"owner_id": user["id"]},
            {f"roles.{user['id']}": {"$exists": True}},
            {"members": user["id"]},
        ]},
        {"_id": 0},
    ).sort("updated_at", -1).to_list(200)
    for p in rows:
        tasks = await db.tasks.find({"project_id": p["id"]}, {"_id": 0, "status": 1}).to_list(1000)
        if tasks:
            done = sum(1 for t in tasks if t.get("status") == "done")
            p["progress"] = int(done * 100 / len(tasks))
            p["task_count"] = len(tasks)
        else:
            p["progress"] = 0
            p["task_count"] = 0
        p["my_role"] = project_role(p, user["id"]) or "viewer"
    return rows


@router.get("/projects/{pid}")
async def get_project(pid: str, user=Depends(get_current_user)):
    p = await load_project_or_403(pid, user["id"])
    tasks = await db.tasks.find({"project_id": pid}, {"_id": 0}).to_list(1000)
    p["tasks"] = tasks
    if tasks:
        done = sum(1 for t in tasks if t.get("status") == "done")
        p["progress"] = int(done * 100 / len(tasks))
    notes = await db.notes.find({"project_id": pid, "done": {"$ne": True}}, {"_id": 0}).sort("created_at", -1).to_list(100)
    p["notes"] = notes
    files = await db.project_files.find({"project_id": pid}, {"_id": 0, "storage_path": 0}).sort("uploaded_at", -1).to_list(200)
    p["files"] = files
    p["my_role"] = project_role(p, user["id"]) or "viewer"
    return p


@router.patch("/projects/{pid}")
async def update_project(pid: str, body: ProjectUpdate, user=Depends(get_current_user)):
    await load_project_or_403(pid, user["id"], require_edit=True)
    upd = body.model_dump(exclude_unset=True)
    upd["updated_at"] = now_iso()
    await db.projects.update_one({"id": pid}, {"$set": upd})
    p = await db.projects.find_one({"id": pid}, {"_id": 0})
    p["my_role"] = project_role(p, user["id"]) or "viewer"
    return p


@router.delete("/projects/{pid}")
async def delete_project(pid: str, user=Depends(get_current_user)):
    await load_project_or_403(pid, user["id"], require_admin=True)
    await db.projects.delete_one({"id": pid})
    await db.tasks.delete_many({"project_id": pid})
    await db.notes.delete_many({"project_id": pid})
    return {"ok": True}


# ---- Sharing / members ----
@router.get("/projects/{pid}/members")
async def list_project_members(pid: str, user=Depends(get_current_user)):
    p = await load_project_or_403(pid, user["id"])
    member_ids = set([p.get("owner_id")] + list((p.get("roles") or {}).keys()) + (p.get("members") or []))
    member_ids.discard(None)
    rows = await db.users.find({"id": {"$in": list(member_ids)}}, {"_id": 0, "password_hash": 0}).to_list(100)
    roles = p.get("roles", {}) or {}
    for u in rows:
        u["role"] = "owner" if p.get("owner_id") == u["id"] else roles.get(u["id"], "viewer")
    return rows


@router.post("/projects/{pid}/share")
async def share_project(pid: str, body: ProjectShareIn, request: Request, user=Depends(get_current_user)):
    p = await load_project_or_403(pid, user["id"], require_admin=True)
    if body.role not in ("editor", "viewer"):
        raise HTTPException(400, "Role must be 'editor' or 'viewer'")
    target = await db.users.find_one({"email": body.email.lower()})
    if not target:
        raise HTTPException(404, "User not found. Invite them to the team first.")
    if target["id"] == user["id"]:
        raise HTTPException(400, "You are the owner")

    await db.projects.update_one(
        {"id": pid},
        {"$set": {f"roles.{target['id']}": body.role, "updated_at": now_iso()},
         "$addToSet": {"members": target["id"]}},
    )
    lang = resolve_lang(request.headers.get("X-Lang"))
    app_url = await resolve_app_url(request)
    await send_templated_email(
        "task_assigned",
        target["email"],
        {
            "actor": user.get("name", ""),
            "title": p.get("name", ""),
            "description": p.get("description", ""),
            "due_date": "",
            "url": f"{app_url}/projects/{pid}",
        },
        lang=lang,
    )
    return {"ok": True, "user_id": target["id"], "role": body.role}


@router.patch("/projects/{pid}/members/{uid}")
async def update_project_member(pid: str, uid: str, body: ProjectMemberUpdate, user=Depends(get_current_user)):
    p = await load_project_or_403(pid, user["id"], require_admin=True)
    if uid == p.get("owner_id"):
        raise HTTPException(400, "Cannot change owner role")
    if body.role not in ("editor", "viewer"):
        raise HTTPException(400, "Invalid role")
    await db.projects.update_one({"id": pid}, {"$set": {f"roles.{uid}": body.role, "updated_at": now_iso()}})
    return {"ok": True}


@router.delete("/projects/{pid}/members/{uid}")
async def remove_project_member(pid: str, uid: str, user=Depends(get_current_user)):
    p = await load_project_or_403(pid, user["id"], require_admin=True)
    if uid == p.get("owner_id"):
        raise HTTPException(400, "Cannot remove the owner")
    await db.projects.update_one(
        {"id": pid},
        {"$unset": {f"roles.{uid}": ""}, "$pull": {"members": uid}, "$set": {"updated_at": now_iso()}},
    )
    return {"ok": True}


# ---- Weekly schedule ----
@router.get("/schedule")
async def get_weekly_schedule(user=Depends(get_current_user)):
    """Return projects grouped by day of week (0=Sun .. 6=Sat) and unscheduled list."""
    projects = await db.projects.find(
        {"members": user["id"], "status": {"$ne": "archived"}},
        {"_id": 0},
    ).to_list(500)
    tids_by_pid: Dict[str, int] = {}
    async for t in db.tasks.find(
        {"owner_id": user["id"], "status": {"$ne": "done"}},
        {"_id": 0, "project_id": 1},
    ):
        pid = t.get("project_id")
        if pid:
            tids_by_pid[pid] = tids_by_pid.get(pid, 0) + 1

    by_day: Dict[int, List[Dict[str, Any]]] = {i: [] for i in range(7)}
    unscheduled: List[Dict[str, Any]] = []
    for p in projects:
        compact = {
            "id": p["id"],
            "name": p["name"],
            "color": p.get("color", "#FF4500"),
            "status": p.get("status", "active"),
            "priority": p.get("priority", "medium"),
            "open_tasks": tids_by_pid.get(p["id"], 0),
            "weekly_days": p.get("weekly_days") or [],
        }
        days = p.get("weekly_days") or []
        if not days:
            unscheduled.append(compact)
        else:
            for d in days:
                if isinstance(d, int) and 0 <= d <= 6:
                    by_day[d].append(compact)
    return {"by_day": by_day, "unscheduled": unscheduled}
