"""Project access helpers (DB-backed wrappers over the pure role helpers).

The pure role logic lives in the top-level security_utils module (kept in place for
Phase 0). Dynamic, org-wide RBAC replaces this in Phase 1.
"""
from typing import List
from fastapi import HTTPException

from app.core.db_mongo import db
# security_utils.py is a top-level backend module (kept in place for Phase 0).
from security_utils import project_role, can_view, can_edit, can_admin  # noqa: F401 (re-exported)

__all__ = [
    "project_role", "can_view", "can_edit", "can_admin",
    "load_project_or_403", "user_visible_project_ids",
]


async def load_project_or_403(pid: str, user_id: str, require_edit: bool = False, require_admin: bool = False) -> dict:
    p = await db.projects.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Project not found")
    if require_admin and not can_admin(p, user_id):
        raise HTTPException(403, "Only the project owner can do this")
    if require_edit and not can_edit(p, user_id):
        raise HTTPException(403, "You need editor access for this project")
    if not require_edit and not require_admin and not can_view(p, user_id):
        raise HTTPException(403, "You don't have access to this project")
    return p


async def user_visible_project_ids(user_id: str) -> List[str]:
    """All project ids the user can view (owner, role-mapped, or legacy members)."""
    rows = await db.projects.find(
        {"$or": [
            {"owner_id": user_id},
            {f"roles.{user_id}": {"$exists": True}},
            {"members": user_id},
        ]},
        {"_id": 0, "id": 1},
    ).to_list(1000)
    return [r["id"] for r in rows]
