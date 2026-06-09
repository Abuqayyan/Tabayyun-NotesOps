"""Tasks: CRUD, today-hints, progress updates, dependency intelligence, timeline, timeblocks.

Route ordering note: the static path /tasks/today-hints is registered BEFORE the
parameterized /tasks/{tid} so it is not shadowed (it previously was, returning 404).
"""
import re
from datetime import datetime, timezone, timedelta, date as _date
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel

from app.core.db_mongo import db
from app.core.security import get_current_user
from app.core.deps import get_lang
from app.core.utils import now_iso, new_id, clean, resolve_lang
from app.shared.websocket import broadcast
from app.shared.activity import emit_activity
from app.shared.email import send_templated_email, resolve_app_url
from app.shared.permissions import can_edit, can_view, user_visible_project_ids

router = APIRouter()


# ---- Models ----
class TaskIn(BaseModel):
    title: str
    description: Optional[str] = ""
    project_id: Optional[str] = None
    status: Optional[str] = "todo"
    priority: Optional[str] = "medium"
    complexity: Optional[str] = "medium"
    estimated_minutes: Optional[int] = 30
    actual_minutes: Optional[int] = 0
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    due_date: Optional[str] = None
    scheduled_for: Optional[str] = None
    tags: Optional[List[str]] = []
    dependencies: Optional[List[str]] = []
    subtasks: Optional[List[Dict[str, Any]]] = []
    assignee_id: Optional[str] = None
    parent_task_id: Optional[str] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    project_id: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    complexity: Optional[str] = None
    estimated_minutes: Optional[int] = None
    actual_minutes: Optional[int] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    due_date: Optional[str] = None
    scheduled_for: Optional[str] = None
    tags: Optional[List[str]] = None
    dependencies: Optional[List[str]] = None
    subtasks: Optional[List[Dict[str, Any]]] = None
    assignee_id: Optional[str] = None


class TaskUpdateLogIn(BaseModel):
    content: str


class TimeBlockIn(BaseModel):
    title: str
    type: str = "deep_work"
    start_date: str
    end_date: str
    project_id: Optional[str] = None
    notes: Optional[str] = ""


class TimeBlockUpdate(BaseModel):
    title: Optional[str] = None
    type: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    project_id: Optional[str] = None
    notes: Optional[str] = None


# ---- Create / list ----
@router.post("/tasks")
async def create_task(body: TaskIn, request: Request, user=Depends(get_current_user)):
    tid = new_id()
    doc = body.model_dump()
    if doc.get("project_id"):
        p = await db.projects.find_one({"id": doc["project_id"]}, {"_id": 0})
        if not p or not can_edit(p, user["id"]):
            raise HTTPException(403, "No edit access to this project")
    doc.update({
        "id": tid,
        "owner_id": user["id"],
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "completed_at": None,
    })
    await db.tasks.insert_one(doc)
    await broadcast(user["id"], "task.created", {"id": tid})
    await emit_activity(user["id"], "task.created", "task", tid, project_id=doc.get("project_id"),
                        actor_name=user.get("name"), metadata={"title": doc.get("title")})

    if doc.get("assignee_id") and doc["assignee_id"] != user["id"]:
        target = await db.users.find_one({"id": doc["assignee_id"]})
        if target:
            lang = resolve_lang(request.headers.get("X-Lang"))
            app_url = await resolve_app_url(request)
            await send_templated_email(
                "task_assigned",
                target["email"],
                {
                    "actor": user.get("name", ""),
                    "title": doc.get("title", ""),
                    "description": doc.get("description", "") or "",
                    "due_date": doc.get("due_date") or "",
                    "url": f"{app_url}/tasks?focus={tid}",
                },
                lang=lang,
            )
    return clean(doc)


@router.get("/tasks")
async def list_tasks(
    project_id: Optional[str] = None,
    status_filter: Optional[str] = None,
    scheduled_for: Optional[str] = None,
    view: Optional[str] = None,
    today: Optional[str] = None,
    day_of_week: Optional[int] = None,
    q: Optional[str] = None,
    scope: Optional[str] = "mine",
    user=Depends(get_current_user),
):
    uid = user["id"]
    visible_pids = await user_visible_project_ids(uid)

    if scope == "all":
        base_q: Dict[str, Any] = {"$or": [
            {"owner_id": uid},
            {"assignee_id": uid},
            {"project_id": {"$in": visible_pids}},
        ]}
    else:
        base_q = {"$or": [{"owner_id": uid}, {"assignee_id": uid}]}

    extra: Dict[str, Any] = {}
    if project_id:
        if project_id not in visible_pids:
            raise HTTPException(403, "No access to this project")
        extra["project_id"] = project_id
    if status_filter:
        extra["status"] = status_filter
    if scheduled_for == "none":
        extra["scheduled_for"] = {"$in": [None]}
    elif scheduled_for:
        extra["scheduled_for"] = scheduled_for
    if q:
        rx = re.compile(re.escape(q), re.IGNORECASE)
        extra["$and"] = [{"$or": [{"title": rx}, {"description": rx}]}]

    if day_of_week is not None and 0 <= day_of_week <= 6:
        proj_rows = await db.projects.find(
            {"id": {"$in": visible_pids}, "weekly_days": day_of_week},
            {"_id": 0, "id": 1},
        ).to_list(500)
        proj_ids = [p["id"] for p in proj_rows]
        if not proj_ids:
            return []
        if "project_id" in extra and isinstance(extra["project_id"], str) and extra["project_id"] not in proj_ids:
            return []
        if "project_id" not in extra:
            extra["project_id"] = {"$in": proj_ids}

    query = {"$and": [base_q, extra]} if extra else base_q
    rows = await db.tasks.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)

    if view in ("today", "week"):
        try:
            today_d = _date.fromisoformat(today) if today else _date.today()
        except Exception:
            today_d = _date.today()
        week_end = today_d + timedelta(days=7)

        def parse_d(s):
            if not s:
                return None
            try:
                return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
            except Exception:
                try:
                    return _date.fromisoformat(s[:10])
                except Exception:
                    return None

        def in_window(t):
            sched = parse_d(t.get("scheduled_for"))
            due = parse_d(t.get("due_date") or t.get("end_date"))
            in_progress = t.get("status") == "in_progress"
            if view == "today":
                return bool(sched and sched == today_d)
            else:
                if sched and today_d <= sched <= week_end:
                    return True
                if due and today_d <= due <= week_end and t.get("status") != "done":
                    return True
                if due and due < today_d and t.get("status") != "done":
                    return True
                if in_progress and not sched and not due:
                    return True
                return False

        rows = [t for t in rows if in_window(t)]
    return rows


# ---- today-hints MUST precede /tasks/{tid} ----
@router.get("/tasks/today-hints")
async def tasks_today_hints(today: Optional[str] = None, user=Depends(get_current_user)):
    try:
        today_d = _date.fromisoformat(today) if today else _date.today()
    except Exception:
        today_d = _date.today()

    def parse_d(s):
        if not s:
            return None
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
        except Exception:
            try:
                return _date.fromisoformat(s[:10])
            except Exception:
                return None

    rows = await db.tasks.find({"owner_id": user["id"], "status": {"$ne": "done"}}, {"_id": 0}).to_list(2000)
    overdue_unpinned = 0
    in_progress_unpinned = 0
    for t in rows:
        sched = parse_d(t.get("scheduled_for"))
        if sched and sched == today_d:
            continue
        due = parse_d(t.get("due_date") or t.get("end_date"))
        if due and due < today_d:
            overdue_unpinned += 1
        elif t.get("status") == "in_progress":
            in_progress_unpinned += 1
    return {"overdue_unpinned": overdue_unpinned, "in_progress_unpinned": in_progress_unpinned}


@router.get("/tasks/{tid}")
async def get_task(tid: str, user=Depends(get_current_user)):
    t = await db.tasks.find_one({"id": tid}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Not found")
    uid = user["id"]
    if t.get("owner_id") == uid or t.get("assignee_id") == uid:
        return t
    if t.get("project_id"):
        p = await db.projects.find_one({"id": t["project_id"]}, {"_id": 0})
        if p and can_view(p, uid):
            return t
    raise HTTPException(403, "No access to this task")


@router.patch("/tasks/{tid}")
async def update_task(tid: str, body: TaskUpdate, request: Request, user=Depends(get_current_user)):
    uid = user["id"]
    existing = await db.tasks.find_one({"id": tid}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Not found")

    allowed = (existing.get("owner_id") == uid) or (existing.get("assignee_id") == uid)
    if not allowed and existing.get("project_id"):
        p = await db.projects.find_one({"id": existing["project_id"]}, {"_id": 0})
        allowed = p and can_edit(p, uid)
    if not allowed:
        raise HTTPException(403, "No edit access")

    upd = body.model_dump(exclude_unset=True)
    upd["updated_at"] = now_iso()
    if upd.get("status") == "done":
        upd["completed_at"] = now_iso()
    await db.tasks.update_one({"id": tid}, {"$set": upd})
    t = await db.tasks.find_one({"id": tid}, {"_id": 0})

    new_assignee = upd.get("assignee_id")
    if new_assignee and new_assignee != existing.get("assignee_id") and new_assignee != uid:
        target = await db.users.find_one({"id": new_assignee})
        if target:
            lang = resolve_lang(request.headers.get("X-Lang"))
            app_url = await resolve_app_url(request)
            await send_templated_email(
                "task_assigned",
                target["email"],
                {
                    "actor": user.get("name", ""),
                    "title": t.get("title", ""),
                    "description": t.get("description", "") or "",
                    "due_date": t.get("due_date") or "",
                    "url": f"{app_url}/tasks?focus={t['id']}",
                },
                lang=lang,
            )
    if upd.get("status") == "done" and existing.get("status") != "done":
        await emit_activity(uid, "task.completed", "task", tid, project_id=t.get("project_id"),
                            actor_name=user.get("name"), metadata={"title": t.get("title")})
    await broadcast(uid, "task.updated", {"id": tid, "status": t.get("status")})
    return t


@router.delete("/tasks/{tid}")
async def delete_task(tid: str, user=Depends(get_current_user)):
    uid = user["id"]
    existing = await db.tasks.find_one({"id": tid}, {"_id": 0})
    if not existing:
        return {"ok": True}
    allowed = existing.get("owner_id") == uid
    if not allowed and existing.get("project_id"):
        p = await db.projects.find_one({"id": existing["project_id"]}, {"_id": 0})
        allowed = p and can_edit(p, uid)
    if not allowed:
        raise HTTPException(403, "No delete access")
    await db.tasks.delete_one({"id": tid})
    await db.reminders.delete_many({"entity_type": "task", "entity_id": tid})
    await broadcast(uid, "task.deleted", {"id": tid})
    return {"ok": True}


# ---- Task progress updates ----
@router.post("/tasks/{tid}/updates")
async def add_task_update(tid: str, body: TaskUpdateLogIn, user=Depends(get_current_user)):
    task = await db.tasks.find_one({"id": tid, "owner_id": user["id"]}, {"_id": 0, "id": 1})
    if not task:
        raise HTTPException(404, "Task not found")
    if not body.content.strip():
        raise HTTPException(400, "Content required")
    doc = {
        "id": new_id(),
        "task_id": tid,
        "owner_id": user["id"],
        "content": body.content.strip(),
        "created_at": now_iso(),
    }
    await db.task_updates.insert_one(doc)
    await db.tasks.update_one({"id": tid}, {"$set": {"updated_at": now_iso()}})
    await broadcast(user["id"], "task.updated", {"id": tid})
    doc.pop("_id", None)
    return doc


@router.get("/tasks/{tid}/updates")
async def list_task_updates(tid: str, user=Depends(get_current_user)):
    task = await db.tasks.find_one({"id": tid, "owner_id": user["id"]}, {"_id": 0, "id": 1})
    if not task:
        raise HTTPException(404, "Task not found")
    rows = await db.task_updates.find({"task_id": tid, "owner_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return rows


@router.delete("/tasks/{tid}/updates/{uid}")
async def delete_task_update(tid: str, uid: str, user=Depends(get_current_user)):
    res = await db.task_updates.delete_one({"id": uid, "task_id": tid, "owner_id": user["id"]})
    if not res.deleted_count:
        raise HTTPException(404, "Update not found")
    return {"ok": True}


# ---- Dependency intelligence ----
@router.get("/dependencies/graph")
async def dep_graph(user=Depends(get_current_user)):
    tasks = await db.tasks.find({"owner_id": user["id"]}, {"_id": 0}).to_list(1000)
    by_id = {t["id"]: t for t in tasks}
    edges = []
    for t in tasks:
        for dep_id in (t.get("dependencies") or []):
            if dep_id in by_id:
                edges.append({"from": dep_id, "to": t["id"]})
    return {"tasks": [{"id": t["id"], "title": t["title"], "status": t.get("status"), "priority": t.get("priority"), "project_id": t.get("project_id")} for t in tasks], "edges": edges}


@router.get("/dependencies/bottlenecks")
async def dep_bottlenecks(user=Depends(get_current_user)):
    tasks = await db.tasks.find({"owner_id": user["id"]}, {"_id": 0}).to_list(1000)
    by_id = {t["id"]: t for t in tasks}
    blocks: Dict[str, List[str]] = {}
    for t in tasks:
        for dep_id in (t.get("dependencies") or []):
            blocks.setdefault(dep_id, []).append(t["id"])
    now = datetime.now(timezone.utc)
    items = []
    for tid, blocked_ids in blocks.items():
        t = by_id.get(tid)
        if not t:
            continue
        is_delayed = False
        if t.get("due_date") and t.get("status") != "done":
            try:
                d = datetime.fromisoformat(t["due_date"].replace("Z", "+00:00"))
                is_delayed = d < now
            except Exception:
                pass
        if t.get("status") in ("blocked", "todo", "in_progress") or is_delayed:
            blocked_tasks = [{"id": bid, "title": by_id[bid]["title"]} for bid in blocked_ids if bid in by_id]
            affected_projects = list({by_id[bid].get("project_id") for bid in blocked_ids if by_id.get(bid) and by_id[bid].get("project_id")})
            items.append({
                "task": {"id": t["id"], "title": t["title"], "status": t.get("status"), "priority": t.get("priority"), "due_date": t.get("due_date"), "is_delayed": is_delayed},
                "blocks_count": len(blocked_ids),
                "blocks": blocked_tasks,
                "affected_projects": affected_projects,
                "impact_score": len(blocked_ids) * (2 if is_delayed else 1) * (3 if t.get("priority") in ("high", "critical") else 1),
            })
    items.sort(key=lambda x: -x["impact_score"])
    return {"bottlenecks": items[:10]}


@router.get("/dependencies/task/{tid}")
async def dep_for_task(tid: str, user=Depends(get_current_user)):
    t = await db.tasks.find_one({"id": tid, "owner_id": user["id"]}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Task not found")
    tasks = await db.tasks.find({"owner_id": user["id"]}, {"_id": 0}).to_list(1000)
    by_id = {x["id"]: x for x in tasks}
    upstream = [{"id": d, "title": by_id[d]["title"], "status": by_id[d].get("status")} for d in (t.get("dependencies") or []) if d in by_id]
    downstream = [{"id": x["id"], "title": x["title"], "status": x.get("status")} for x in tasks if tid in (x.get("dependencies") or [])]
    return {"task_id": tid, "upstream": upstream, "downstream": downstream}


# ---- Timeline insights ----
@router.get("/timeline/insights")
async def timeline_insights(user=Depends(get_current_user), lang: str = Depends(get_lang)):
    """Lightweight, surgical analysis of project timelines."""
    uid = user["id"]
    now = datetime.now(timezone.utc)
    projects = await db.projects.find({"members": uid, "status": {"$ne": "archived"}}, {"_id": 0}).to_list(200)
    tasks = await db.tasks.find({"owner_id": uid}, {"_id": 0}).to_list(1000)

    def parse_iso(s):
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None
        except Exception:
            return None

    AR = (lang == "ar")

    def msg_overlap(a, b):
        return f"{a['name']} و {b['name']} متداخلان — كلاهما عالي الأولوية. رتّبهما تسلسليًا أو خصّص مسبقًا فترات تركيز." if AR \
            else f"{a['name']} and {b['name']} overlap — both high-priority. Sequence or pre-allocate focus blocks."

    def msg_compressed(p, n, d):
        return f"{p['name']} يضغط {n} مهمة في {d} يوم — غير واقعي على الأرجح." if AR \
            else f"{p['name']} packs {n} tasks into {d} day(s) — likely unrealistic."

    def msg_slipping(p, days, status):
        return f"تجاوز {p['name']} موعد نهايته بـ {days} يوم وما زال {status}." if AR \
            else f"{p['name']} end date passed {days}d ago and project is still {status}."

    def msg_idle_empty(p):
        return f"{p['name']} بلا مهام. حدّد النطاق أو أوقفه مؤقتًا." if AR \
            else f"{p['name']} has no tasks. Define scope or pause."

    def msg_idle_stale(p, days):
        return f"{p['name']} بلا نشاط منذ {days} يوم." if AR \
            else f"{p['name']} hasn't seen activity in {days} days."

    def msg_dep(t, dep):
        return f"«{t['title']}» يبدأ قبل أن تنتهي تبعيته «{dep['title']}»." if AR \
            else f"'{t['title']}' starts before its dependency '{dep['title']}' ends."

    insights = []
    dated = [p for p in projects if p.get("start_date") and p.get("end_date")]
    for i, a in enumerate(dated):
        for b in dated[i + 1:]:
            sa, ea = parse_iso(a["start_date"]), parse_iso(a["end_date"])
            sb, eb = parse_iso(b["start_date"]), parse_iso(b["end_date"])
            if not (sa and ea and sb and eb):
                continue
            if sa <= eb and sb <= ea:
                if (a.get("priority") in ("high", "critical")) and (b.get("priority") in ("high", "critical")):
                    insights.append({
                        "type": "overlap",
                        "severity": "high",
                        "message": msg_overlap(a, b),
                        "project_ids": [a["id"], b["id"]],
                    })

    for p in dated:
        sa, ea = parse_iso(p["start_date"]), parse_iso(p["end_date"])
        if sa and ea:
            duration_days = (ea - sa).days
            ptasks = [t for t in tasks if t.get("project_id") == p["id"]]
            if duration_days < 7 and len(ptasks) > 5:
                insights.append({
                    "type": "compressed",
                    "severity": "medium",
                    "message": msg_compressed(p, len(ptasks), duration_days),
                    "project_ids": [p["id"]],
                })

    for p in dated:
        ea = parse_iso(p["end_date"])
        if ea and ea < now and p.get("status") not in ("completed", "archived"):
            insights.append({
                "type": "slipping",
                "severity": "high",
                "message": msg_slipping(p, (now - ea).days, p.get('status')),
                "project_ids": [p["id"]],
            })

    for p in projects:
        if p.get("status") != "active":
            continue
        ptasks = [t for t in tasks if t.get("project_id") == p["id"]]
        if not ptasks:
            insights.append({"type": "idle", "severity": "low", "message": msg_idle_empty(p), "project_ids": [p["id"]]})
            continue
        most_recent = max((parse_iso(t.get("updated_at")) or now for t in ptasks), default=now)
        if most_recent and (now - most_recent).days >= 14:
            insights.append({"type": "idle", "severity": "low", "message": msg_idle_stale(p, (now - most_recent).days), "project_ids": [p["id"]]})

    by_id = {t["id"]: t for t in tasks}
    for t in tasks:
        for dep_id in (t.get("dependencies") or []):
            dep = by_id.get(dep_id)
            if not dep:
                continue
            t_start, dep_end = parse_iso(t.get("start_date")), parse_iso(dep.get("end_date"))
            if t_start and dep_end and dep_end > t_start:
                insights.append({
                    "type": "dep_collision",
                    "severity": "medium",
                    "message": msg_dep(t, dep),
                    "task_ids": [t["id"], dep_id],
                })

    severity_order = {"high": 0, "medium": 1, "low": 2}
    insights.sort(key=lambda x: severity_order.get(x["severity"], 9))
    return {"insights": insights[:12], "generated_at": now_iso()}


# ---- Time blocks ----
@router.post("/timeblocks")
async def create_block(body: TimeBlockIn, user=Depends(get_current_user)):
    doc = body.model_dump()
    doc.update({"id": new_id(), "user_id": user["id"], "created_at": now_iso()})
    await db.timeblocks.insert_one(doc)
    return clean(doc)


@router.get("/timeblocks")
async def list_blocks(user=Depends(get_current_user)):
    rows = await db.timeblocks.find({"user_id": user["id"]}, {"_id": 0}).sort("start_date", 1).to_list(500)
    return rows


@router.patch("/timeblocks/{bid}")
async def update_block(bid: str, body: TimeBlockUpdate, user=Depends(get_current_user)):
    upd = body.model_dump(exclude_unset=True)
    res = await db.timeblocks.update_one({"id": bid, "user_id": user["id"]}, {"$set": upd})
    if not res.matched_count:
        raise HTTPException(404, "Not found")
    return await db.timeblocks.find_one({"id": bid}, {"_id": 0})


@router.delete("/timeblocks/{bid}")
async def delete_block(bid: str, user=Depends(get_current_user)):
    await db.timeblocks.delete_one({"id": bid, "user_id": user["id"]})
    return {"ok": True}
