"""Dashboard summary + time-aware greeting + service root."""
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends

from app.core.config import APP_NAME
from app.core.db_mongo import db
from app.core.security import get_current_user
from app.core.deps import get_lang
from app.core.utils import now_iso

router = APIRouter()


@router.get("/")
async def root():
    return {"app": APP_NAME, "version": "1.0", "status": "ok"}


@router.get("/dashboard/summary")
async def dashboard_summary(user=Depends(get_current_user)):
    uid = user["id"]
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    projects = await db.projects.find({"members": uid}, {"_id": 0}).to_list(500)
    tasks = await db.tasks.find({"owner_id": uid}, {"_id": 0}).to_list(1000)
    sessions = await db.focus_sessions.find({"user_id": uid}, {"_id": 0}).to_list(500)

    total_tasks = len(tasks)
    done = [t for t in tasks if t.get("status") == "done"]
    in_progress = [t for t in tasks if t.get("status") == "in_progress"]
    blocked = [t for t in tasks if t.get("status") == "blocked"]
    todo = [t for t in tasks if t.get("status") == "todo"]

    delayed = []
    for t in tasks:
        if t.get("status") != "done" and t.get("due_date"):
            try:
                d = datetime.fromisoformat(t["due_date"].replace("Z", "+00:00"))
                if d < now:
                    delayed.append(t)
            except Exception:
                pass

    weekly_focus_minutes = 0
    for s in sessions:
        try:
            d = datetime.fromisoformat(s["created_at"].replace("Z", "+00:00"))
            if d >= week_ago and s.get("completed"):
                weekly_focus_minutes += s.get("duration_minutes", 0)
        except Exception:
            pass

    weekly_completed = 0
    for t in done:
        if t.get("completed_at"):
            try:
                d = datetime.fromisoformat(t["completed_at"].replace("Z", "+00:00"))
                if d >= week_ago:
                    weekly_completed += 1
            except Exception:
                pass

    completion_rate = int(len(done) * 100 / total_tasks) if total_tasks else 0
    focus_score = min(100, int(weekly_focus_minutes / 12))
    burnout_risk = "low"
    workload_load = len(in_progress) + len(todo)
    if workload_load > 15:
        burnout_risk = "high"
    elif workload_load > 8:
        burnout_risk = "medium"
    execution_score = min(100, weekly_completed * 12)

    upcoming = []
    for t in tasks:
        if t.get("status") != "done" and t.get("due_date"):
            try:
                d = datetime.fromisoformat(t["due_date"].replace("Z", "+00:00"))
                if d >= now and (d - now).days <= 7:
                    upcoming.append(t)
            except Exception:
                pass
    upcoming.sort(key=lambda x: x["due_date"])

    return {
        "projects_active": len([p for p in projects if p.get("status") == "active"]),
        "projects_total": len(projects),
        "tasks_total": total_tasks,
        "tasks_done": len(done),
        "tasks_in_progress": len(in_progress),
        "tasks_blocked": len(blocked),
        "tasks_todo": len(todo),
        "tasks_delayed": len(delayed),
        "completion_rate": completion_rate,
        "focus_score": focus_score,
        "execution_score": execution_score,
        "burnout_risk": burnout_risk,
        "workload_load": workload_load,
        "weekly_focus_minutes": weekly_focus_minutes,
        "weekly_completed": weekly_completed,
        "upcoming_deadlines": upcoming[:6],
        "blocked_tasks": blocked[:6],
        "projects": projects[:6],
    }


@router.get("/dashboard/greeting")
async def dashboard_greeting(user=Depends(get_current_user), lang: str = Depends(get_lang)):
    """Time-aware greeting + a single smart prompt based on today's state."""
    uid = user["id"]
    now = datetime.now(timezone.utc)
    hour = now.hour
    AR = (lang == "ar")
    if hour < 5:
        period, greeting = "late", ("تعمل متأخرًا" if AR else "Working late")
    elif hour < 12:
        period, greeting = "morning", ("صباح الخير" if AR else "Good morning")
    elif hour < 17:
        period, greeting = "afternoon", ("مساء النور" if AR else "Good afternoon")
    elif hour < 21:
        period, greeting = "evening", ("مساء الخير" if AR else "Good evening")
    else:
        period, greeting = "night", ("ليلة سعيدة" if AR else "Good night")

    name = (user.get("name") or "").split(" ")[0]

    tasks = await db.tasks.find({"owner_id": uid}, {"_id": 0, "status": 1, "due_date": 1, "priority": 1, "title": 1, "id": 1}).to_list(500)
    open_tasks = [t for t in tasks if t.get("status") != "done"]
    in_progress = [t for t in open_tasks if t.get("status") == "in_progress"]
    overdue = []
    for t in open_tasks:
        if t.get("due_date"):
            try:
                d = datetime.fromisoformat(t["due_date"].replace("Z", "+00:00"))
                if d < now:
                    overdue.append(t)
            except Exception:
                pass

    prompt = None
    if period == "morning":
        if in_progress:
            prompt = (f"تابع من حيث توقفت: {in_progress[0]['title']}" if AR else f"Pick up where you left off: {in_progress[0]['title']}")
        elif overdue:
            prompt = (f"{len(overdue)} مهمة متأخرة. أزل العوائق أولًا." if AR else f"{len(overdue)} task{'s' if len(overdue) != 1 else ''} overdue. Clear blockers first.")
        elif open_tasks:
            top = next((t for t in open_tasks if t.get("priority") in ("high", "critical")), open_tasks[0])
            prompt = (f"ابدأ بـ: {top['title']}" if AR else f"Start with: {top['title']}")
        else:
            prompt = ("صفحة بيضاء. خطّط لثلاث انتصارات اليوم." if AR else "Clean slate. Plan today's three wins.")
    elif period == "afternoon":
        if overdue:
            prompt = (f"{len(overdue)} مهمة تنزلق. افرز الآن." if AR else f"{len(overdue)} task{'s' if len(overdue) != 1 else ''} slipping. Triage now.")
        elif in_progress:
            prompt = (f"حافظ على الزخم في: {in_progress[0]['title']}" if AR else f"Keep momentum on: {in_progress[0]['title']}")
        else:
            prompt = ("نافذة تركيز بعد الظهر — اختر مهمة عالية الأثر." if AR else "Afternoon focus block — pick one high-impact task.")
    elif period == "evening":
        prompt = ("أنهِ الأطراف العالقة وجهّز أولوية الغد." if AR else "Wrap up loose ends and queue tomorrow's top priority.")
    elif period == "night":
        prompt = ("حان وقت الاسترخاء. ملخص الغد سيكون جاهزًا عند عودتك." if AR else "Time to unwind. Tomorrow's brief will be ready when you return.")
    else:
        prompt = ("النوم رافعة. احفظه للغد." if AR else "Sleep is leverage. Save it for tomorrow.")

    return {
        "greeting": greeting,
        "name": name,
        "period": period,
        "prompt": prompt,
        "hour": hour,
        "stats": {
            "open_tasks": len(open_tasks),
            "in_progress": len(in_progress),
            "overdue": len(overdue),
        },
    }
