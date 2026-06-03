"""Public, expiring shareable executive briefing."""
import json
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.core.db_mongo import db
from app.core.security import get_current_user
from app.core.deps import get_lang
from app.core.utils import now_iso, new_id
from app.modules.ai.service import claude_chat

router = APIRouter()


class ShareBriefIn(BaseModel):
    title: Optional[str] = None
    expires_days: Optional[int] = 30


@router.post("/share/brief")
async def create_share_brief(body: ShareBriefIn, user=Depends(get_current_user)):
    token = secrets.token_urlsafe(12)
    doc = {
        "id": new_id(),
        "token": token,
        "user_id": user["id"],
        "user_name": user["name"],
        "title": body.title or f"{user['name']}'s Daily Briefing",
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=body.expires_days or 30)).isoformat(),
        "created_at": now_iso(),
        "views": 0,
    }
    await db.share_briefs.insert_one(doc)
    return {"token": token, "share_url": f"/brief/{token}", "title": doc["title"], "expires_at": doc["expires_at"]}


@router.get("/share/brief/{token}")
async def get_share_brief(token: str, lang: str = Depends(get_lang)):
    s = await db.share_briefs.find_one({"token": token}, {"_id": 0})
    if not s:
        raise HTTPException(404, "Briefing not found")
    try:
        exp = datetime.fromisoformat(s["expires_at"])
        if exp < datetime.now(timezone.utc):
            raise HTTPException(410, "Briefing expired")
    except (ValueError, TypeError):
        pass
    await db.share_briefs.update_one({"token": token}, {"$inc": {"views": 1}})

    uid = s["user_id"]
    user = await db.users.find_one({"id": uid}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(404, "Owner not found")
    now = datetime.now(timezone.utc)
    tasks = await db.tasks.find({"owner_id": uid}, {"_id": 0}).to_list(500)
    projects = await db.projects.find({"members": uid}, {"_id": 0}).to_list(100)
    sessions = await db.focus_sessions.find({"user_id": uid}, {"_id": 0}).to_list(500)
    week_ago = now - timedelta(days=7)
    completed_week = [t for t in tasks if t.get("completed_at") and datetime.fromisoformat(t["completed_at"].replace("Z", "+00:00")) >= week_ago]
    week_focus = sum(s.get("duration_minutes", 0) for s in sessions if s.get("completed") and datetime.fromisoformat(s["created_at"].replace("Z", "+00:00")) >= week_ago)
    project_health = []
    for p in projects[:8]:
        ptasks = [t for t in tasks if t.get("project_id") == p["id"]]
        done = sum(1 for t in ptasks if t.get("status") == "done")
        progress = int(done * 100 / len(ptasks)) if ptasks else 0
        risk = "on_track"
        if any(t.get("status") == "blocked" for t in ptasks):
            risk = "at_risk"
        if any(t.get("status") != "done" and t.get("due_date") and datetime.fromisoformat(t["due_date"].replace("Z", "+00:00")) < now for t in ptasks):
            risk = "delayed"
        project_health.append({"name": p["name"], "progress": progress, "status": p.get("status"), "risk": risk, "task_count": len(ptasks)})

    cached = await db.share_briefs_cache.find_one({"user_id": uid, "lang": lang}, {"_id": 0})
    use_cache = False
    if cached:
        try:
            generated = datetime.fromisoformat(cached["generated_at"])
            if (now - generated).total_seconds() < 3600:
                use_cache = True
        except Exception:
            pass

    if use_cache:
        ai_narrative = cached["narrative"]
        top_risks = cached["top_risks"]
        strategic_actions = cached["strategic_actions"]
    else:
        compact = {
            "open_tasks": [{"title": t["title"], "priority": t.get("priority"), "status": t.get("status")} for t in tasks if t.get("status") != "done"][:20],
            "projects": project_health,
            "week_focus_min": week_focus,
            "completed_week": len(completed_week),
        }
        if lang == "en":
            system = """Produce an executive summary for public sharing from a founder to partners/investors. Write in English. Output VALID JSON only:
{
 "narrative": "One paragraph about the operational status (3 sentences max)",
 "top_risks": ["3 specific risks"],
 "strategic_actions": ["3 strategic steps"]
}
Confident, direct, no filler, no emoji."""
        else:
            system = """أنشئ ملخصًا تنفيذيًا للمشاركة العامة من مؤسس إلى شركائه/مستثمريه. اكتب بالعربية. أخرج JSON صالحًا فقط:
{
 "narrative": "فقرة واحدة عن حالة العمليات (٣ جمل كحد أقصى)",
 "top_risks": ["٣ مخاطر محددة"],
 "strategic_actions": ["٣ خطوات استراتيجية"]
}
واثق، مباشر، بدون حشو، بدون رموز إيموجي."""
        raw = await claude_chat(new_id(), system, json.dumps(compact), user_id=uid, lang=lang)
        try:
            si = raw.find("{"); ei = raw.rfind("}")
            d = json.loads(raw[si:ei+1]) if si >= 0 else {}
        except Exception:
            d = {}
        ai_narrative = d.get("narrative", "")
        top_risks = d.get("top_risks", [])
        strategic_actions = d.get("strategic_actions", [])
        await db.share_briefs_cache.update_one(
            {"user_id": uid, "lang": lang},
            {"$set": {"narrative": ai_narrative, "top_risks": top_risks, "strategic_actions": strategic_actions, "generated_at": now_iso()}},
            upsert=True,
        )

    velocity = len(completed_week)

    return {
        "title": s["title"],
        "owner_name": user["name"],
        "generated_at": now_iso(),
        "projects": project_health,
        "narrative": ai_narrative,
        "top_risks": top_risks,
        "strategic_actions": strategic_actions,
        "velocity": velocity,
        "weekly_focus_minutes": week_focus,
        "active_tasks": len([t for t in tasks if t.get("status") != "done"]),
        "views": s["views"] + 1,
    }


@router.get("/share/briefs")
async def list_my_briefs(user=Depends(get_current_user)):
    rows = await db.share_briefs.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(50)
    return rows


@router.delete("/share/brief/{token}")
async def del_brief(token: str, user=Depends(get_current_user)):
    await db.share_briefs.delete_one({"token": token, "user_id": user["id"]})
    return {"ok": True}
