"""CRM Dashboards (Module 8): department pipeline/forecast/conversion + executive rollup."""
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db_postgres import get_session
from app.core.security import get_current_user
from app.modules.crm.models import CRMLead, CRMOpportunity, LEAD_STAGES, OPP_STAGES
from app.modules.rbac.resolver import user_can
from app.modules.crm import service as svc

router = APIRouter()


def _lead_aggregates(leads: List[CRMLead]) -> Dict[str, Any]:
    by_stage = {s: 0 for s in LEAD_STAGES}
    won = lost = 0
    for l in leads:
        by_stage[l.stage] = by_stage.get(l.stage, 0) + 1
        if l.status == "won":
            won += 1
        elif l.status == "lost":
            lost += 1
    total = len(leads)
    closed = won + lost
    return {"total": total, "by_stage": by_stage, "won": won, "lost": lost,
            "conversion_rate": int(won * 100 / closed) if closed else 0}


def _opp_aggregates(opps: List[CRMOpportunity]) -> Dict[str, Any]:
    by_stage = {s: {"count": 0, "value": 0.0, "weighted": 0.0} for s in OPP_STAGES}
    open_pipeline = weighted = won_rev = lost_rev = 0.0
    won = lost = 0
    for o in opps:
        col = by_stage.setdefault(o.stage, {"count": 0, "value": 0.0, "weighted": 0.0})
        col["count"] += 1
        col["value"] += o.expected_revenue or 0
        col["weighted"] += (o.expected_revenue or 0) * (o.probability or 0) / 100.0
        if o.status == "open":
            open_pipeline += o.expected_revenue or 0
            weighted += (o.expected_revenue or 0) * (o.probability or 0) / 100.0
        elif o.status == "won":
            won_rev += o.expected_revenue or 0
            won += 1
        elif o.status == "lost":
            lost_rev += o.expected_revenue or 0
            lost += 1
    for col in by_stage.values():
        col["value"] = round(col["value"], 2)
        col["weighted"] = round(col["weighted"], 2)
    closed = won + lost
    return {"by_stage": by_stage, "total_pipeline": round(open_pipeline, 2), "weighted_forecast": round(weighted, 2),
            "won_revenue": round(won_rev, 2), "lost_revenue": round(lost_rev, 2),
            "win_rate": int(won * 100 / closed) if closed else 0, "won": won, "lost": lost}


@router.get("/crm/dashboards/department/{dept_id}")
async def department_crm_dashboard(dept_id: str, user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    ok = user.get("is_admin") \
        or await user_can(session, user, "crm.opportunity.view", department_id=dept_id) \
        or await user_can(session, user, "department.dashboard.view", department_id=dept_id)
    if not ok:
        raise HTTPException(403, "No access to this department's CRM dashboard")
    leads = (await session.execute(select(CRMLead).where(CRMLead.department_id == dept_id))).scalars().all()
    opps = (await session.execute(select(CRMOpportunity).where(CRMOpportunity.department_id == dept_id))).scalars().all()
    la = _lead_aggregates(leads)
    oa = _opp_aggregates(opps)
    return {
        "department_id": dept_id,
        "leads": la,
        "opportunities": oa,
        "revenue_forecast": oa["weighted_forecast"],
        "conversion_rates": {"lead_conversion": la["conversion_rate"], "opportunity_win_rate": oa["win_rate"]},
    }


@router.get("/crm/dashboards/executive")
async def executive_crm_dashboard(user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    ok = user.get("is_admin") \
        or await user_can(session, user, "company.dashboard.view") \
        or await user_can(session, user, "intelligence.view")
    if not ok:
        raise HTTPException(403, "Missing permission: company.dashboard.view")
    leads = (await session.execute(select(CRMLead))).scalars().all()
    opps = (await session.execute(select(CRMOpportunity))).scalars().all()
    la = _lead_aggregates(leads)
    oa = _opp_aggregates(opps)

    open_opps = [o for o in opps if o.status == "open"]
    top = sorted(open_opps, key=lambda o: -(o.expected_revenue or 0))[:10]
    top_opportunities = [{"id": o.id, "name": o.name, "expected_revenue": o.expected_revenue,
                          "probability": o.probability, "stage": o.stage, "owner_id": o.owner_id} for o in top]

    # Team performance per owner
    perf: Dict[str, Dict[str, Any]] = {}
    for o in opps:
        p = perf.setdefault(o.owner_id or "unassigned", {"owner_id": o.owner_id, "open_pipeline": 0.0,
                                                          "won_revenue": 0.0, "won": 0, "open": 0})
        if o.status == "open":
            p["open_pipeline"] += o.expected_revenue or 0
            p["open"] += 1
        elif o.status == "won":
            p["won_revenue"] += o.expected_revenue or 0
            p["won"] += 1
    team_performance = sorted(perf.values(), key=lambda x: -x["won_revenue"])
    for p in team_performance:
        p["open_pipeline"] = round(p["open_pipeline"], 2)
        p["won_revenue"] = round(p["won_revenue"], 2)
    await svc.enrich_users(team_performance)

    return {
        "total_pipeline": oa["total_pipeline"],
        "weighted_forecast": oa["weighted_forecast"],
        "won_revenue": oa["won_revenue"],
        "lost_revenue": oa["lost_revenue"],
        "conversion_trends": {"lead_conversion": la["conversion_rate"], "opportunity_win_rate": oa["win_rate"],
                              "leads_total": la["total"], "opps_won": oa["won"], "opps_lost": oa["lost"]},
        "pipeline_by_stage": oa["by_stage"],
        "top_opportunities": top_opportunities,
        "team_performance": team_performance,
    }
