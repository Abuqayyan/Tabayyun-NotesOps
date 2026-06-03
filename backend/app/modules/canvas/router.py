"""Canvas / graph boards (xyflow nodes + edges)."""
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.core.db_mongo import db
from app.core.security import get_current_user
from app.core.utils import now_iso, new_id, clean

router = APIRouter()


class CanvasIn(BaseModel):
    name: str
    project_id: Optional[str] = None
    nodes: Optional[List[Dict[str, Any]]] = []
    edges: Optional[List[Dict[str, Any]]] = []


class CanvasUpdate(BaseModel):
    name: Optional[str] = None
    project_id: Optional[str] = None
    nodes: Optional[List[Dict[str, Any]]] = None
    edges: Optional[List[Dict[str, Any]]] = None


@router.post("/canvases")
async def create_canvas(body: CanvasIn, user=Depends(get_current_user)):
    doc = body.model_dump()
    doc.update({"id": new_id(), "user_id": user["id"], "created_at": now_iso(), "updated_at": now_iso()})
    await db.canvases.insert_one(doc)
    return clean(doc)


@router.get("/canvases")
async def list_canvases(user=Depends(get_current_user)):
    rows = await db.canvases.find({"user_id": user["id"]}, {"_id": 0, "nodes": 0, "edges": 0}).sort("updated_at", -1).to_list(100)
    for r in rows:
        full = await db.canvases.find_one({"id": r["id"]}, {"_id": 0, "nodes": 1, "edges": 1})
        r["node_count"] = len((full or {}).get("nodes", []) or [])
        r["edge_count"] = len((full or {}).get("edges", []) or [])
    return rows


@router.get("/canvases/{cid}")
async def get_canvas(cid: str, user=Depends(get_current_user)):
    c = await db.canvases.find_one({"id": cid, "user_id": user["id"]}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Not found")
    return c


@router.patch("/canvases/{cid}")
async def update_canvas(cid: str, body: CanvasUpdate, user=Depends(get_current_user)):
    upd = body.model_dump(exclude_unset=True)
    upd["updated_at"] = now_iso()
    res = await db.canvases.update_one({"id": cid, "user_id": user["id"]}, {"$set": upd})
    if not res.matched_count:
        raise HTTPException(404, "Not found")
    return await db.canvases.find_one({"id": cid}, {"_id": 0})


@router.delete("/canvases/{cid}")
async def delete_canvas(cid: str, user=Depends(get_current_user)):
    await db.canvases.delete_one({"id": cid, "user_id": user["id"]})
    return {"ok": True}
