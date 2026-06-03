"""Reporting API: generate + read stored report snapshots.

Generation computes raw metrics for a (scope, period) from the live stores and persists
them. No AI summarisation here (Phase 3) — `summary` stays empty by design.
"""
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db_mongo import db as mongo
from app.core.db_postgres import get_session
from app.core.security import get_current_user
from app.modules.reporting.models import Report
from app.modules.meetings.models import Meeting
from app.modules.approvals.models import ApprovalRequest
from app.modules.daily_updates.models import DailyUpdate
from app.modules.org.models import Department
from app.modules.rbac.resolver import ensure_permission, get_permission_keys, user_department_ids
from app.modules.audit.service import record_audit
from app.modules.dashboards.service import department_user_ids
# Reuse the shared reporting foundation (Module 10) for metrics + period parsing.
from app.modules.reporting.service import compute_metrics as _compute_metrics, parse_dt as _parse

router = APIRouter()

_DEPARTMENT_TYPES = {"weekly_department", "monthly_department"}
_COMPANY_TYPES = {"weekly_company", "monthly_company", "executive"}


class ReportGenerateIn(BaseModel):
    report_type: str
    department_id: Optional[str] = None
    period_start: str  # YYYY-MM-DD
    period_end: str    # YYYY-MM-DD


def _out(r: Report) -> dict:
    return {"id": r.id, "report_type": r.report_type, "scope_type": r.scope_type,
            "department_id": r.department_id, "period_start": r.period_start, "period_end": r.period_end,
            "data": r.data or {}, "summary": r.summary, "status": r.status,
            "generated_by": r.generated_by, "created_at": r.created_at}


@router.post("/reports/generate")
async def generate_report(body: ReportGenerateIn, request: Request,
                          user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    if body.report_type in _DEPARTMENT_TYPES:
        if not body.department_id:
            raise HTTPException(400, "department_id required for department reports")
        await ensure_permission(session, user, "report.view_department", department_id=body.department_id)
        scope_type = "department"
    elif body.report_type in _COMPANY_TYPES:
        await ensure_permission(session, user, "report.view_company")
        scope_type = "company"
    else:
        raise HTTPException(400, f"Unknown report_type: {body.report_type}")

    start = _parse(body.period_start + "T00:00:00+00:00")
    end = _parse(body.period_end + "T23:59:59+00:00")
    if not start or not end or start > end:
        raise HTTPException(400, "Invalid period_start/period_end")

    if scope_type == "department":
        if not (await session.execute(select(Department).where(Department.id == body.department_id))).scalar_one_or_none():
            raise HTTPException(404, "Department not found")
        user_ids = list(await department_user_ids(session, body.department_id))
        data = await _compute_metrics(session, user_ids, body.department_id, start, end)
    else:
        data = await _compute_metrics(session, None, None, start, end)
        # Executive/company reports include a per-department breakdown.
        depts = (await session.execute(select(Department))).scalars().all()
        breakdown = []
        for d in depts:
            uids = list(await department_user_ids(session, d.id))
            breakdown.append({"department_id": d.id, "name": d.name,
                              **(await _compute_metrics(session, uids, d.id, start, end))})
        data["departments"] = breakdown

    r = Report(report_type=body.report_type, scope_type=scope_type, department_id=body.department_id,
               period_start=body.period_start, period_end=body.period_end, data=data, summary="",
               status="generated", generated_by=user["id"])
    session.add(r)
    await session.flush()
    await record_audit(session, user, "report.generate", "report", r.id,
                       after={"report_type": r.report_type, "scope": scope_type, "department_id": body.department_id},
                       ip=request.client.host if request.client else None)
    await session.commit()
    return _out(r)


@router.get("/reports")
async def list_reports(report_type: Optional[str] = None, department_id: Optional[str] = None, limit: int = 100,
                       user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    limit = min(max(limit, 1), 500)
    perms = await get_permission_keys(session, user)
    has_company = "report.view_company" in perms
    my_depts = await user_department_ids(session, user["id"])

    q = select(Report).order_by(Report.created_at.desc())
    if report_type:
        q = q.where(Report.report_type == report_type)
    if department_id:
        q = q.where(Report.department_id == department_id)
    rows = (await session.execute(q.limit(500))).scalars().all()

    out = []
    for r in rows:
        if has_company or user.get("is_admin"):
            visible = True
        elif r.scope_type == "department" and r.department_id:
            visible = ("report.view_department" in perms) and (
                r.department_id in my_depts or await user_can_dept_report(session, user, r.department_id))
        else:
            visible = False
        if visible:
            out.append(_out(r))
        if len(out) >= limit:
            break
    return out


async def user_can_dept_report(session: AsyncSession, user: dict, department_id: str) -> bool:
    from app.modules.rbac.resolver import user_can
    return await user_can(session, user, "report.view_department", department_id=department_id)


@router.get("/reports/{rid}")
async def get_report(rid: str, user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    r = (await session.execute(select(Report).where(Report.id == rid))).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "Report not found")
    if not user.get("is_admin"):
        if r.scope_type == "company":
            await ensure_permission(session, user, "report.view_company")
        else:
            await ensure_permission(session, user, "report.view_department", department_id=r.department_id)
    return _out(r)
