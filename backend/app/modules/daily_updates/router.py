"""Daily Updates API.

Submission: one update per employee per day (edit the same-day update in place).
Visibility (read) is permission-driven:
  - daily_update.view_all         -> every update company-wide
  - daily_update.view_department  -> updates in the viewer's department(s) + own
  - daily_update.view_team        -> updates of the viewer's direct reports + own
  - otherwise                     -> only the viewer's own updates
"""
from datetime import date
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db_mongo import db as mongo
from app.core.db_postgres import get_session
from app.core.security import get_current_user
from app.core.utils import now_iso
from app.modules.daily_updates.models import DailyUpdate
from app.modules.org.models import Employee
from app.modules.rbac.resolver import (
    require_permission, get_permission_keys, permission_scopes,
    user_department_ids, direct_report_user_ids,
)
from app.modules.audit.service import record_audit
from app.shared.activity import emit_activity

router = APIRouter()


class DailyUpdateIn(BaseModel):
    today: Optional[str] = ""
    tomorrow: Optional[str] = ""
    blockers: Optional[str] = ""
    update_date: Optional[str] = None  # defaults to today; pin for backfill/testing
    department_id: Optional[str] = None  # defaults to the employee's primary department


class DailyUpdateEdit(BaseModel):
    today: Optional[str] = None
    tomorrow: Optional[str] = None
    blockers: Optional[str] = None
    status: Optional[str] = None


def _out(u: DailyUpdate) -> dict:
    return {
        "id": u.id, "user_id": u.user_id, "department_id": u.department_id,
        "update_date": u.update_date, "today": u.today, "tomorrow": u.tomorrow,
        "blockers": u.blockers, "status": u.status,
        "created_at": u.created_at, "updated_at": u.updated_at,
    }


async def _primary_department(session: AsyncSession, user_id: str) -> Optional[str]:
    emp = (await session.execute(select(Employee).where(Employee.user_id == user_id))).scalar_one_or_none()
    return emp.primary_department_id if emp else None


async def _enrich_users(rows: List[dict]) -> None:
    ids = list({r["user_id"] for r in rows if r.get("user_id")})
    if not ids:
        return
    users = await mongo.users.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "name": 1, "email": 1}).to_list(1000)
    by_id = {u["id"]: u for u in users}
    for r in rows:
        u = by_id.get(r["user_id"]) or {}
        r["user_name"] = u.get("name")
        r["user_email"] = u.get("email")


@router.post("/daily-updates")
async def submit_update(
    body: DailyUpdateIn, request: Request,
    user=Depends(require_permission("daily_update.submit")),
    session: AsyncSession = Depends(get_session),
):
    day = (body.update_date or date.today().isoformat())[:10]
    dup = (await session.execute(select(DailyUpdate).where(
        DailyUpdate.user_id == user["id"], DailyUpdate.update_date == day))).scalar_one_or_none()
    if dup:
        raise HTTPException(400, "You already submitted an update for this day — edit it instead")
    dept = body.department_id or await _primary_department(session, user["id"])
    u = DailyUpdate(
        user_id=user["id"], department_id=dept, update_date=day,
        today=(body.today or "").strip(), tomorrow=(body.tomorrow or "").strip(),
        blockers=(body.blockers or "").strip(), status="submitted",
    )
    session.add(u)
    await session.flush()
    await record_audit(session, user, "daily_update.submit", "daily_update", u.id, after=_out(u),
                       ip=request.client.host if request.client else None)
    await session.commit()
    await emit_activity(user["id"], "daily_update.submitted", "daily_update", u.id, department_id=dept,
                        actor_name=user.get("name"), metadata={"date": day})
    return _out(u)


@router.get("/daily-updates")
async def list_updates(
    update_date: Optional[str] = None, user_id: Optional[str] = None,
    department_id: Optional[str] = None, limit: int = 100,
    user=Depends(get_current_user), session: AsyncSession = Depends(get_session),
):
    limit = min(max(limit, 1), 500)
    view_all, _ = await permission_scopes(session, user, "daily_update.view_all")
    view_dept_global, view_dept_ids = await permission_scopes(session, user, "daily_update.view_department")
    view_team, _ = await permission_scopes(session, user, "daily_update.view_team")

    q = select(DailyUpdate).order_by(DailyUpdate.update_date.desc())
    if view_all:
        pass  # no visibility restriction
    elif view_dept_global or view_dept_ids:
        # Own dept(s) if granted globally; otherwise exactly the departments scoped to the user.
        dept_ids = list(await user_department_ids(session, user["id"])) if view_dept_global else list(view_dept_ids)
        q = q.where(_or_user_or_dept({user["id"]}, dept_ids))
    elif view_team:
        team = await direct_report_user_ids(session, user["id"])
        team.add(user["id"])
        q = q.where(DailyUpdate.user_id.in_(list(team)))
    else:
        q = q.where(DailyUpdate.user_id == user["id"])

    if update_date:
        q = q.where(DailyUpdate.update_date == update_date[:10])
    if user_id:
        q = q.where(DailyUpdate.user_id == user_id)
    if department_id:
        q = q.where(DailyUpdate.department_id == department_id)

    rows = (await session.execute(q.limit(limit))).scalars().all()
    out = [_out(u) for u in rows]
    await _enrich_users(out)
    return out


@router.get("/daily-updates/me/today")
async def my_today(user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    day = date.today().isoformat()
    u = (await session.execute(select(DailyUpdate).where(
        DailyUpdate.user_id == user["id"], DailyUpdate.update_date == day))).scalar_one_or_none()
    return _out(u) if u else None


@router.get("/daily-updates/{uid}")
async def get_update(uid: str, user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    u = (await session.execute(select(DailyUpdate).where(DailyUpdate.id == uid))).scalar_one_or_none()
    if not u:
        raise HTTPException(404, "Daily update not found")
    if u.user_id != user["id"]:
        perms = await get_permission_keys(session, user, department_id=u.department_id)
        visible = ("daily_update.view_all" in perms) or ("daily_update.view_department" in perms)
        if not visible and "daily_update.view_team" in perms:
            team = await direct_report_user_ids(session, user["id"])
            visible = u.user_id in team
        if not visible:
            raise HTTPException(403, "No access to this update")
    out = [_out(u)]
    await _enrich_users(out)
    return out[0]


@router.patch("/daily-updates/{uid}")
async def edit_update(
    uid: str, body: DailyUpdateEdit, request: Request,
    user=Depends(get_current_user), session: AsyncSession = Depends(get_session),
):
    u = (await session.execute(select(DailyUpdate).where(DailyUpdate.id == uid))).scalar_one_or_none()
    if not u:
        raise HTTPException(404, "Daily update not found")
    if u.user_id != user["id"]:
        raise HTTPException(403, "You can only edit your own update")
    if u.update_date != date.today().isoformat():
        raise HTTPException(400, "Only the same-day update can be edited")
    before = _out(u)
    for f in ("today", "tomorrow", "blockers", "status"):
        v = getattr(body, f)
        if v is not None:
            setattr(u, f, v.strip() if isinstance(v, str) and f != "status" else v)
    u.updated_at = now_iso()
    await record_audit(session, user, "daily_update.update", "daily_update", uid, before=before, after=_out(u),
                       ip=request.client.host if request.client else None)
    await session.commit()
    return _out(u)


def _or_user_or_dept(user_ids: set, dept_ids: list):
    from sqlalchemy import or_
    clauses = [DailyUpdate.user_id.in_(list(user_ids))]
    if dept_ids:
        clauses.append(DailyUpdate.department_id.in_(dept_ids))
    return or_(*clauses)
