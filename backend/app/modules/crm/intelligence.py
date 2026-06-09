"""CRM Intelligence (Module 9) — integrates with the Phase 3 intelligence layer.

Lead risk, opportunity risk, stalled deals, follow-up recommendations, and revenue
forecast insights. EXPLAINABLE and rule-based: every item carries its `source` data; the
optional narrative reuses the Phase 3 `narrate()` wrapper, which degrades to a
deterministic summary with no hallucination when AI is unavailable.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db_mongo import db as mongo
from app.core.db_postgres import get_session
from app.core.security import get_current_user
from app.modules.crm.models import CRMLead, CRMOpportunity
from app.modules.crm import service as svc
from app.modules.rbac.resolver import user_can
from app.modules.reporting.service import parse_dt
from app.modules.intelligence.risk import LEVEL_SCORE, _level
from app.modules.intelligence.ai import narrate

router = APIRouter()

STALL_DAYS = 14          # no activity in this many days => stalled
HIGH_VALUE = 10000.0     # value threshold for "high value, low probability" risk
LOW_PROBABILITY = 30     # probability at/below this is "low"


def _risk(rtype, level, title, description, source, department_id=None):
    return {"type": rtype, "level": level, "score": LEVEL_SCORE[level], "title": title,
            "description": description, "source": source, "department_id": department_id}


async def _last_activity_at(crm_entity_type: str, crm_entity_id: str) -> Optional[str]:
    doc = await mongo.crm_activities.find_one(
        {"crm_entity_type": crm_entity_type, "crm_entity_id": crm_entity_id},
        {"_id": 0, "created_at": 1}, sort=[("created_at", -1)])
    return (doc or {}).get("created_at")


async def detect_crm_risks(session: AsyncSession, now: datetime, department_id: Optional[str] = None) -> Dict[str, Any]:
    lq = select(CRMLead).where(CRMLead.status == "open")
    oq = select(CRMOpportunity).where(CRMOpportunity.status == "open")
    if department_id:
        lq = lq.where(CRMLead.department_id == department_id)
        oq = oq.where(CRMOpportunity.department_id == department_id)
    leads = (await session.execute(lq)).scalars().all()
    opps = (await session.execute(oq)).scalars().all()
    cutoff = now - timedelta(days=STALL_DAYS)

    risks: List[Dict[str, Any]] = []
    follow_ups: List[Dict[str, Any]] = []

    # --- Lead risk: high value + low probability ---
    hv_leads = [l for l in leads if (l.value or 0) >= HIGH_VALUE and (l.probability or 0) <= LOW_PROBABILITY]
    if hv_leads:
        risks.append(_risk("lead_risk", _level(len(hv_leads), 1, 3, 6),
                           f"{len(hv_leads)} high-value low-probability lead(s)",
                           "Leads worth chasing whose probability is low.",
                           {"count": len(hv_leads), "samples": [{"id": l.id, "title": l.title, "value": l.value,
                            "probability": l.probability} for l in hv_leads[:5]]}, department_id))

    # --- Stalled leads ---
    stalled_leads = []
    for l in leads:
        last = await _last_activity_at("lead", l.id)
        anchor = parse_dt(last) or parse_dt(l.created_at)
        if anchor and anchor < cutoff:
            stalled_leads.append({"id": l.id, "title": l.title, "last_activity": last, "stage": l.stage})
            follow_ups.append({"entity_type": "lead", "entity_id": l.id, "title": l.title,
                               "reason": f"No activity in {STALL_DAYS}+ days", "last_activity": last})
    if stalled_leads:
        risks.append(_risk("stalled_lead", _level(len(stalled_leads), 1, 3, 6),
                           f"{len(stalled_leads)} stalled lead(s)", f"Open leads with no activity in {STALL_DAYS}+ days.",
                           {"count": len(stalled_leads), "samples": stalled_leads[:5]}, department_id))

    # --- Stalled deals (opportunities) ---
    stalled_deals = []
    overdue_close = []
    for o in opps:
        last = await _last_activity_at("opportunity", o.id)
        anchor = parse_dt(last) or parse_dt(o.created_at)
        if anchor and anchor < cutoff:
            stalled_deals.append({"id": o.id, "name": o.name, "expected_revenue": o.expected_revenue,
                                  "stage": o.stage, "last_activity": last})
            follow_ups.append({"entity_type": "opportunity", "entity_id": o.id, "title": o.name,
                               "reason": f"No activity in {STALL_DAYS}+ days", "last_activity": last})
        close = parse_dt(o.expected_close_date)
        if close and close < now:
            overdue_close.append({"id": o.id, "name": o.name, "expected_close_date": o.expected_close_date,
                                  "expected_revenue": o.expected_revenue})
    if stalled_deals:
        risks.append(_risk("stalled_deal", _level(len(stalled_deals), 1, 3, 6),
                           f"{len(stalled_deals)} stalled deal(s)", f"Open opportunities idle for {STALL_DAYS}+ days.",
                           {"count": len(stalled_deals), "samples": stalled_deals[:5],
                            "stalled_value": round(sum(d["expected_revenue"] or 0 for d in stalled_deals), 2)}, department_id))
    if overdue_close:
        risks.append(_risk("opportunity_risk", _level(len(overdue_close), 1, 3, 6),
                           f"{len(overdue_close)} deal(s) past expected close",
                           "Open opportunities whose expected close date has passed.",
                           {"count": len(overdue_close), "samples": overdue_close[:5],
                            "at_risk_value": round(sum(d["expected_revenue"] or 0 for d in overdue_close), 2)}, department_id))

    risks.sort(key=lambda r: -r["score"])
    return {"risks": risks, "follow_ups": follow_ups[:20], "open_leads": len(leads), "open_opps": len(opps)}


async def forecast_insights(session: AsyncSession, now: datetime, department_id: Optional[str] = None) -> Dict[str, Any]:
    oq = select(CRMOpportunity)
    if department_id:
        oq = oq.where(CRMOpportunity.department_id == department_id)
    opps = (await session.execute(oq)).scalars().all()
    open_opps = [o for o in opps if o.status == "open"]
    month_end = (now.replace(day=28) + timedelta(days=4)).replace(day=1)
    closing_this_month = [o for o in open_opps if (parse_dt(o.expected_close_date) and parse_dt(o.expected_close_date) < month_end)]
    weighted = sum((o.expected_revenue or 0) * (o.probability or 0) / 100.0 for o in open_opps)
    at_risk = [o for o in open_opps if parse_dt(o.expected_close_date) and parse_dt(o.expected_close_date) < now]
    return {
        "open_pipeline": round(sum(o.expected_revenue or 0 for o in open_opps), 2),
        "weighted_forecast": round(weighted, 2),
        "expected_close_this_month": {"count": len(closing_this_month),
                                      "value": round(sum(o.expected_revenue or 0 for o in closing_this_month), 2)},
        "at_risk_revenue": round(sum(o.expected_revenue or 0 for o in at_risk), 2),
        "won_revenue": round(sum(o.expected_revenue or 0 for o in opps if o.status == "won"), 2),
    }


@router.get("/crm/intelligence")
async def crm_intelligence(department_id: Optional[str] = None,
                           user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    if department_id:
        ok = user.get("is_admin") \
            or await user_can(session, user, "intelligence.view") \
            or await user_can(session, user, "crm.opportunity.view", department_id=department_id)
        if not ok:
            raise HTTPException(403, "No access to this department's CRM intelligence")
    else:
        ok = user.get("is_admin") \
            or await user_can(session, user, "intelligence.view") \
            or await user_can(session, user, "company.dashboard.view")
        if not ok:
            raise HTTPException(403, "Missing permission: intelligence.view")

    now = datetime.now(timezone.utc)
    detected = await detect_crm_risks(session, now, department_id)
    forecast = await forecast_insights(session, now, department_id)
    payload = {"risks": detected["risks"], "follow_ups": detected["follow_ups"], "forecast": forecast}
    fallback = (f"{len(detected['risks'])} CRM risk(s); {len(detected['follow_ups'])} follow-up(s); "
                f"weighted forecast {forecast['weighted_forecast']}, at-risk revenue {forecast['at_risk_revenue']}.")
    narrative, ai_used = await narrate(
        "You are a sales operations analyst. Summarize CRM pipeline risks and forecast for an executive.",
        payload, fallback, user_id=user.get("id"), session_id="crm-intel")
    return {
        "department_id": department_id,
        "risks": detected["risks"],
        "follow_up_recommendations": detected["follow_ups"],
        "forecast_insights": forecast,
        "open_leads": detected["open_leads"],
        "open_opportunities": detected["open_opps"],
        "narrative": narrative,
        "ai_used": ai_used,
    }
