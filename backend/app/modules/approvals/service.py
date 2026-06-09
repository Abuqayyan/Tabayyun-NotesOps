"""Approval workflow engine.

Pure domain logic, no HTTP: resolve a step's approver from the live org/RBAC structures,
instantiate a request's step chain, and check whether a given user may decide the active
step. The router wires these into endpoints + activity/audit/notifications.
"""
from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils import now_iso
from app.modules.approvals.models import (
    ApprovalTemplate, ApprovalTemplateStep, ApprovalRequest, ApprovalStep,
    APPROVER_MANAGER, APPROVER_SKIP_LEVEL, APPROVER_DEPARTMENT_LEAD, APPROVER_ROLE, APPROVER_USER,
)
from app.modules.org.models import Employee, Department
from app.modules.rbac.models import RoleAssignment, Role
from app.modules.rbac.models import SCOPE_GLOBAL, SCOPE_DEPARTMENT


async def _manager_user_id(session: AsyncSession, user_id: str, levels: int = 1) -> Optional[str]:
    """Walk the reporting chain `levels` times; return the manager's user_id (or None)."""
    emp = (await session.execute(select(Employee).where(Employee.user_id == user_id))).scalar_one_or_none()
    for _ in range(levels):
        if not emp or not emp.manager_id:
            return None
        emp = (await session.execute(select(Employee).where(Employee.id == emp.manager_id))).scalar_one_or_none()
        if not emp:
            return None
    return emp.user_id if emp else None


async def resolve_step_approver(session: AsyncSession, step: ApprovalStep, request: ApprovalRequest) -> Optional[str]:
    """Resolve the concrete approver user_id for a step, or None for role-based (any holder)."""
    t = step.approver_type
    if t == APPROVER_MANAGER:
        return await _manager_user_id(session, request.requester_id, 1)
    if t == APPROVER_SKIP_LEVEL:
        return await _manager_user_id(session, request.requester_id, 2)
    if t == APPROVER_DEPARTMENT_LEAD:
        if request.department_id:
            d = (await session.execute(select(Department).where(Department.id == request.department_id))).scalar_one_or_none()
            return d.lead_user_id if d else None
        return None
    if t == APPROVER_USER:
        return step.approver_value
    # APPROVER_ROLE -> any holder; no single concrete approver.
    return None


async def _users_with_role(session: AsyncSession, role_ref: str, department_id: Optional[str]) -> set:
    """User ids holding a role (by id or key) at global scope or the request's department scope."""
    role = (await session.execute(select(Role).where((Role.id == role_ref) | (Role.key == role_ref)))).scalar_one_or_none()
    if not role:
        return set()
    rows = (await session.execute(select(RoleAssignment).where(RoleAssignment.role_id == role.id))).scalars().all()
    out = set()
    for a in rows:
        if a.scope_type == SCOPE_GLOBAL:
            out.add(a.user_id)
        elif a.scope_type == SCOPE_DEPARTMENT and department_id and a.scope_id == department_id:
            out.add(a.user_id)
    return out


async def can_user_decide(session: AsyncSession, user: dict, step: ApprovalStep, request: ApprovalRequest) -> bool:
    """True if `user` is allowed to approve/reject the given (active) step."""
    if user.get("is_admin"):
        return True
    if step.approver_user_id and step.approver_user_id == user["id"]:
        return True
    if step.approver_type == APPROVER_ROLE and step.approver_value:
        holders = await _users_with_role(session, step.approver_value, request.department_id)
        if user["id"] in holders:
            return True
    return False


async def instantiate_request(
    session: AsyncSession, template: ApprovalTemplate, requester_id: str,
    department_id: Optional[str], title: str, form_data: dict,
) -> Tuple[ApprovalRequest, List[ApprovalStep]]:
    """Create the request and snapshot its ordered step instances; activate step 1."""
    tsteps = (await session.execute(
        select(ApprovalTemplateStep).where(ApprovalTemplateStep.template_id == template.id)
        .order_by(ApprovalTemplateStep.step_order)
    )).scalars().all()
    if not tsteps:
        raise ValueError("Template has no steps")

    req = ApprovalRequest(
        template_id=template.id, requester_id=requester_id, department_id=department_id,
        title=title or template.name, status="pending", current_step=tsteps[0].step_order,
        form_data=form_data or {},
    )
    session.add(req)
    await session.flush()

    instances: List[ApprovalStep] = []
    for ts in tsteps:
        si = ApprovalStep(
            request_id=req.id, step_order=ts.step_order, name=ts.name,
            approver_type=ts.approver_type, approver_value=ts.approver_value, status="pending",
        )
        session.add(si)
        instances.append(si)
    await session.flush()

    # Resolve + activate the first step.
    first = instances[0]
    first.approver_user_id = await resolve_step_approver(session, first, req)
    first.activated_at = now_iso()
    return req, instances


async def active_step(session: AsyncSession, request: ApprovalRequest) -> Optional[ApprovalStep]:
    return (await session.execute(
        select(ApprovalStep).where(
            ApprovalStep.request_id == request.id, ApprovalStep.step_order == request.current_step)
    )).scalar_one_or_none()


async def advance_after_approval(session: AsyncSession, request: ApprovalRequest) -> Optional[ApprovalStep]:
    """Move to the next pending step (resolving its approver) or finalise as approved.

    Returns the newly-activated step, or None if the request is now fully approved.
    """
    nxt = (await session.execute(
        select(ApprovalStep).where(
            ApprovalStep.request_id == request.id, ApprovalStep.step_order > request.current_step)
        .order_by(ApprovalStep.step_order)
    )).scalars().first()
    if not nxt:
        request.status = "approved"
        request.decided_at = now_iso()
        request.updated_at = now_iso()
        return None
    request.current_step = nxt.step_order
    request.updated_at = now_iso()
    nxt.approver_user_id = await resolve_step_approver(session, nxt, request)
    nxt.activated_at = now_iso()
    return nxt
