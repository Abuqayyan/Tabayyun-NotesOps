"""Knowledge Base API: versioned articles with categories, tags, department scoping,
search, and attachments. RBAC + Activity Feed + Audit Log integrated.
"""
import re
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db_mongo import db
from app.core.db_postgres import get_session
from app.core.security import get_current_user
from app.core.utils import now_iso, new_id
from app.modules.knowledge import service as kb
from app.modules.rbac.resolver import ensure_permission, user_can
from app.modules.audit.service import record_audit
from app.shared.activity import emit_activity

router = APIRouter()


class ArticleIn(BaseModel):
    title: str
    body: Optional[str] = ""
    category: Optional[str] = "general"
    article_type: Optional[str] = "internal_guide"
    tags: Optional[List[str]] = []
    department_id: Optional[str] = None  # None = company-wide
    status: Optional[str] = "published"  # draft|published


class ArticleUpdate(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    category: Optional[str] = None
    article_type: Optional[str] = None
    tags: Optional[List[str]] = None
    department_id: Optional[str] = None
    status: Optional[str] = None


class AttachmentIn(BaseModel):
    filename: str
    url: str


def _out(a: dict) -> dict:
    a = dict(a)
    a.pop("_id", None)
    return a


async def _enrich_owner(rows: List[dict]) -> None:
    ids = list({r.get("owner_id") for r in rows if r.get("owner_id")})
    if not ids:
        return
    users = await db.users.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(1000)
    by_id = {u["id"]: u for u in users}
    for r in rows:
        r["owner_name"] = (by_id.get(r.get("owner_id")) or {}).get("name")


@router.post("/knowledge")
async def create_article(body: ArticleIn, request: Request,
                         user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    if not body.title.strip():
        raise HTTPException(400, "title required")
    if body.article_type and body.article_type not in kb.ARTICLE_TYPES:
        raise HTTPException(400, f"Invalid article_type. Allowed: {sorted(kb.ARTICLE_TYPES)}")
    await ensure_permission(session, user, "kb.create", department_id=body.department_id)
    doc = {
        "id": new_id(), "title": body.title.strip(), "body": body.body or "",
        "category": body.category or "general", "article_type": body.article_type or "internal_guide",
        "tags": [t.strip() for t in (body.tags or []) if t.strip()],
        "department_id": body.department_id, "owner_id": user["id"],
        "status": body.status if body.status in ("draft", "published") else "published",
        "version": 1, "attachments": [],
        "created_by": user["id"], "updated_by": user["id"],
        "created_at": now_iso(), "updated_at": now_iso(),
    }
    await db.knowledge_articles.insert_one(doc)
    await record_audit(session, user, "kb.create", "knowledge_article", doc["id"],
                       after={"title": doc["title"], "type": doc["article_type"], "department_id": doc["department_id"]},
                       ip=request.client.host if request.client else None)
    await session.commit()
    await emit_activity(user["id"], "knowledge.created", "knowledge_article", doc["id"],
                        department_id=doc["department_id"], actor_name=user.get("name"),
                        metadata={"title": doc["title"], "type": doc["article_type"]})
    return _out(doc)


@router.get("/knowledge")
async def list_articles(q: Optional[str] = None, category: Optional[str] = None,
                        article_type: Optional[str] = None, tag: Optional[str] = None,
                        department_id: Optional[str] = None, status: Optional[str] = None, limit: int = 100,
                        user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    limit = min(max(limit, 1), 500)
    ctx = await kb.view_context(session, user)
    query: Dict[str, Any] = dict(kb.visibility_query(ctx, user["id"]))
    extra: Dict[str, Any] = {}
    if category:
        extra["category"] = category
    if article_type:
        extra["article_type"] = article_type
    if tag:
        extra["tags"] = tag
    if department_id:
        extra["department_id"] = department_id
    if status:
        extra["status"] = status
    if q:
        rx = re.compile(re.escape(q), re.IGNORECASE)
        extra["$and"] = [{"$or": [{"title": rx}, {"body": rx}, {"tags": rx}]}]
    final = {"$and": [query, extra]} if (query and extra) else (extra or query)
    rows = await db.knowledge_articles.find(final, {"_id": 0}).sort("updated_at", -1).to_list(limit)
    await _enrich_owner(rows)
    return rows


@router.get("/knowledge/{aid}")
async def get_article(aid: str, user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    a = await db.knowledge_articles.find_one({"id": aid}, {"_id": 0})
    if not a:
        raise HTTPException(404, "Article not found")
    ctx = await kb.view_context(session, user)
    if not await kb.can_view_article(ctx, a, user["id"]):
        raise HTTPException(403, "No access to this article")
    rows = [a]
    await _enrich_owner(rows)
    return rows[0]


@router.patch("/knowledge/{aid}")
async def update_article(aid: str, body: ArticleUpdate, request: Request,
                         user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    a = await db.knowledge_articles.find_one({"id": aid}, {"_id": 0})
    if not a:
        raise HTTPException(404, "Article not found")
    if not await kb.can_edit(session, user, a):
        raise HTTPException(403, "No edit access to this article")
    if body.article_type and body.article_type not in kb.ARTICLE_TYPES:
        raise HTTPException(400, "Invalid article_type")
    # Moving an article into a department requires create rights there.
    if body.department_id is not None and body.department_id != a.get("department_id"):
        await ensure_permission(session, user, "kb.create", department_id=body.department_id)

    changes = {f: getattr(body, f) for f in ("title", "body", "category", "article_type", "tags") if getattr(body, f) is not None}
    is_content_change = bool(changes)
    if is_content_change:
        await kb.snapshot_version(a)  # archive the pre-edit state

    upd: Dict[str, Any] = {"updated_at": now_iso(), "updated_by": user["id"]}
    upd.update(changes)
    if body.status is not None and body.status in ("draft", "published", "archived"):
        upd["status"] = body.status
    if body.department_id is not None:
        upd["department_id"] = body.department_id
    if is_content_change:
        upd["version"] = a.get("version", 1) + 1
    await db.knowledge_articles.update_one({"id": aid}, {"$set": upd})

    verb = "knowledge.published" if (body.status == "published" and a.get("status") != "published") else "knowledge.updated"
    await record_audit(session, user, "kb.update", "knowledge_article", aid,
                       before={"version": a.get("version"), "status": a.get("status")},
                       after={"version": upd.get("version", a.get("version")), "status": upd.get("status", a.get("status"))},
                       ip=request.client.host if request.client else None)
    await session.commit()
    await emit_activity(user["id"], verb, "knowledge_article", aid,
                        department_id=upd.get("department_id", a.get("department_id")),
                        actor_name=user.get("name"), metadata={"title": upd.get("title", a.get("title"))})
    return await db.knowledge_articles.find_one({"id": aid}, {"_id": 0})


@router.delete("/knowledge/{aid}")
async def delete_article(aid: str, request: Request,
                         user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    a = await db.knowledge_articles.find_one({"id": aid}, {"_id": 0})
    if not a:
        raise HTTPException(404, "Article not found")
    if not await kb.can_delete(session, user, a):
        raise HTTPException(403, "No delete access to this article")
    await db.knowledge_articles.delete_one({"id": aid})
    await db.knowledge_versions.delete_many({"article_id": aid})
    await record_audit(session, user, "kb.delete", "knowledge_article", aid,
                       before={"title": a.get("title")}, ip=request.client.host if request.client else None)
    await session.commit()
    await emit_activity(user["id"], "knowledge.deleted", "knowledge_article", aid,
                        department_id=a.get("department_id"), actor_name=user.get("name"),
                        metadata={"title": a.get("title")})
    return {"ok": True}


# ---- Versioning ----
@router.get("/knowledge/{aid}/versions")
async def list_versions(aid: str, user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    a = await db.knowledge_articles.find_one({"id": aid}, {"_id": 0})
    if not a:
        raise HTTPException(404, "Article not found")
    ctx = await kb.view_context(session, user)
    if not await kb.can_view_article(ctx, a, user["id"]):
        raise HTTPException(403, "No access to this article")
    rows = await db.knowledge_versions.find({"article_id": aid}, {"_id": 0}).sort("version", -1).to_list(200)
    return rows


# ---- Attachments (metadata) ----
@router.post("/knowledge/{aid}/attachments")
async def add_attachment(aid: str, body: AttachmentIn,
                         user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    a = await db.knowledge_articles.find_one({"id": aid}, {"_id": 0})
    if not a:
        raise HTTPException(404, "Article not found")
    if not await kb.can_edit(session, user, a):
        raise HTTPException(403, "No edit access to this article")
    att = list(a.get("attachments") or [])
    att.append({"id": new_id(), "filename": body.filename, "url": body.url,
                "uploaded_by": user["id"], "uploaded_at": now_iso()})
    await db.knowledge_articles.update_one({"id": aid}, {"$set": {"attachments": att, "updated_at": now_iso()}})
    return {"attachments": att}
