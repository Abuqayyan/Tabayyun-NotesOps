"""Deterministic health scoring shared by reports and the executive dashboard.

A health score is 100 minus explainable penalties: overdue ratio, blocked/critical work,
risk load, low participation, and approval backlog. Same inputs always yield the same score.
"""
from typing import Dict, Any, List

_RISK_PENALTY = {"low": 2, "medium": 5, "high": 10, "critical": 18}


def health_score(metrics: Dict[str, Any], participation: Dict[str, Any], risks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Return {score, grade, penalties} for a scope given its metrics/participation/risks."""
    tasks = metrics.get("tasks", {})
    open_t = tasks.get("open", 0)
    delayed = tasks.get("delayed", 0)
    approvals = metrics.get("approvals", {})
    pending = approvals.get("pending", 0)

    penalties: Dict[str, int] = {}
    # Overdue ratio (up to -35)
    if open_t:
        ratio = delayed / open_t
        penalties["overdue"] = int(min(35, ratio * 45))
    elif delayed:
        penalties["overdue"] = 15
    # Critical open work (up to -15)
    penalties["critical_open"] = int(min(15, tasks.get("critical_open", 0) * 3))
    # Risk load (sum of leveled penalties, capped -40)
    penalties["risks"] = int(min(40, sum(_RISK_PENALTY.get(r["level"], 0) for r in risks)))
    # Low participation (up to -15)
    pr = participation.get("participation_rate", 100) if participation else 100
    penalties["participation"] = int(min(15, (100 - pr) * 0.15))
    # Approval backlog (up to -10)
    penalties["approval_backlog"] = int(min(10, pending * 2))

    score = max(0, min(100, 100 - sum(penalties.values())))
    grade = "excellent" if score >= 85 else "good" if score >= 70 else "fair" if score >= 50 else "poor"
    return {"score": score, "grade": grade, "penalties": penalties}
