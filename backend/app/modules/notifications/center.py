"""Notification Center (Phase 5, Module 3) — persistent per-user inbox.

Read/unread/archive/mark-all/filter by category. Fed by notify() from approvals,
escalations, CRM, reminders, reports, and intelligence alerts. The legacy dynamic
GET /notifications (task-state derived) is preserved unchanged for backward compatibility.
"""
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: F401 (kept for symmetry; not required)

from app.core.db_mongo import db
from app.core.security import get_current_user
from app.core.utils import now_iso
from app.shared.notifications import CATEGORIES

router = APIRouter()


@router.get("/notifications/center")
async def inbox(category: Optional[str] = None, status: Optional[str] = "all", limit: int = 50,
                user=Depends(get_current_user)):
    limit = min(max(limit, 1), 200)
    q: Dict[str, Any] = {"user_id": user["id"]}
    if status == "unread":
        q["read"] = False
        q["archived"] = False
    elif status == "read":
        q["read"] = True
        q["archived"] = False
    elif status == "archived":
        q["archived"] = True
    else:  # all = not archived
        q["archived"] = False
    if category:
        q["category"] = category
    rows = await db.notifications.find(q, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return rows


@router.get("/notifications/center/unread-count")
async def unread_count(user=Depends(get_current_user)):
    n = await db.notifications.count_documents({"user_id": user["id"], "read": False, "archived": False})
    return {"unread": n}


@router.get("/notifications/center/categories")
async def category_counts(user=Depends(get_current_user)):
    out = {c: 0 for c in CATEGORIES}
    for c in CATEGORIES:
        out[c] = await db.notifications.count_documents(
            {"user_id": user["id"], "category": c, "read": False, "archived": False})
    return {"unread_by_category": out}


@router.post("/notifications/center/{nid}/read")
async def mark_read(nid: str, user=Depends(get_current_user)):
    res = await db.notifications.update_one(
        {"id": nid, "user_id": user["id"]}, {"$set": {"read": True, "read_at": now_iso()}})
    if not res.matched_count:
        raise HTTPException(404, "Notification not found")
    return {"ok": True}


@router.post("/notifications/center/{nid}/unread")
async def mark_unread(nid: str, user=Depends(get_current_user)):
    res = await db.notifications.update_one(
        {"id": nid, "user_id": user["id"]}, {"$set": {"read": False}, "$unset": {"read_at": ""}})
    if not res.matched_count:
        raise HTTPException(404, "Notification not found")
    return {"ok": True}


@router.post("/notifications/center/{nid}/archive")
async def archive(nid: str, user=Depends(get_current_user)):
    res = await db.notifications.update_one(
        {"id": nid, "user_id": user["id"]}, {"$set": {"archived": True, "read": True, "archived_at": now_iso()}})
    if not res.matched_count:
        raise HTTPException(404, "Notification not found")
    return {"ok": True}


@router.post("/notifications/center/read-all")
async def mark_all_read(category: Optional[str] = None, user=Depends(get_current_user)):
    q: Dict[str, Any] = {"user_id": user["id"], "read": False, "archived": False}
    if category:
        q["category"] = category
    res = await db.notifications.update_many(q, {"$set": {"read": True, "read_at": now_iso()}})
    return {"ok": True, "updated": res.modified_count}
