"""The RBAC resolver — the single authority for 'can this user do X (here)?'.

All authorization flows through this. Code asks for PERMISSIONS, scoped to a resource's
department/project. Legacy Mongo `is_admin` users are treated as superusers during the
transition (so existing admin behavior is preserved while dynamic roles are adopted).
"""
from typing import Optional, Set

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.core.db_postgres import get_session
from typing import Tuple

from app.modules.rbac.catalog import ALL_PERMISSION_KEYS
from app.modules.rbac.models import (
    RoleAssignment, RolePermission, Permission,
    SCOPE_GLOBAL, SCOPE_DEPARTMENT, SCOPE_PROJECT,
)


async def get_permission_keys(
    session: AsyncSession,
    user: dict,
    department_id: Optional[str] = None,
    project_id: Optional[str] = None,
) -> Set[str]:
    """Effective permission keys for the user within the given scope."""
    # Legacy super-admin bridge.
    if user.get("is_admin"):
        return set(ALL_PERMISSION_KEYS)

    uid = user["id"]
    assignments = (await session.execute(
        select(RoleAssignment).where(RoleAssignment.user_id == uid)
    )).scalars().all()

    role_ids = []
    for a in assignments:
        if a.scope_type == SCOPE_GLOBAL:
            role_ids.append(a.role_id)
        elif a.scope_type == SCOPE_DEPARTMENT and department_id and a.scope_id == department_id:
            role_ids.append(a.role_id)
        elif a.scope_type == SCOPE_PROJECT and project_id and a.scope_id == project_id:
            role_ids.append(a.role_id)

    if not role_ids:
        return set()

    keys = (await session.execute(
        select(Permission.key)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_id.in_(role_ids))
    )).scalars().all()
    return set(keys)


async def user_can(
    session: AsyncSession,
    user: dict,
    permission: str,
    department_id: Optional[str] = None,
    project_id: Optional[str] = None,
) -> bool:
    return permission in await get_permission_keys(session, user, department_id, project_id)


async def permission_scopes(session: AsyncSession, user: dict, permission: str) -> Tuple[bool, Set[str]]:
    """Where does the user hold `permission`?

    Returns (held_globally, {department_ids where held via a department-scoped role}).
    This is what read endpoints need to filter results: get_permission_keys answers a
    single scope, but a department-scoped manager's permissions are invisible when you
    resolve at the global scope. Admins hold everything globally.
    """
    if user.get("is_admin"):
        return True, set()
    assignments = (await session.execute(
        select(RoleAssignment).where(RoleAssignment.user_id == user["id"])
    )).scalars().all()
    if not assignments:
        return False, set()
    perm = (await session.execute(select(Permission).where(Permission.key == permission))).scalar_one_or_none()
    if not perm:
        return False, set()
    roles_with_perm = set((await session.execute(
        select(RolePermission.role_id).where(RolePermission.permission_id == perm.id)
    )).scalars().all())
    held_global = False
    dept_ids: Set[str] = set()
    for a in assignments:
        if a.role_id not in roles_with_perm:
            continue
        if a.scope_type == SCOPE_GLOBAL:
            held_global = True
        elif a.scope_type == SCOPE_DEPARTMENT and a.scope_id:
            dept_ids.add(a.scope_id)
    return held_global, dept_ids


def require_permission(permission: str):
    """FastAPI dependency factory enforcing a GLOBAL-scoped permission.

    Returns the current user when allowed; raises 403 otherwise. For resource-scoped
    checks (department/project), call ensure_permission(...) inside the handler with the
    scope so department/project-scoped role assignments are honoured.
    """
    async def _dep(user: dict = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> dict:
        if await user_can(session, user, permission):
            return user
        raise HTTPException(403, f"Missing permission: {permission}")

    return _dep


async def ensure_permission(
    session: AsyncSession,
    user: dict,
    permission: str,
    department_id: Optional[str] = None,
    project_id: Optional[str] = None,
) -> None:
    """Raise 403 unless the user holds `permission` in the given scope.

    Unlike require_permission (global only), this honours department/project-scoped
    role assignments — e.g. a Department Manager assigned with scope=department:X can
    act inside X but nowhere else. Use inside handlers once the resource's department
    or project is known.
    """
    if not await user_can(session, user, permission, department_id=department_id, project_id=project_id):
        raise HTTPException(403, f"Missing permission: {permission}")


async def user_department_ids(session: AsyncSession, user_id: str) -> Set[str]:
    """All department ids a user belongs to (primary employee dept + memberships)."""
    from app.modules.org.models import Employee, DepartmentMember
    out: Set[str] = set()
    emp = (await session.execute(select(Employee).where(Employee.user_id == user_id))).scalar_one_or_none()
    if emp and emp.primary_department_id:
        out.add(emp.primary_department_id)
    mem = (await session.execute(
        select(DepartmentMember.department_id).where(DepartmentMember.user_id == user_id)
    )).scalars().all()
    out.update(mem)
    return out


async def direct_report_user_ids(session: AsyncSession, manager_user_id: str) -> Set[str]:
    """User ids of employees who report (manager_id) to the given user's employee record."""
    from app.modules.org.models import Employee
    mgr = (await session.execute(select(Employee).where(Employee.user_id == manager_user_id))).scalar_one_or_none()
    if not mgr:
        return set()
    rows = (await session.execute(
        select(Employee.user_id).where(Employee.manager_id == mgr.id)
    )).scalars().all()
    return set(rows)
