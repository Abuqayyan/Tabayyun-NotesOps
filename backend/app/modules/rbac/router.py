"""RBAC management API: permissions (read), roles (CRUD), assignments, my-permissions."""
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.core.db_postgres import get_session
from app.core.utils import now_iso
from app.modules.rbac.models import Permission, Role, RoleAssignment, SCOPE_TYPES, SCOPE_GLOBAL
from app.modules.rbac.resolver import require_permission, get_permission_keys
from app.modules.rbac.service import role_permission_keys, set_role_permissions
from app.modules.audit.service import record_audit

router = APIRouter()


class RoleIn(BaseModel):
    key: str
    name: str
    description: Optional[str] = ""
    permissions: List[str] = []


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    permissions: Optional[List[str]] = None


class AssignmentIn(BaseModel):
    user_id: str
    role_id: str
    scope_type: str = SCOPE_GLOBAL
    scope_id: Optional[str] = None


async def _role_out(session: AsyncSession, role: Role) -> dict:
    return {
        "id": role.id, "key": role.key, "name": role.name, "description": role.description,
        "is_system": role.is_system, "permissions": await role_permission_keys(session, role.id),
        "created_at": role.created_at, "updated_at": role.updated_at,
    }


# ---- Permissions (catalog) ----
@router.get("/rbac/permissions")
async def list_permissions(user=Depends(require_permission("role.view")), session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(Permission))).scalars().all()
    return [{"key": p.key, "category": p.category, "description": p.description} for p in rows]


# ---- Roles ----
@router.get("/rbac/roles")
async def list_roles(user=Depends(require_permission("role.view")), session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(Role).order_by(Role.name))).scalars().all()
    return [await _role_out(session, r) for r in rows]


@router.post("/rbac/roles")
async def create_role(body: RoleIn, request: Request, user=Depends(require_permission("role.manage")), session: AsyncSession = Depends(get_session)):
    key = body.key.strip().lower().replace(" ", "_")
    if not key:
        raise HTTPException(400, "key required")
    exists = (await session.execute(select(Role).where(Role.key == key))).scalar_one_or_none()
    if exists:
        raise HTTPException(400, "Role key already exists")
    role = Role(key=key, name=body.name, description=body.description or "", is_system=False)
    session.add(role)
    await session.flush()
    await set_role_permissions(session, role.id, body.permissions)
    await record_audit(session, user, "role.create", "role", role.id, after={"key": key, "permissions": body.permissions}, ip=request.client.host if request.client else None)
    await session.commit()
    return await _role_out(session, role)


@router.get("/rbac/roles/{rid}")
async def get_role(rid: str, user=Depends(require_permission("role.view")), session: AsyncSession = Depends(get_session)):
    role = (await session.execute(select(Role).where(Role.id == rid))).scalar_one_or_none()
    if not role:
        raise HTTPException(404, "Role not found")
    return await _role_out(session, role)


@router.patch("/rbac/roles/{rid}")
async def update_role(rid: str, body: RoleUpdate, request: Request, user=Depends(require_permission("role.manage")), session: AsyncSession = Depends(get_session)):
    role = (await session.execute(select(Role).where(Role.id == rid))).scalar_one_or_none()
    if not role:
        raise HTTPException(404, "Role not found")
    before = {"name": role.name, "description": role.description, "permissions": await role_permission_keys(session, rid)}
    if body.name is not None:
        role.name = body.name
    if body.description is not None:
        role.description = body.description
    if body.permissions is not None:
        await set_role_permissions(session, rid, body.permissions)
    role.updated_at = now_iso()
    await record_audit(session, user, "role.update", "role", rid, before=before,
                       after={"name": role.name, "permissions": body.permissions}, ip=request.client.host if request.client else None)
    await session.commit()
    return await _role_out(session, role)


@router.delete("/rbac/roles/{rid}")
async def delete_role(rid: str, request: Request, user=Depends(require_permission("role.manage")), session: AsyncSession = Depends(get_session)):
    role = (await session.execute(select(Role).where(Role.id == rid))).scalar_one_or_none()
    if not role:
        raise HTTPException(404, "Role not found")
    if role.is_system:
        raise HTTPException(400, "System roles cannot be deleted")
    # Remove assignments referencing this role.
    assigns = (await session.execute(select(RoleAssignment).where(RoleAssignment.role_id == rid))).scalars().all()
    for a in assigns:
        await session.delete(a)
    await set_role_permissions(session, rid, [])
    await session.delete(role)
    await record_audit(session, user, "role.delete", "role", rid, before={"key": role.key}, ip=request.client.host if request.client else None)
    await session.commit()
    return {"ok": True}


# ---- Assignments ----
@router.get("/rbac/assignments")
async def list_assignments(user_id: Optional[str] = None, user=Depends(require_permission("role.view")), session: AsyncSession = Depends(get_session)):
    q = select(RoleAssignment)
    if user_id:
        q = q.where(RoleAssignment.user_id == user_id)
    rows = (await session.execute(q)).scalars().all()
    return [{"id": a.id, "user_id": a.user_id, "role_id": a.role_id, "scope_type": a.scope_type,
             "scope_id": a.scope_id, "created_at": a.created_at} for a in rows]


@router.post("/rbac/assignments")
async def create_assignment(body: AssignmentIn, request: Request, user=Depends(require_permission("role.manage")), session: AsyncSession = Depends(get_session)):
    if body.scope_type not in SCOPE_TYPES:
        raise HTTPException(400, f"scope_type must be one of {SCOPE_TYPES}")
    if body.scope_type != SCOPE_GLOBAL and not body.scope_id:
        raise HTTPException(400, "scope_id is required for department/project scope")
    role = (await session.execute(select(Role).where(Role.id == body.role_id))).scalar_one_or_none()
    if not role:
        raise HTTPException(404, "Role not found")
    dup = (await session.execute(select(RoleAssignment).where(
        RoleAssignment.user_id == body.user_id, RoleAssignment.role_id == body.role_id,
        RoleAssignment.scope_type == body.scope_type,
        RoleAssignment.scope_id == (body.scope_id if body.scope_type != SCOPE_GLOBAL else None),
    ))).scalar_one_or_none()
    if dup:
        raise HTTPException(400, "Assignment already exists")
    a = RoleAssignment(user_id=body.user_id, role_id=body.role_id, scope_type=body.scope_type,
                       scope_id=(body.scope_id if body.scope_type != SCOPE_GLOBAL else None), created_by=user["id"])
    session.add(a)
    await record_audit(session, user, "role.assign", "role_assignment", a.id,
                       after={"user_id": body.user_id, "role_id": body.role_id, "scope_type": body.scope_type, "scope_id": body.scope_id},
                       ip=request.client.host if request.client else None)
    await session.commit()
    return {"id": a.id, "user_id": a.user_id, "role_id": a.role_id, "scope_type": a.scope_type, "scope_id": a.scope_id}


@router.delete("/rbac/assignments/{aid}")
async def delete_assignment(aid: str, request: Request, user=Depends(require_permission("role.manage")), session: AsyncSession = Depends(get_session)):
    a = (await session.execute(select(RoleAssignment).where(RoleAssignment.id == aid))).scalar_one_or_none()
    if not a:
        raise HTTPException(404, "Assignment not found")
    await session.delete(a)
    await record_audit(session, user, "role.unassign", "role_assignment", aid,
                       before={"user_id": a.user_id, "role_id": a.role_id}, ip=request.client.host if request.client else None)
    await session.commit()
    return {"ok": True}


# ---- Self ----
@router.get("/rbac/my-permissions")
async def my_permissions(user=Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    keys = await get_permission_keys(session, user)
    return {"is_admin": bool(user.get("is_admin")), "permissions": sorted(keys)}
