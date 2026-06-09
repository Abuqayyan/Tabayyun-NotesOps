"""Analytics: 14-day overview + productivity intelligence."""
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends

from app.core.db_mongo import db
from app.core.security import get_current_user

router = APIRouter()


@router.get("/analytics/overview")
async def analytics_overview(user=Depends(get_current_user)):
    uid = user["id"]
    now = datetime.now(timezone.utc)
    days = 14
    daily = []
    sessions = await db.focus_sessions.find({"user_id": uid}, {"_id": 0}).to_list(1000)
    tasks = await db.tasks.find({"owner_id": uid}, {"_id": 0}).to_list(1000)
    for i in range(days - 1, -1, -1):
        day = (now - timedelta(days=i)).date()
        day_start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        focus_min = 0
        for s in sessions:
            try:
                d = datetime.fromisoformat(s["created_at"].replace("Z", "+00:00"))
                if day_start <= d < day_end and s.get("completed"):
                    focus_min += s.get("duration_minutes", 0)
            except Exception:
                pass
        completed = 0
        for t in tasks:
            if t.get("completed_at"):
                try:
                    d = datetime.fromisoformat(t["completed_at"].replace("Z", "+00:00"))
                    if day_start <= d < day_end:
                        completed += 1
                except Exception:
                    pass
        daily.append({
            "date": day.isoformat(),
            "label": day.strftime("%a"),
            "focus_minutes": focus_min,
            "completed": completed,
        })

    heatmap = [[0]*24 for _ in range(7)]
    for s in sessions:
        try:
            d = datetime.fromisoformat(s["created_at"].replace("Z", "+00:00"))
            heatmap[d.weekday()][d.hour] += s.get("duration_minutes", 0)
        except Exception:
            pass

    pri = {"low": 0, "medium": 0, "high": 0, "critical": 0}
    for t in tasks:
        p = t.get("priority", "medium")
        pri[p] = pri.get(p, 0) + 1

    accuracy = []
    for t in tasks:
        if t.get("status") == "done" and t.get("estimated_minutes") and t.get("actual_minutes"):
            est = t["estimated_minutes"]; act = t["actual_minutes"]
            ratio = min(est, act) / max(est, act) if max(est, act) else 0
            accuracy.append(int(ratio * 100))
    avg_accuracy = int(sum(accuracy)/len(accuracy)) if accuracy else 0

    return {
        "daily": daily,
        "heatmap": heatmap,
        "priority_distribution": pri,
        "estimate_accuracy": avg_accuracy,
    }


@router.get("/analytics/intelligence")
async def analytics_intelligence(user=Depends(get_current_user)):
    uid = user["id"]
    now = datetime.now(timezone.utc)
    sessions = await db.focus_sessions.find({"user_id": uid}, {"_id": 0}).to_list(2000)
    tasks = await db.tasks.find({"owner_id": uid}, {"_id": 0}).to_list(1000)

    hour_min = [0] * 24
    for s in sessions:
        try:
            d = datetime.fromisoformat(s["created_at"].replace("Z", "+00:00"))
            hour_min[d.hour] += s.get("duration_minutes", 0)
        except Exception:
            pass
    top_hours_idx = sorted(range(24), key=lambda h: -hour_min[h])[:3]
    best_hours = [{"hour": h, "minutes": hour_min[h]} for h in top_hours_idx if hour_min[h] > 0]

    active_days = set()
    for t in tasks:
        if t.get("completed_at"):
            try:
                d = datetime.fromisoformat(t["completed_at"].replace("Z", "+00:00")).date()
                if (now.date() - d).days <= 14:
                    active_days.add(d.isoformat())
            except Exception:
                pass
    consistency_pct = int(len(active_days) * 100 / 14)

    procrastinated = []
    for t in tasks:
        if t.get("status") != "done" and t.get("due_date"):
            try:
                d = datetime.fromisoformat(t["due_date"].replace("Z", "+00:00"))
                upd = datetime.fromisoformat(t.get("updated_at", t.get("created_at", now.isoformat())).replace("Z", "+00:00"))
                if d < now and (now - upd).days >= 3:
                    procrastinated.append({"id": t["id"], "title": t["title"], "days_overdue": (now - d).days})
            except Exception:
                pass

    accuracy_records = []
    for t in tasks:
        if t.get("status") == "done" and t.get("estimated_minutes") and t.get("actual_minutes"):
            est, act = t["estimated_minutes"], t["actual_minutes"]
            ratio = min(est, act) / max(est, act)
            accuracy_records.append({"ratio": ratio, "delta": act - est})
    avg_accuracy = int(sum(r["ratio"] for r in accuracy_records) / len(accuracy_records) * 100) if accuracy_records else 0
    tends_to = "underestimate" if accuracy_records and sum(r["delta"] for r in accuracy_records) > 0 else "overestimate" if accuracy_records else "unknown"

    days_with_session = set()
    for s in sessions:
        if s.get("completed"):
            try:
                d = datetime.fromisoformat(s["created_at"].replace("Z", "+00:00")).date()
                days_with_session.add(d)
            except Exception:
                pass
    streak = 0
    cur = now.date()
    while cur in days_with_session:
        streak += 1
        cur = cur - timedelta(days=1)

    short_sessions = sum(1 for s in sessions if s.get("duration_minutes", 0) < 15)
    interruption_rate = int(short_sessions * 100 / len(sessions)) if sessions else 0

    return {
        "best_hours": best_hours,
        "consistency_pct": consistency_pct,
        "active_days_14": len(active_days),
        "procrastinated": procrastinated[:10],
        "estimate_accuracy": avg_accuracy,
        "tends_to": tends_to,
        "focus_streak_days": streak,
        "interruption_rate_pct": interruption_rate,
        "total_focus_sessions": len([s for s in sessions if s.get("completed")]),
        "total_focus_minutes": sum(s.get("duration_minutes", 0) for s in sessions if s.get("completed")),
    }
