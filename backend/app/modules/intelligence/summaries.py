"""AI summary pipelines (Modules 2 & 3) — daily updates + meetings.

Each summary stores BOTH the deterministic structured facts and an AI (or fallback)
narrative in Mongo `ai_summaries`. Generation is deduped by a hash of the source facts +
period so identical inputs are not re-summarized ("do not regenerate unnecessarily").
"""
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, Dict, Any, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db_mongo import db as mongo
from app.core.utils import new_id, now_iso
from app.modules.daily_updates.models import DailyUpdate
from app.modules.meetings.models import Meeting, ActionItem
from app.modules.rbac.resolver import direct_report_user_ids, user_department_ids
from app.modules.dashboards.service import department_user_ids
from app.modules.reporting.service import parse_dt
from app.modules.intelligence.ai import narrate, source_hash

SUBJECT_EMPLOYEE = "employee"
SUBJECT_TEAM = "team"
SUBJECT_DEPARTMENT = "department"

_DAILY_SYSTEM = ("You are an operations chief of staff. Produce a 2-4 sentence summary of a team's "
                 "daily updates: what got done, what's planned, and the blockers/risks that need attention.")
_MEETING_SYSTEM = ("You are an executive assistant. Produce a short executive summary of a meeting from its "
                   "notes, decisions, discussion points and action items. Highlight decisions and risks.")


async def _subject_user_ids(session: AsyncSession, subject_type: str, subject_id: str) -> List[str]:
    if subject_type == SUBJECT_EMPLOYEE:
        return [subject_id]
    if subject_type == SUBJECT_TEAM:
        team = await direct_report_user_ids(session, subject_id)
        team.add(subject_id)
        return list(team)
    if subject_type == SUBJECT_DEPARTMENT:
        return list(await department_user_ids(session, subject_id))
    return []


async def build_daily_update_data(session: AsyncSession, subject_type: str, subject_id: str,
                                  start: datetime, end: datetime) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    q = select(DailyUpdate).where(
        DailyUpdate.update_date >= start.date().isoformat(),
        DailyUpdate.update_date <= end.date().isoformat(),
    )
    if subject_type == SUBJECT_EMPLOYEE:
        q = q.where(DailyUpdate.user_id == subject_id)
    elif subject_type == SUBJECT_TEAM:
        uids = await _subject_user_ids(session, subject_type, subject_id)
        q = q.where(DailyUpdate.user_id.in_(uids or ["__none__"]))
    elif subject_type == SUBJECT_DEPARTMENT:
        q = q.where(DailyUpdate.department_id == subject_id)
    rows = (await session.execute(q.order_by(DailyUpdate.update_date))).scalars().all()

    completed = [u.today.strip() for u in rows if u.today and u.today.strip()]
    planned = [u.tomorrow.strip() for u in rows if u.tomorrow and u.tomorrow.strip()]
    blockers = [u.blockers.strip() for u in rows if u.blockers and u.blockers.strip()]
    participants = sorted({u.user_id for u in rows})
    expected = len(await _subject_user_ids(session, subject_type, subject_id)) if subject_type != SUBJECT_EMPLOYEE else 1

    risks: List[str] = []
    if blockers:
        risks.append(f"{len(blockers)} blocker(s) reported")
    if subject_type != SUBJECT_EMPLOYEE and expected and len(participants) < expected:
        risks.append(f"Low participation: {len(participants)}/{expected} submitted updates")

    structured = {
        "completed": completed, "planned": planned, "blockers": blockers, "risks": risks,
        "updates_count": len(rows), "participants": len(participants), "expected_participants": expected,
        "delayed_signals": len(blockers),
    }
    payload = {"subject_type": subject_type, "subject_id": subject_id,
               "period": [start.date().isoformat(), end.date().isoformat()], **structured}
    return structured, payload


def _daily_fallback(structured: Dict[str, Any]) -> str:
    parts = [f"{structured['updates_count']} update(s) from {structured['participants']} participant(s)."]
    if structured["completed"]:
        parts.append(f"Completed: {len(structured['completed'])} item(s).")
    if structured["planned"]:
        parts.append(f"Planned: {len(structured['planned'])} item(s).")
    if structured["blockers"]:
        parts.append(f"Blockers: {'; '.join(structured['blockers'][:3])}.")
    if structured["risks"]:
        parts.append("Risks: " + "; ".join(structured["risks"]) + ".")
    return " ".join(parts)


async def generate_daily_update_summary(session: AsyncSession, subject_type: str, subject_id: str,
                                        start: datetime, end: datetime, user: dict,
                                        force: bool = False) -> Dict[str, Any]:
    structured, payload = await build_daily_update_data(session, subject_type, subject_id, start, end)
    shash = source_hash(payload)
    existing = await mongo.ai_summaries.find_one({
        "summary_type": "daily_update", "subject_type": subject_type, "subject_id": subject_id,
        "period_start": start.date().isoformat(), "period_end": end.date().isoformat(),
    }, {"_id": 0})
    if existing and existing.get("source_hash") == shash and not force:
        existing["deduped"] = True
        return existing

    narrative, ai_used = await narrate(_DAILY_SYSTEM, payload, _daily_fallback(structured), user_id=user.get("id"),
                                       session_id=f"du-{subject_id}")
    doc = {
        "id": existing["id"] if existing else new_id(),
        "summary_type": "daily_update", "subject_type": subject_type, "subject_id": subject_id,
        "period_start": start.date().isoformat(), "period_end": end.date().isoformat(),
        "structured": structured, "narrative": narrative, "ai_used": ai_used,
        "source_hash": shash, "generated_by": user.get("id"), "created_at": now_iso(),
    }
    await mongo.ai_summaries.replace_one({"id": doc["id"]}, doc, upsert=True)
    doc["deduped"] = False
    return doc


async def build_meeting_data(session: AsyncSession, meeting: Meeting) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    items = (await session.execute(select(ActionItem).where(ActionItem.meeting_id == meeting.id))).scalars().all()
    now = datetime.now(timezone.utc)
    open_items = [a for a in items if a.status in ("open", "in_progress")]
    done_items = [a for a in items if a.status == "done"]
    overdue_items = [a for a in open_items if a.due_date and parse_dt(a.due_date) and parse_dt(a.due_date) < now]
    risks: List[str] = []
    if overdue_items:
        risks.append(f"{len(overdue_items)} overdue action item(s)")
    if meeting.status == "cancelled":
        risks.append("Meeting was cancelled")

    structured = {
        "title": meeting.title,
        "key_decisions": list(meeting.decisions or []),
        "discussion_points": list(meeting.discussion_points or []),
        "risks": risks,
        "action_items": {
            "total": len(items), "open": len(open_items), "done": len(done_items), "overdue": len(overdue_items),
            "list": [{"id": a.id, "title": a.title, "status": a.status, "owner_user_id": a.owner_user_id,
                      "due_date": a.due_date} for a in items],
        },
    }
    payload = {"meeting_id": meeting.id, "department_id": meeting.department_id,
               "notes": (meeting.notes or "")[:2000], **structured}
    return structured, payload


def _meeting_fallback(structured: Dict[str, Any]) -> str:
    ai = structured["action_items"]
    parts = [f"Meeting '{structured['title']}'."]
    if structured["key_decisions"]:
        parts.append(f"Decisions: {len(structured['key_decisions'])}.")
    parts.append(f"Action items: {ai['total']} ({ai['open']} open, {ai['overdue']} overdue).")
    if structured["risks"]:
        parts.append("Risks: " + "; ".join(structured["risks"]) + ".")
    return " ".join(parts)


async def generate_meeting_summary(session: AsyncSession, meeting: Meeting, user: dict,
                                   force: bool = False) -> Dict[str, Any]:
    structured, payload = await build_meeting_data(session, meeting)
    shash = source_hash(payload)
    existing = await mongo.ai_summaries.find_one(
        {"summary_type": "meeting", "subject_type": "meeting", "subject_id": meeting.id}, {"_id": 0})
    if existing and existing.get("source_hash") == shash and not force:
        existing["deduped"] = True
        return existing

    narrative, ai_used = await narrate(_MEETING_SYSTEM, payload, _meeting_fallback(structured), user_id=user.get("id"),
                                       session_id=f"mtg-{meeting.id}")
    doc = {
        "id": existing["id"] if existing else new_id(),
        "summary_type": "meeting", "subject_type": "meeting", "subject_id": meeting.id,
        "department_id": meeting.department_id,
        "structured": structured, "narrative": narrative, "ai_used": ai_used,
        "source_hash": shash, "generated_by": user.get("id"), "created_at": now_iso(),
    }
    await mongo.ai_summaries.replace_one({"id": doc["id"]}, doc, upsert=True)
    doc["deduped"] = False
    return doc
