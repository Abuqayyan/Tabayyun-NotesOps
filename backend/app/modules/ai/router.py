"""AI endpoints: chat, rewrite, breakdown, summaries, prioritization, briefs, memory, AI settings."""
import json
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel

from app.core.config import DEFAULT_CLAUDE_MODEL, SUPPORTED_MODELS, FERNET
from app.core.db_mongo import db
from app.core.security import get_current_user
from app.core.deps import get_lang
from app.core.utils import now_iso, new_id, clean
from app.shared.rate_limit import limiter, LIMIT_AI
from app.modules.ai.service import (
    claude_chat, build_user_context, get_user_ai_config, compute_priority_score,
)

router = APIRouter()


# ---- Models ----
class AIChatIn(BaseModel):
    message: str
    session_id: Optional[str] = None
    context_type: Optional[str] = "general"
    context_id: Optional[str] = None


class AIRewriteIn(BaseModel):
    text: str
    tone: Optional[str] = "professional"


class AIBreakdownIn(BaseModel):
    task_id: str


class AISummaryIn(BaseModel):
    project_id: str


class MemoryIn(BaseModel):
    content: str
    type: Optional[str] = "note"
    tags: Optional[List[str]] = []


class ScheduleSuggestIn(BaseModel):
    project_id: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = ""
    estimated_days: Optional[int] = None
    priority: Optional[str] = "medium"


class AISettingsIn(BaseModel):
    api_key: Optional[str] = None
    model: Optional[str] = None
    use_own_key: Optional[bool] = None


# ---- Chat ----
@router.post("/ai/chat")
@limiter.limit(LIMIT_AI)
async def ai_chat(body: AIChatIn, request: Request, user=Depends(get_current_user), lang: str = Depends(get_lang)):
    session_id = body.session_id or new_id()
    projects = await db.projects.find({"members": user["id"]}, {"_id": 0}).to_list(50)
    tasks = await db.tasks.find({"owner_id": user["id"]}, {"_id": 0}).to_list(100)
    ctx = build_user_context(user, projects, tasks)

    focus_ctx = ""
    if body.context_type == "project" and body.context_id:
        p = await db.projects.find_one({"id": body.context_id}, {"_id": 0})
        if p:
            focus_ctx = f"\n\nFOCUSED PROJECT: {json.dumps({k: p.get(k) for k in ['name','description','status','priority','progress']})}"

    if lang == "en":
        system = f"""You are OpsCore — an AI Chief of Operations for a multi-project founder. You are direct, sharp, calm, and surgically useful. You operate as COO + technical PM + executive assistant + productivity coach.

You understand the full context of the user's workspace below. Reference projects/tasks by name when relevant. Avoid generic advice. Be concise, actionable, and specific.

Always reply in clear modern English.

Workspace context:
{ctx}{focus_ctx}

Style:
- No filler. No emoji.
- Short paragraphs or tight bullet lists.
- Suggest specific actions where appropriate.
- If the user shares raw notes, rewrite them professionally."""
    else:
        system = f"""أنت أوبس‌كور — رئيس عمليات ذكي للمؤسس متعدد المشاريع. أنت مباشر، ذكي، هادئ، ومفيد جراحيًا. تتصرّف كرئيس عمليات + مدير مشاريع تقني + مساعد تنفيذي + مدرّب إنتاجية.

تفهم السياق الكامل لمساحة عمل المستخدم أدناه. أَشِر إلى المشاريع/المهام بأسمائها عند الحاجة. تجنّب النصائح العامة. كن مختصرًا، قابلًا للتنفيذ، ومحددًا.

ردّ دائمًا باللغة العربية الفصحى الواضحة.

سياق المساحة:
{ctx}{focus_ctx}

الأسلوب:
- بدون حشو. بدون رموز إيموجي.
- فقرات قصيرة أو قوائم محكمة.
- اقترح إجراءات محددة عند الاقتضاء.
- إذا شارك المستخدم ملاحظات خامة، أعد صياغتها باحترافية."""

    convo = await db.ai_conversations.find_one({"session_id": session_id, "user_id": user["id"]}, {"_id": 0})
    messages = convo["messages"] if convo else []

    history_str = ""
    for m in messages[-10:]:
        history_str += f"\n{m['role'].upper()}: {m['content']}"
    full_user_msg = (history_str + f"\nUSER: {body.message}").strip() if history_str else body.message

    reply = await claude_chat(session_id, system, full_user_msg, user_id=user["id"], lang=lang)

    messages.append({"role": "user", "content": body.message, "at": now_iso()})
    messages.append({"role": "assistant", "content": reply, "at": now_iso()})

    if convo:
        await db.ai_conversations.update_one(
            {"session_id": session_id, "user_id": user["id"]},
            {"$set": {"messages": messages, "updated_at": now_iso()}},
        )
    else:
        await db.ai_conversations.insert_one({
            "session_id": session_id,
            "user_id": user["id"],
            "messages": messages,
            "created_at": now_iso(),
            "updated_at": now_iso(),
        })

    return {"session_id": session_id, "reply": reply, "messages": messages}


@router.get("/ai/conversations")
async def list_ai_convos(user=Depends(get_current_user)):
    rows = await db.ai_conversations.find({"user_id": user["id"]}, {"_id": 0}).sort("updated_at", -1).to_list(50)
    for r in rows:
        r["preview"] = (r["messages"][0]["content"][:80] if r.get("messages") else "")
        r["message_count"] = len(r.get("messages", []))
    return rows


@router.get("/ai/conversations/{session_id}")
async def get_ai_convo(session_id: str, user=Depends(get_current_user)):
    convo = await db.ai_conversations.find_one({"session_id": session_id, "user_id": user["id"]}, {"_id": 0})
    if not convo:
        return {"session_id": session_id, "messages": []}
    return convo


@router.post("/ai/rewrite")
@limiter.limit(LIMIT_AI)
async def ai_rewrite(body: AIRewriteIn, request: Request, user=Depends(get_current_user), lang: str = Depends(get_lang)):
    if lang == "en":
        system = f"You are a professional writing assistant. Rewrite the user's raw notes into clear, {body.tone}, well-structured English prose. Preserve all factual content. Output only the rewritten text, nothing else."
    else:
        system = f"أنت مساعد كتابة محترف. أعد صياغة ملاحظات المستخدم الخام إلى نثر عربي واضح، {body.tone}، منظّم. احتفظ بكل المحتوى الواقعي. أخرج النص المُعاد صياغته فقط، لا شيء غيره."
    out = await claude_chat(new_id(), system, body.text, user_id=user["id"], lang=lang)
    return {"rewritten": out}


@router.post("/ai/breakdown")
@limiter.limit(LIMIT_AI)
async def ai_breakdown(body: AIBreakdownIn, request: Request, user=Depends(get_current_user), lang: str = Depends(get_lang)):
    task = await db.tasks.find_one({"id": body.task_id, "owner_id": user["id"]}, {"_id": 0})
    if not task:
        raise HTTPException(404, "Task not found")
    system = """You are an execution planner. Given a task, break it into 4-8 small, concrete, actionable subtasks. Each subtask should be a single execution unit (15-60 minutes). Output STRICT JSON only, in this format:
{"subtasks": [{"title": "...", "estimated_minutes": 30, "rationale": "..."}, ...]}"""
    user_text = f"TASK: {task['title']}\nDESCRIPTION: {task.get('description','')}\nPRIORITY: {task.get('priority')}\nCOMPLEXITY: {task.get('complexity')}\n\nReturn JSON only."
    out = await claude_chat(new_id(), system, user_text, user_id=user["id"], lang=lang)
    try:
        start = out.find("{"); end = out.rfind("}")
        if start >= 0 and end > start:
            data = json.loads(out[start:end+1])
        else:
            data = {"subtasks": []}
    except Exception:
        data = {"subtasks": [], "raw": out}
    subtasks = data.get("subtasks", [])
    if subtasks:
        formatted = [{"id": new_id(), "title": s.get("title"), "estimated_minutes": s.get("estimated_minutes", 30), "done": False, "rationale": s.get("rationale", "")} for s in subtasks]
        await db.tasks.update_one({"id": body.task_id}, {"$set": {"subtasks": formatted, "updated_at": now_iso()}})
        task["subtasks"] = formatted
    return {"task": task, "subtasks": data.get("subtasks", []), "raw": out}


@router.post("/ai/summarize-project")
@limiter.limit(LIMIT_AI)
async def ai_summarize_project(body: AISummaryIn, request: Request, user=Depends(get_current_user), lang: str = Depends(get_lang)):
    p = await db.projects.find_one({"id": body.project_id, "members": user["id"]}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Project not found")
    tasks = await db.tasks.find({"project_id": body.project_id}, {"_id": 0}).to_list(500)
    notes = await db.notes.find({"project_id": body.project_id}, {"_id": 0}).sort("created_at", -1).to_list(50)
    text = f"PROJECT: {p.get('name')}\nDESCRIPTION: {p.get('description','')}\nSTATUS: {p.get('status')}\nPRIORITY: {p.get('priority')}\n\nTASKS ({len(tasks)}):\n"
    for t in tasks[:30]:
        text += f"- [{t.get('status')}] {t.get('title')}\n"
    text += "\nRECENT NOTES:\n"
    for n in notes[:10]:
        text += f"- {n.get('title')}: {n.get('content','')[:200]}\n"
    if lang == "en":
        system = """You are an AI Chief of Operations. Produce a concise executive summary for the project below. Write in English. Include:
1. Current status (1-2 lines)
2. Top 3 priorities / next actions
3. Risks and blockers
4. Suggested timeline adjustments if any
Be direct. No filler."""
    else:
        system = """أنت رئيس عمليات ذكي. أنتج ملخصًا تنفيذيًا موجزًا للمشروع أدناه. اكتب بالعربية. تضمّن:
١. الحالة الراهنة (سطر إلى سطرين)
٢. أعلى ٣ أولويات / إجراءات تالية
٣. المخاطر والعوائق
٤. تعديلات الجدول الزمني المقترحة إن وُجدت
كن مباشرًا. لا حشو."""
    out = await claude_chat(new_id(), system, text, user_id=user["id"], lang=lang)
    return {"summary": out}


@router.get("/ai/prioritize")
@limiter.limit(LIMIT_AI)
async def ai_prioritize(request: Request, user=Depends(get_current_user), lang: str = Depends(get_lang)):
    tasks = await db.tasks.find({"owner_id": user["id"], "status": {"$ne": "done"}}, {"_id": 0}).to_list(200)
    if not tasks:
        return {"recommendations": [], "ranked": []}
    text = "OPEN TASKS:\n"
    for t in tasks[:30]:
        text += f"- ID={t['id']} | {t['title']} | priority={t.get('priority')} | status={t.get('status')} | due={t.get('due_date','none')} | complexity={t.get('complexity')}\n"
    if lang == "en":
        system = """You are the smart priority engine. Rank tasks by what the user should do NOW based on: deadlines, dependencies, business impact, complexity vs energy, and momentum. Write reasons in clear English. Output VALID JSON only:
{"ranked": [{"id": "...", "title": "...", "score": 0-100, "reason": "single line"}], "insights": ["..."]}"""
    else:
        system = """أنت محرّك الأولوية الذكي. رتّب المهام بناءً على ما يجب على المستخدم فعله الآن وفق: المواعيد، التبعيات، الأثر التجاري، التعقيد مقابل الطاقة، والزخم. اكتب الأسباب بالعربية. أخرج JSON صالحًا فقط:
{"ranked": [{"id": "...", "title": "...", "score": 0-100, "reason": "سطر واحد"}], "insights": ["..."]}"""
    out = await claude_chat(new_id(), system, text, user_id=user["id"], lang=lang)
    try:
        start = out.find("{"); end = out.rfind("}")
        data = json.loads(out[start:end+1]) if start >= 0 else {"ranked": [], "insights": []}
    except Exception:
        data = {"ranked": [], "insights": [], "raw": out}
    return data


@router.get("/ai/daily-brief")
@limiter.limit(LIMIT_AI)
async def ai_daily_brief(request: Request, user=Depends(get_current_user), lang: str = Depends(get_lang)):
    uid = user["id"]
    now = datetime.now(timezone.utc)
    tasks = await db.tasks.find({"owner_id": uid}, {"_id": 0}).to_list(500)
    projects = await db.projects.find({"members": uid}, {"_id": 0}).to_list(100)
    proj_by_id = {p["id"]: p for p in projects}

    open_tasks = [t for t in tasks if t.get("status") != "done"]
    in_progress = [t for t in open_tasks if t.get("status") == "in_progress"]
    blocked = [t for t in open_tasks if t.get("status") == "blocked"]

    for t in open_tasks:
        t["_score"] = compute_priority_score(t, now)
        t["_project_name"] = proj_by_id.get(t.get("project_id"), {}).get("name")

    open_tasks.sort(key=lambda x: -x["_score"])

    current_focus = next((t for t in in_progress if t.get("status") == "in_progress"), open_tasks[0] if open_tasks else None)
    next_action = next((t for t in open_tasks if t.get("status") == "todo"), None)
    high_leverage = [t for t in open_tasks if t.get("priority") in ("high", "critical") and t.get("complexity") in ("low", "medium")][:3]

    recommended = None
    for t in open_tasks:
        if t.get("complexity") in ("medium", "high") and t.get("status") != "blocked":
            recommended = t
            break

    workload = len(in_progress) + len([t for t in open_tasks if t.get("priority") in ("high", "critical")])
    burnout = "low" if workload < 6 else "medium" if workload < 12 else "high"

    summary = ""
    if open_tasks:
        compact = [{"id": t["id"], "title": t["title"], "priority": t.get("priority"), "status": t.get("status"), "due": t.get("due_date"), "project": t.get("_project_name")} for t in open_tasks[:15]]
        if lang == "en":
            system = """You are the AI Chief of Operations. In 3-4 short sentences in English, give the founder their direction for today. State the most important thing, the biggest risk, and one decisive action. Direct, no filler, no emoji, no bullet points."""
        else:
            system = """أنت رئيس العمليات الذكي. في ٣-٤ جمل قصيرة بالعربية، أعطِ المؤسس توجيهه لهذا اليوم. اذكر أهم شيء، أكبر خطر، وإجراءً حاسمًا واحدًا. مباشر، بدون حشو، بدون رموز إيموجي، بدون قوائم نقطية."""
        prompt = f"OPEN TASKS:\n{json.dumps(compact, default=str)}\n\nWorkload: {workload}. Burnout: {burnout}."
        summary = await claude_chat(new_id(), system, prompt, user_id=uid, lang=lang)

    def lite(t):
        if not t:
            return None
        return {"id": t["id"], "title": t["title"], "priority": t.get("priority"), "status": t.get("status"),
                "due_date": t.get("due_date"), "estimated_minutes": t.get("estimated_minutes"),
                "complexity": t.get("complexity"), "project_id": t.get("project_id"),
                "project_name": t.get("_project_name"), "score": t.get("_score")}

    return {
        "summary": summary,
        "current_focus": lite(current_focus),
        "next_action": lite(next_action),
        "high_leverage": [lite(t) for t in high_leverage],
        "blocked": [lite(t) for t in blocked][:5],
        "recommended_deep_work": lite(recommended),
        "workload": workload,
        "burnout": burnout,
        "generated_at": now_iso(),
    }


@router.get("/ai/weekly-review")
@limiter.limit(LIMIT_AI)
async def ai_weekly_review(request: Request, user=Depends(get_current_user), lang: str = Depends(get_lang)):
    uid = user["id"]
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    tasks = await db.tasks.find({"owner_id": uid}, {"_id": 0}).to_list(1000)
    sessions = await db.focus_sessions.find({"user_id": uid}, {"_id": 0}).to_list(1000)

    completed = []
    delayed = []
    for t in tasks:
        if t.get("completed_at"):
            try:
                d = datetime.fromisoformat(t["completed_at"].replace("Z", "+00:00"))
                if d >= week_ago:
                    completed.append(t)
            except Exception:
                pass
        elif t.get("status") != "done" and t.get("due_date"):
            try:
                d = datetime.fromisoformat(t["due_date"].replace("Z", "+00:00"))
                if d < now:
                    delayed.append(t)
            except Exception:
                pass

    week_focus = 0
    for s in sessions:
        try:
            d = datetime.fromisoformat(s["created_at"].replace("Z", "+00:00"))
            if d >= week_ago and s.get("completed"):
                week_focus += s.get("duration_minutes", 0)
        except Exception:
            pass

    stats = {
        "completed_count": len(completed),
        "delayed_count": len(delayed),
        "focus_minutes": week_focus,
        "focus_sessions": len([s for s in sessions if s.get("completed") and datetime.fromisoformat(s["created_at"].replace("Z", "+00:00")) >= week_ago]),
        "blocked_count": len([t for t in tasks if t.get("status") == "blocked"]),
    }

    compact_completed = [{"title": t["title"], "priority": t.get("priority"), "actual_minutes": t.get("actual_minutes", 0)} for t in completed[:30]]
    compact_delayed = [{"title": t["title"], "priority": t.get("priority"), "due": t.get("due_date")} for t in delayed[:20]]

    if lang == "en":
        system = """You are the AI Chief of Operations producing a weekly executive review for a multi-project founder. Write in English. Output VALID JSON only with these keys:
{
 "narrative": "2-3 short paragraphs about the week",
 "wins": ["..."],
 "misses": ["..."],
 "patterns": ["observed productivity patterns"],
 "bottlenecks": ["..."],
 "next_week_priorities": ["3-5 specific prioritized items"],
 "insights": ["1-3 sharp operational insights"]
}
Be direct and specific. No filler. No emoji."""
    else:
        system = """أنت رئيس العمليات الذكي تنتج مراجعة تنفيذية أسبوعية لمؤسس متعدد المشاريع. اكتب باللغة العربية. أخرج JSON صالحًا فقط بهذه المفاتيح:
{
 "narrative": "٢-٣ فقرات قصيرة عن الأسبوع",
 "wins": ["..."],
 "misses": ["..."],
 "patterns": ["أنماط الإنتاجية الملاحَظة"],
 "bottlenecks": ["..."],
 "next_week_priorities": ["٣-٥ أولويات محددة مرتبة"],
 "insights": ["١-٣ رؤى تشغيلية حادّة"]
}
كن مباشرًا ومحددًا. لا حشو. لا رموز إيموجي."""
    prompt = f"STATS: {json.dumps(stats)}\nCOMPLETED: {json.dumps(compact_completed)}\nDELAYED: {json.dumps(compact_delayed)}"
    raw = await claude_chat(new_id(), system, prompt, user_id=uid, lang=lang)
    try:
        start = raw.find("{"); end = raw.rfind("}")
        data = json.loads(raw[start:end+1]) if start >= 0 else {}
    except Exception:
        data = {"narrative": raw, "wins": [], "misses": [], "patterns": [], "bottlenecks": [], "next_week_priorities": [], "insights": []}

    await db.ai_memory.insert_one({
        "id": new_id(),
        "user_id": uid,
        "type": "weekly_review",
        "content": data,
        "stats": stats,
        "created_at": now_iso(),
    })

    return {**data, "stats": stats, "generated_at": now_iso()}


# ---- AI memory ----
@router.get("/ai/memory")
async def list_memory(user=Depends(get_current_user)):
    rows = await db.ai_memory.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return rows


@router.post("/ai/memory")
async def add_memory(body: MemoryIn, user=Depends(get_current_user)):
    doc = {"id": new_id(), "user_id": user["id"], "type": body.type, "content": body.content, "tags": body.tags, "created_at": now_iso()}
    await db.ai_memory.insert_one(doc)
    return clean(doc)


@router.delete("/ai/memory/{mid}")
async def del_memory(mid: str, user=Depends(get_current_user)):
    await db.ai_memory.delete_one({"id": mid, "user_id": user["id"]})
    return {"ok": True}


@router.post("/ai/memory/extract")
@limiter.limit(LIMIT_AI)
async def ai_extract_memory(request: Request, user=Depends(get_current_user), lang: str = Depends(get_lang)):
    uid = user["id"]
    tasks = await db.tasks.find({"owner_id": uid}, {"_id": 0}).to_list(500)
    notes = await db.notes.find({"owner_id": uid}, {"_id": 0}).sort("created_at", -1).to_list(50)
    blocked = [t for t in tasks if t.get("status") == "blocked"]
    delayed = []
    now = datetime.now(timezone.utc)
    for t in tasks:
        if t.get("status") != "done" and t.get("due_date"):
            try:
                d = datetime.fromisoformat(t["due_date"].replace("Z", "+00:00"))
                if d < now:
                    delayed.append(t)
            except Exception:
                pass
    payload = {
        "blocked": [{"title": t["title"], "priority": t.get("priority")} for t in blocked[:20]],
        "delayed": [{"title": t["title"], "priority": t.get("priority")} for t in delayed[:20]],
        "recent_notes": [{"title": n.get("title"), "content": n.get("content","")[:300]} for n in notes[:15]],
    }
    if lang == "en":
        system = """Analyze the founder's operational state. Identify 3-6 recurring patterns or operational concerns worth remembering. Write in English. Output VALID JSON only:
{"patterns":[{"type":"blocker|pattern|bottleneck","content":"specific observation"}]}
Examples of useful patterns: recurring blockers, neglected projects, repetitive task types, productivity tendencies. Be specific. No filler."""
    else:
        system = """حلّل الحالة التشغيلية للمؤسس. حدّد ٣-٦ أنماط متكررة أو مخاوف تشغيلية يجب تذكّرها. اكتب بالعربية. أخرج JSON صالحًا فقط:
{"patterns":[{"type":"blocker|pattern|bottleneck","content":"ملاحظة محددة"}]}
أمثلة على أنماط مفيدة: عوائق متكررة، مشاريع مهمَلة، أنواع مهام متكررة، ميول إنتاجية. كن محددًا. لا حشو."""
    raw = await claude_chat(new_id(), system, json.dumps(payload), user_id=uid, lang=lang)
    try:
        s = raw.find("{"); e = raw.rfind("}")
        data = json.loads(raw[s:e+1]) if s >= 0 else {"patterns": []}
    except Exception:
        data = {"patterns": []}
    saved = []
    for p in data.get("patterns", []):
        doc = {"id": new_id(), "user_id": uid, "type": p.get("type", "pattern"), "content": p.get("content"), "tags": ["auto"], "created_at": now_iso(), "source": "ai_extract"}
        await db.ai_memory.insert_one(doc)
        saved.append({k: v for k, v in doc.items() if k != "_id"})
    return {"extracted": saved}


# ---- Schedule suggest ----
@router.post("/ai/schedule-suggest")
@limiter.limit(LIMIT_AI)
async def ai_schedule_suggest(body: ScheduleSuggestIn, request: Request, user=Depends(get_current_user), lang: str = Depends(get_lang)):
    uid = user["id"]
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    projects = await db.projects.find({"members": uid}, {"_id": 0}).to_list(100)
    tasks = await db.tasks.find({"owner_id": uid, "status": {"$ne": "done"}}, {"_id": 0}).to_list(500)
    sessions = await db.focus_sessions.find({"user_id": uid}, {"_id": 0}).to_list(500)

    workload = len(tasks)
    week_focus = sum(s.get("duration_minutes", 0) for s in sessions if s.get("completed") and datetime.fromisoformat(s["created_at"].replace("Z", "+00:00")) >= week_ago)
    busy_windows = []
    for p in projects:
        if p.get("start_date") and p.get("end_date"):
            busy_windows.append({"name": p["name"], "start": p["start_date"], "end": p["end_date"]})

    target_project = None
    if body.project_id:
        target_project = next((p for p in projects if p["id"] == body.project_id), None)

    payload = {
        "target": target_project or {"title": body.title, "description": body.description, "priority": body.priority, "estimated_days": body.estimated_days},
        "workload_tasks": workload,
        "weekly_focus_minutes": week_focus,
        "active_projects": len([p for p in projects if p.get("status") == "active"]),
        "busy_windows": busy_windows[:20],
        "today": now.date().isoformat(),
    }
    if lang == "en":
        system = """You are a smart scheduling assistant for a multi-project founder. Based on the workspace context, suggest realistic start_date and end_date (ISO 8601) for the target. Consider workload, busy windows, weekly focus capacity, and avoid conflicts. Write the rationale in English. Output VALID JSON only:
{
 "start_date": "YYYY-MM-DDTHH:MM:SS+00:00",
 "end_date": "YYYY-MM-DDTHH:MM:SS+00:00",
 "rationale": "two sentences max",
 "focus_blocks_per_week": 0,
 "sprint_weeks": 0,
 "warnings": ["..."]
}
No text outside JSON."""
    else:
        system = """أنت مساعد جدولة ذكي لمؤسس متعدد المشاريع. بناءً على سياق المساحة، اقترح start_date و end_date واقعيين (ISO 8601) للهدف. ضع في الاعتبار حجم العمل، النوافذ المشغولة، طاقة التركيز الأسبوعية، وتجنّب التضارب. اكتب المبررات بالعربية. أخرج JSON صالحًا فقط:
{
 "start_date": "YYYY-MM-DDTHH:MM:SS+00:00",
 "end_date": "YYYY-MM-DDTHH:MM:SS+00:00",
 "rationale": "جملتان كحد أقصى",
 "focus_blocks_per_week": 0,
 "sprint_weeks": 0,
 "warnings": ["..."]
}
لا نصوص خارج JSON."""
    raw = await claude_chat(new_id(), system, json.dumps(payload, default=str), user_id=uid, lang=lang)
    try:
        s = raw.find("{"); e = raw.rfind("}")
        data = json.loads(raw[s:e+1]) if s >= 0 else {}
    except Exception:
        data = {"raw": raw}
    return data


# ---- AI settings ----
@router.get("/settings/ai")
async def get_ai_settings(user=Depends(get_current_user)):
    s = await db.user_settings.find_one({"user_id": user["id"]}, {"_id": 0}) or {}
    has_key = bool(s.get("api_key_encrypted"))
    return {
        "has_custom_key": has_key,
        "model": s.get("model", DEFAULT_CLAUDE_MODEL),
        "use_own_key": s.get("use_own_key", False),
        "usage": s.get("usage", {"tokens_in": 0, "tokens_out": 0, "calls": 0, "last_call_at": None}),
        "supported_models": SUPPORTED_MODELS,
        "active_source": "user" if has_key and s.get("use_own_key", False) else "emergent",
    }


@router.put("/settings/ai")
async def update_ai_settings(body: AISettingsIn, user=Depends(get_current_user)):
    upd: Dict[str, Any] = {"updated_at": now_iso()}
    if body.model is not None:
        if body.model not in SUPPORTED_MODELS:
            raise HTTPException(400, f"Unsupported model. Use one of: {SUPPORTED_MODELS}")
        upd["model"] = body.model
    if body.use_own_key is not None:
        upd["use_own_key"] = body.use_own_key
    if body.api_key is not None:
        if body.api_key == "":
            upd["api_key_encrypted"] = None
        else:
            upd["api_key_encrypted"] = FERNET.encrypt(body.api_key.encode()).decode()
    await db.user_settings.update_one(
        {"user_id": user["id"]},
        {"$set": upd, "$setOnInsert": {"user_id": user["id"], "created_at": now_iso()}},
        upsert=True,
    )
    return await get_ai_settings(user)


@router.post("/settings/ai/test")
async def test_ai_connection(user=Depends(get_current_user)):
    import time
    started = time.time()
    reply = await claude_chat(new_id(), "You are a connection tester. Respond with exactly: PONG", "ping", user_id=user["id"])
    elapsed_ms = int((time.time() - started) * 1000)
    cfg = await get_user_ai_config(user["id"])
    ok = "PONG" in reply.upper() or "pong" in reply.lower() or not reply.startswith("AI error")
    return {"ok": ok, "latency_ms": elapsed_ms, "model": cfg["model"], "source": cfg["source"], "reply": reply[:200]}
