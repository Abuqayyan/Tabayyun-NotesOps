"""Company activity feed — read API with permission-based visibility.

Visibility rules:
  - activity.view_all          -> entire company feed
  - activity.view_department   -> events in the user's department(s) + the user's own actions
  - otherwise                  -> only the user's own actions
"""
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.core.db_mongo import db
from app.core.db_postgres import get_session
from app.modules.rbac.resolver import get_permission_keys, user_department_ids

router = APIRouter()


@router.get("/activity")
async def list_activity(
    limit: int = 50,
    department_id: Optional[str] = None,
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    limit = min(max(limit, 1), 200)
    perms = await get_permission_keys(session, user)

    if "activity.view_all" in perms:
        query: Dict[str, Any] = {}
        if department_id:
            query["department_id"] = department_id
    elif "activity.view_department" in perms:
        dept_ids = list(await user_department_ids(session, user["id"]))
        ors = [{"actor_id": user["id"]}]
        if dept_ids:
            ors.append({"department_id": {"$in": dept_ids}})
        query = {"$or": ors}
        if department_id:
            query = {"$and": [query, {"department_id": department_id}]}
    else:
        query = {"actor_id": user["id"]}

    rows = await db.activity_feed.find(query, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return rows
