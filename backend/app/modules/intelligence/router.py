"""Intelligence layer API.

Summaries (daily updates + meetings), risk detection, recommendations, the executive
intelligence dashboard, weekly/monthly reports, and executive digests. All reads/writes
are permission-gated; reports persist to the shared `reports` table (read via /reports).
"""
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db_mongo import db as mongo
from app.core.db_postgres import get_session
from app.core.security import get_current_user
from app.modules.meetings.models import Meeting, MeetingAttendee
from app.modules.org.models import Employee
from app.modules.rbac.resolver import require_permission, ensure_permission, user_can, direct_report_user_ids
from app.modules.audit.service import record_audit
from app.shared.activity import emit_activity
from app.modules.intelligence import summaries as S
from app.modules.intelligence import reports as R
from app.modules.intelligence.risk import detect_risks
from app.modules.intelligence.recommendations import build_recommendations
from app.modules.intelligence.dashboard import build_intelligence_dashboard
from app.modules.intelligence.digests import generate_digest, PERIOD_TYPES

router = APIRouter()


def _ref(ref_date: Optional[str]) -> datetime:
    if ref_date:
        d = S.parse_dt(ref_date + "T12:00:00+00:00")
        if d:
            return d
    return datetime.now(timezone.utc)


def _period(period_start: Optional[str], period_end: Optional[str]):
    end = _ref(period_end)
    start = S.parse_dt((period_start or "") + "T00:00:00+00:00") if period_start else (end - timedelta(days=7))
    return start, end


# ============ MODULE 2 — DAILY UPDATE SUMMARIES ============
async def _can_view_subject(session: AsyncSession, user: dict, subject_type: str, subject_id: str) -> bool:
    if user.get("is_admin"):
        return True
    if await user_can(session, user, "daily_update.view_all"):
        return True
    if subject_type == S.SUBJECT_EMPLOYEE:
        if subject_id == user["id"]:
            return True
        emp = (await session.execute(select(Employee).where(Employee.user_id == subject_id))).scalar_one_or_none()
        if emp and emp.primary_department_id and await user_can(session, user, "daily_update.view_department", department_id=emp.primary_department_id):
            return True
        if await user_can(session, user, "daily_update.view_team"):
            return subject_id in await direct_report_user_ids(session, user["id"])
        return False
    if subject_type == S.SUBJECT_TEAM:
        return subject_id == user["id"] and await user_can(session, user, "daily_update.view_team")
    if subject_type == S.SUBJECT_DEPARTMENT:
        return await user_can(session, user, "daily_update.view_department", department_id=subject_id)
    return False


@router.post("/intelligence/summaries/daily-update")
async def summarize_daily_updates(subject_type: str, subject_id: str,
                                  period_start: Optional[str] = None, period_end: Optional[str] = None,
                                  force: bool = False, user=Depends(get_current_user),
                                  session: AsyncSession = Depends(get_session)):
    if subject_type not in (S.SUBJECT_EMPLOYEE, S.SUBJECT_TEAM, S.SUBJECT_DEPARTMENT):
        raise HTTPException(400, "subject_type must be employee|team|department")
    if not await _can_view_subject(session, user, subject_type, subject_id):
        raise HTTPException(403, "No access to summarize this subject")
    start, end = _period(period_start, period_end)
    return await S.generate_daily_update_summary(session, subject_type, subject_id, start, end, user, force=force)


@router.get("/intelligence/summaries")
async def list_summaries(summary_type: Optional[str] = None, subject_type: Optional[str] = None,
                         subject_id: Optional[str] = None, limit: int = 50,
                         user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    limit = min(max(limit, 1), 200)
    if subject_id and subject_type:
        st = subject_type if subject_type != "meeting" else None
        if st and not await _can_view_subject(session, user, subject_type, subject_id):
            raise HTTPException(403, "No access to these summaries")
    elif not (user.get("is_admin") or await user_can(session, user, "daily_update.view_all")
              or await user_can(session, user, "intelligence.view")):
        raise HTTPException(403, "Missing permission to browse summaries")
    q = {}
    if summary_type:
        q["summary_type"] = summary_type
    if subject_type:
        q["subject_type"] = subject_type
    if subject_id:
        q["subject_id"] = subject_id
    return await mongo.ai_summaries.find(q, {"_id": 0}).sort("created_at", -1).to_list(limit)


# ============ MODULE 3 — MEETING SUMMARIES ============
async def _load_meeting_for_view(session: AsyncSession, user: dict, mid: str) -> Meeting:
    m = (await session.execute(select(Meeting).where(Meeting.id == mid))).scalar_one_or_none()
    if not m:
        raise HTTPException(404, "Meeting not found")
    if m.organizer_id == user["id"] or user.get("is_admin"):
        return m
    attendees = (await session.execute(select(MeetingAttendee.user_id).where(MeetingAttendee.meeting_id == mid))).scalars().all()
    if user["id"] in attendees:
        return m
    await ensure_permission(session, user, "meeting.mom.view", department_id=m.department_id)
    return m


@router.post("/intelligence/summaries/meeting/{mid}")
async def summarize_meeting(mid: str, force: bool = False,
                            user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    m = await _load_meeting_for_view(session, user, mid)
    return await S.generate_meeting_summary(session, m, user, force=force)


@router.get("/intelligence/summaries/meeting/{mid}")
async def get_meeting_summary(mid: str, user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    await _load_meeting_for_view(session, user, mid)
    doc = await mongo.ai_summaries.find_one({"summary_type": "meeting", "subject_id": mid}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "No summary yet — generate one first")
    return doc


# ============ MODULE 6 — RISKS ============
@router.get("/intelligence/risks")
async def list_risks(department_id: Optional[str] = None,
                     user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    if department_id:
        ok = await user_can(session, user, "intelligence.view") \
            or await user_can(session, user, "department.dashboard.view", department_id=department_id) \
            or await user_can(session, user, "report.view_department", department_id=department_id)
        if not ok and not user.get("is_admin"):
            raise HTTPException(403, "No access to this department's risks")
    else:
        await ensure_permission(session, user, "intelligence.view")
    risks = await detect_risks(session, datetime.now(timezone.utc), department_id=department_id)
    return {"department_id": department_id, "count": len(risks), "risks": risks}


# ============ MODULE 7 — EXECUTIVE INTELLIGENCE DASHBOARD ============
@router.get("/intelligence/dashboard")
async def intelligence_dashboard(user=Depends(require_permission("intelligence.view")),
                                 session: AsyncSession = Depends(get_session)):
    return await build_intelligence_dashboard(session, datetime.now(timezone.utc))


# ============ MODULE 8 — RECOMMENDATIONS ============
@router.get("/intelligence/recommendations")
async def recommendations(user=Depends(require_permission("intelligence.view")),
                          session: AsyncSession = Depends(get_session)):
    recs = await build_recommendations(session, datetime.now(timezone.utc))
    return {"count": len(recs), "recommendations": recs}


# ============ MODULES 4/5 — WEEKLY + MONTHLY REPORTS ============
@router.post("/intelligence/reports/weekly-department")
async def weekly_department_report(department_id: str, ref_date: Optional[str] = None, request: Request = None,
                                   user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    await ensure_permission(session, user, "report.view_department", department_id=department_id)
    r = await R.generate_weekly_department_report(session, department_id, _ref(ref_date), user)
    await record_audit(session, user, "intelligence.report.weekly", "report", r.id,
                       after={"department_id": department_id, "period": [r.period_start, r.period_end]},
                       ip=request.client.host if request and request.client else None)
    await session.commit()
    await emit_activity(user["id"], "report.generated", "report", r.id, department_id=department_id,
                        actor_name=user.get("name"), metadata={"type": "weekly_department"})
    return {"id": r.id, "report_type": r.report_type, "department_id": r.department_id,
            "period_start": r.period_start, "period_end": r.period_end, "summary": r.summary, "data": r.data}


@router.post("/intelligence/reports/monthly-executive")
async def monthly_executive_report(ref_date: Optional[str] = None, request: Request = None,
                                   user=Depends(require_permission("report.view_company")),
                                   session: AsyncSession = Depends(get_session)):
    r = await R.generate_monthly_executive_report(session, _ref(ref_date), user)
    await record_audit(session, user, "intelligence.report.monthly", "report", r.id,
                       after={"period": [r.period_start, r.period_end]},
                       ip=request.client.host if request and request.client else None)
    await session.commit()
    await emit_activity(user["id"], "report.generated", "report", r.id,
                        actor_name=user.get("name"), metadata={"type": "monthly_company"})
    return {"id": r.id, "report_type": r.report_type, "period_start": r.period_start,
            "period_end": r.period_end, "summary": r.summary, "data": r.data}


# ============ MODULE 9 — EXECUTIVE DIGESTS ============
@router.post("/intelligence/digests")
async def create_digest(period_type: str, ref_date: Optional[str] = None, force: bool = False, request: Request = None,
                        user=Depends(require_permission("executive.digest.view")),
                        session: AsyncSession = Depends(get_session)):
    if period_type not in PERIOD_TYPES:
        raise HTTPException(400, f"period_type must be one of {PERIOD_TYPES}")
    doc = await generate_digest(session, period_type, _ref(ref_date), user, force=force)
    await record_audit(session, user, "intelligence.digest.generate", "executive_digest", doc["id"],
                       after={"period_type": period_type, "period": [doc["period_start"], doc["period_end"]]},
                       ip=request.client.host if request and request.client else None)
    await session.commit()
    return doc


@router.get("/intelligence/digests")
async def list_digests(period_type: Optional[str] = None, limit: int = 30,
                       user=Depends(require_permission("executive.digest.view")),
                       session: AsyncSession = Depends(get_session)):
    limit = min(max(limit, 1), 100)
    q = {"period_type": period_type} if period_type else {}
    return await mongo.executive_digests.find(q, {"_id": 0}).sort("created_at", -1).to_list(limit)


@router.get("/intelligence/digests/{did}")
async def get_digest(did: str, user=Depends(require_permission("executive.digest.view")),
                     session: AsyncSession = Depends(get_session)):
    doc = await mongo.executive_digests.find_one({"id": did}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Digest not found")
    return doc
