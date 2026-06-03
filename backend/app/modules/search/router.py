"""Global search API: GET /search (permission-aware) + recent searches."""
from typing import Optional, List

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db_mongo import db
from app.core.db_postgres import get_session
from app.core.security import get_current_user
from app.core.utils import new_id, now_iso
from app.shared.rate_limit import limiter, LIMIT_SEARCH
from app.modules.search.service import global_search, ALL_TYPES

router = APIRouter()


@router.get("/search")
@limiter.limit(LIMIT_SEARCH)
async def search(request: Request, q: str = "", types: Optional[str] = None,
                 limit: int = 30, user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    type_list: Optional[List[str]] = [t.strip() for t in types.split(",") if t.strip()] if types else None
    result = await global_search(session, user, q, type_list, limit)
    # Persist a recent search (best-effort, deduped by query).
    if result["count"] >= 0 and len((q or "").strip()) >= 2:
        try:
            await db.search_history.update_one(
                {"user_id": user["id"], "q": q.strip()},
                {"$set": {"at": now_iso(), "hits": result["count"]},
                 "$setOnInsert": {"id": new_id(), "user_id": user["id"], "q": q.strip()}},
                upsert=True,
            )
        except Exception:  # noqa: BLE001
            pass
    return result


@router.get("/search/types")
async def search_types(user=Depends(get_current_user)):
    return {"types": ALL_TYPES}


@router.get("/search/recent")
async def recent_searches(limit: int = 10, user=Depends(get_current_user)):
    limit = min(max(limit, 1), 30)
    rows = await db.search_history.find({"user_id": user["id"]}, {"_id": 0, "q": 1, "at": 1, "hits": 1}).sort("at", -1).to_list(limit)
    return rows


@router.delete("/search/recent")
async def clear_recent(user=Depends(get_current_user)):
    await db.search_history.delete_many({"user_id": user["id"]})
    return {"ok": True}
