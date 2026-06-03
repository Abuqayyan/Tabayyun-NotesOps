"""RBAC seeding + helpers."""
from typing import List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils import now_iso
from app.modules.rbac.catalog import PERMISSIONS, SYSTEM_ROLES, ALL_PERMISSION_KEYS
from app.modules.rbac.models import Permission, Role, RolePermission


async def seed_rbac(session: AsyncSession) -> dict:
    """Idempotently seed the permission catalog and system roles.

    Permissions are upserted by key. System roles are created (with their catalog
    permissions) only if missing — existing system roles are left untouched so admin
    edits are preserved across restarts.
    """
    created_perms = 0
    perm_by_key = {}
    existing = {p.key: p for p in (await session.execute(select(Permission))).scalars().all()}
    for key, category, desc in PERMISSIONS:
        p = existing.get(key)
        if not p:
            p = Permission(key=key, category=category, description=desc)
            session.add(p)
            created_perms += 1
        perm_by_key[key] = p
    await session.flush()  # assign ids

    created_roles = 0
    existing_roles = {r.key: r for r in (await session.execute(select(Role))).scalars().all()}
    for rkey, spec in SYSTEM_ROLES.items():
        if rkey in existing_roles:
            continue
        role = Role(key=rkey, name=spec["name"], description=spec["description"], is_system=True)
        session.add(role)
        await session.flush()
        keys = ALL_PERMISSION_KEYS if spec["permissions"] == "*" else spec["permissions"]
        for k in keys:
            perm = perm_by_key.get(k)
            if perm:
                session.add(RolePermission(role_id=role.id, permission_id=perm.id))
        created_roles += 1

    await session.commit()
    return {"permissions_created": created_perms, "roles_created": created_roles}


async def role_permission_keys(session: AsyncSession, role_id: str) -> List[str]:
    rows = (await session.execute(
        select(Permission.key)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_id == role_id)
    )).scalars().all()
    return sorted(rows)


async def set_role_permissions(session: AsyncSession, role_id: str, keys: List[str]) -> None:
    """Replace a role's permissions with the given set of permission keys."""
    perms = {p.key: p for p in (await session.execute(select(Permission))).scalars().all()}
    # clear existing
    existing = (await session.execute(
        select(RolePermission).where(RolePermission.role_id == role_id)
    )).scalars().all()
    for rp in existing:
        await session.delete(rp)
    await session.flush()
    for k in keys:
        p = perms.get(k)
        if p:
            session.add(RolePermission(role_id=role_id, permission_id=p.id))
