"""Knowledge Base domain helpers: visibility scoping, search query, versioning.

Articles live in Mongo (`knowledge_articles`) with edit history in `knowledge_versions`.
Authorisation reuses the RBAC resolver: company-wide articles are visible to any kb.view
holder; department-scoped articles are visible to that department's members, holders of a
kb.view assignment scoped to it, or kb.manage/admin.
"""
from typing import Dict, Any, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db_mongo import db
from app.modules.rbac.resolver import permission_scopes, user_department_ids

ARTICLE_TYPES = {
    "policy", "procedure", "playbook", "runbook", "tech_doc",
    "department_doc", "meeting_archive", "internal_guide",
}


async def view_context(session: AsyncSession, user: dict) -> Dict[str, Any]:
    """Resolve what the user may see: company-wide flag + the set of accessible departments."""
    if user.get("is_admin"):
        return {"manage": True, "can_view_company": True, "all_departments": True, "dept_ids": set()}
    view_global, view_depts = await permission_scopes(session, user, "kb.view")
    manage_global, manage_depts = await permission_scopes(session, user, "kb.manage")
    member_depts = await user_department_ids(session, user["id"])
    has_any_view = view_global or bool(view_depts) or manage_global or bool(manage_depts)
    accessible = set(view_depts) | set(manage_depts) | set(member_depts)
    return {
        "manage": manage_global,
        "can_view_company": has_any_view,
        "all_departments": manage_global,
        "dept_ids": accessible,
    }


def visibility_query(ctx: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    """Mongo filter for the articles a user may read (published in scope + their own drafts)."""
    if ctx.get("all_departments"):
        scope = {}  # admin / kb.manage: everything
    else:
        ors: List[Dict[str, Any]] = [{"owner_id": user_id}]  # always see your own
        if ctx.get("can_view_company"):
            ors.append({"department_id": None, "status": "published"})
        if ctx.get("dept_ids"):
            ors.append({"department_id": {"$in": list(ctx["dept_ids"])}, "status": "published"})
        scope = {"$or": ors}
    return scope


async def can_edit(session: AsyncSession, user: dict, article: dict) -> bool:
    if user.get("is_admin") or article.get("owner_id") == user["id"]:
        return True
    from app.modules.rbac.resolver import user_can
    return await user_can(session, user, "kb.edit", department_id=article.get("department_id")) \
        or await user_can(session, user, "kb.manage", department_id=article.get("department_id"))


async def can_delete(session: AsyncSession, user: dict, article: dict) -> bool:
    if user.get("is_admin") or article.get("owner_id") == user["id"]:
        return True
    from app.modules.rbac.resolver import user_can
    return await user_can(session, user, "kb.delete", department_id=article.get("department_id")) \
        or await user_can(session, user, "kb.manage", department_id=article.get("department_id"))


async def can_view_article(ctx: Dict[str, Any], article: dict, user_id: str) -> bool:
    if ctx.get("all_departments") or article.get("owner_id") == user_id:
        return True
    if article.get("status") != "published":
        return False
    if article.get("department_id") is None:
        return bool(ctx.get("can_view_company"))
    return article.get("department_id") in ctx.get("dept_ids", set())


async def snapshot_version(article: dict) -> None:
    """Save the current article state to history before it is overwritten."""
    from app.core.utils import new_id, now_iso
    await db.knowledge_versions.insert_one({
        "id": new_id(), "article_id": article["id"], "version": article.get("version", 1),
        "title": article.get("title"), "body": article.get("body"), "category": article.get("category"),
        "article_type": article.get("article_type"), "tags": article.get("tags", []),
        "attachments": article.get("attachments", []), "edited_by": article.get("updated_by") or article.get("created_by"),
        "created_at": now_iso(),
    })
