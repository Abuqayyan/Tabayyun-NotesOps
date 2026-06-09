"""Organization API: departments, employees, department membership, reporting lines."""
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db_mongo import db as mongo
from app.core.db_postgres import get_session
from app.core.utils import now_iso
from app.modules.org.models import Department, Employee, DepartmentMember
from app.modules.rbac.resolver import require_permission
from app.modules.audit.service import record_audit
from app.shared.activity import emit_activity

router = APIRouter()


class DepartmentIn(BaseModel):
    name: str
    description: Optional[str] = ""
    parent_department_id: Optional[str] = None
    lead_user_id: Optional[str] = None


class DepartmentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    parent_department_id: Optional[str] = None
    lead_user_id: Optional[str] = None
    is_active: Optional[bool] = None


class EmployeeIn(BaseModel):
    user_id: str
    position: Optional[str] = ""
    primary_department_id: Optional[str] = None
    manager_id: Optional[str] = None
    employment_status: Optional[str] = "active"


class EmployeeUpdate(BaseModel):
    position: Optional[str] = None
    primary_department_id: Optional[str] = None
    manager_id: Optional[str] = None
    employment_status: Optional[str] = None


class MemberIn(BaseModel):
    user_id: str
    is_primary: Optional[bool] = False


def _dept_out(d: Department) -> dict:
    return {"id": d.id, "name": d.name, "description": d.description, "parent_department_id": d.parent_department_id,
            "lead_user_id": d.lead_user_id, "is_active": d.is_active, "created_at": d.created_at, "updated_at": d.updated_at}


async def _enrich_users(rows: List[dict], key: str = "user_id") -> None:
    ids = list({r[key] for r in rows if r.get(key)})
    if not ids:
        return
    users = await mongo.users.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "name": 1, "email": 1}).to_list(1000)
    by_id = {u["id"]: u for u in users}
    for r in rows:
        u = by_id.get(r.get(key))
        r["user_name"] = (u or {}).get("name")
        r["user_email"] = (u or {}).get("email")


# ============ DEPARTMENTS ============
@router.get("/departments")
async def list_departments(user=Depends(require_permission("department.view")), session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(Department).order_by(Department.name))).scalars().all()
    return [_dept_out(d) for d in rows]


@router.post("/departments")
async def create_department(body: DepartmentIn, request: Request, user=Depends(require_permission("department.manage")), session: AsyncSession = Depends(get_session)):
    if not body.name.strip():
        raise HTTPException(400, "name required")
    dup = (await session.execute(select(Department).where(Department.name == body.name))).scalar_one_or_none()
    if dup:
        raise HTTPException(400, "Department name already exists")
    if body.lead_user_id and not await mongo.users.find_one({"id": body.lead_user_id}, {"_id": 0, "id": 1}):
        raise HTTPException(404, "lead_user_id not found")
    d = Department(name=body.name.strip(), description=body.description or "",
                   parent_department_id=body.parent_department_id, lead_user_id=body.lead_user_id)
    session.add(d)
    await session.flush()
    await record_audit(session, user, "department.create", "department", d.id, after=_dept_out(d), ip=request.client.host if request.client else None)
    await session.commit()
    await emit_activity(user["id"], "department.created", "department", d.id, department_id=d.id,
                        actor_name=user.get("name"), metadata={"name": d.name})
    return _dept_out(d)


@router.get("/departments/{did}")
async def get_department(did: str, user=Depends(require_permission("department.view")), session: AsyncSession = Depends(get_session)):
    d = (await session.execute(select(Department).where(Department.id == did))).scalar_one_or_none()
    if not d:
        raise HTTPException(404, "Department not found")
    return _dept_out(d)


@router.patch("/departments/{did}")
async def update_department(did: str, body: DepartmentUpdate, request: Request, user=Depends(require_permission("department.manage")), session: AsyncSession = Depends(get_session)):
    d = (await session.execute(select(Department).where(Department.id == did))).scalar_one_or_none()
    if not d:
        raise HTTPException(404, "Department not found")
    before = _dept_out(d)
    for f in ("name", "description", "parent_department_id", "lead_user_id", "is_active"):
        v = getattr(body, f)
        if v is not None:
            setattr(d, f, v)
    d.updated_at = now_iso()
    await record_audit(session, user, "department.update", "department", did, before=before, after=_dept_out(d), ip=request.client.host if request.client else None)
    await session.commit()
    return _dept_out(d)


@router.delete("/departments/{did}")
async def delete_department(did: str, request: Request, user=Depends(require_permission("department.manage")), session: AsyncSession = Depends(get_session)):
    d = (await session.execute(select(Department).where(Department.id == did))).scalar_one_or_none()
    if not d:
        raise HTTPException(404, "Department not found")
    # Detach members, employees, and child departments pointing at this department (avoid orphan FK violations).
    for m in (await session.execute(select(DepartmentMember).where(DepartmentMember.department_id == did))).scalars().all():
        await session.delete(m)
    for e in (await session.execute(select(Employee).where(Employee.primary_department_id == did))).scalars().all():
        e.primary_department_id = None
    for child in (await session.execute(select(Department).where(Department.parent_department_id == did))).scalars().all():
        child.parent_department_id = None
    await session.flush()
    await session.delete(d)
    await record_audit(session, user, "department.delete", "department", did, before=_dept_out(d), ip=request.client.host if request.client else None)
    await session.commit()
    return {"ok": True}


# ============ MEMBERS ============
@router.get("/departments/{did}/members")
async def list_members(did: str, user=Depends(require_permission("department.view")), session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(DepartmentMember).where(DepartmentMember.department_id == did))).scalars().all()
    out = [{"id": m.id, "user_id": m.user_id, "is_primary": m.is_primary, "created_at": m.created_at} for m in rows]
    await _enrich_users(out)
    return out


@router.post("/departments/{did}/members")
async def add_member(did: str, body: MemberIn, request: Request, user=Depends(require_permission("department.manage")), session: AsyncSession = Depends(get_session)):
    d = (await session.execute(select(Department).where(Department.id == did))).scalar_one_or_none()
    if not d:
        raise HTTPException(404, "Department not found")
    if not await mongo.users.find_one({"id": body.user_id}, {"_id": 0, "id": 1}):
        raise HTTPException(404, "user_id not found")
    dup = (await session.execute(select(DepartmentMember).where(
        DepartmentMember.department_id == did, DepartmentMember.user_id == body.user_id))).scalar_one_or_none()
    if dup:
        raise HTTPException(400, "Already a member")
    m = DepartmentMember(department_id=did, user_id=body.user_id, is_primary=bool(body.is_primary))
    session.add(m)
    await record_audit(session, user, "department.add_member", "department", did, after={"user_id": body.user_id}, ip=request.client.host if request.client else None)
    await session.commit()
    return {"id": m.id, "user_id": m.user_id, "is_primary": m.is_primary}


@router.delete("/departments/{did}/members/{uid}")
async def remove_member(did: str, uid: str, request: Request, user=Depends(require_permission("department.manage")), session: AsyncSession = Depends(get_session)):
    m = (await session.execute(select(DepartmentMember).where(
        DepartmentMember.department_id == did, DepartmentMember.user_id == uid))).scalar_one_or_none()
    if not m:
        raise HTTPException(404, "Member not found")
    await session.delete(m)
    await record_audit(session, user, "department.remove_member", "department", did, before={"user_id": uid}, ip=request.client.host if request.client else None)
    await session.commit()
    return {"ok": True}


# ============ EMPLOYEES ============
@router.get("/employees")
async def list_employees(department_id: Optional[str] = None, user=Depends(require_permission("employee.view")), session: AsyncSession = Depends(get_session)):
    q = select(Employee)
    if department_id:
        q = q.where(Employee.primary_department_id == department_id)
    rows = (await session.execute(q)).scalars().all()
    out = [{"id": e.id, "user_id": e.user_id, "position": e.position, "primary_department_id": e.primary_department_id,
            "manager_id": e.manager_id, "employment_status": e.employment_status,
            "created_at": e.created_at, "updated_at": e.updated_at} for e in rows]
    await _enrich_users(out)
    return out


@router.post("/employees")
async def create_employee(body: EmployeeIn, request: Request, user=Depends(require_permission("employee.manage")), session: AsyncSession = Depends(get_session)):
    if not await mongo.users.find_one({"id": body.user_id}, {"_id": 0, "id": 1}):
        raise HTTPException(404, "user_id not found")
    dup = (await session.execute(select(Employee).where(Employee.user_id == body.user_id))).scalar_one_or_none()
    if dup:
        raise HTTPException(400, "Employee profile already exists for this user")
    if body.primary_department_id and not (await session.execute(select(Department).where(Department.id == body.primary_department_id))).scalar_one_or_none():
        raise HTTPException(404, "primary_department_id not found")
    if body.manager_id and not (await session.execute(select(Employee).where(Employee.id == body.manager_id))).scalar_one_or_none():
        raise HTTPException(404, "manager_id not found")
    e = Employee(user_id=body.user_id, position=body.position or "",
                 primary_department_id=body.primary_department_id, manager_id=body.manager_id,
                 employment_status=body.employment_status or "active")
    session.add(e)
    await session.flush()
    await record_audit(session, user, "employee.create", "employee", e.id, after={"user_id": e.user_id, "position": e.position}, ip=request.client.host if request.client else None)
    await session.commit()
    await emit_activity(user["id"], "employee.created", "employee", e.id, department_id=e.primary_department_id,
                        actor_name=user.get("name"), metadata={"user_id": e.user_id})
    return {"id": e.id, "user_id": e.user_id, "position": e.position, "primary_department_id": e.primary_department_id,
            "manager_id": e.manager_id, "employment_status": e.employment_status}


@router.get("/employees/{eid}")
async def get_employee(eid: str, user=Depends(require_permission("employee.view")), session: AsyncSession = Depends(get_session)):
    e = (await session.execute(select(Employee).where(Employee.id == eid))).scalar_one_or_none()
    if not e:
        raise HTTPException(404, "Employee not found")
    out = [{"id": e.id, "user_id": e.user_id, "position": e.position, "primary_department_id": e.primary_department_id,
            "manager_id": e.manager_id, "employment_status": e.employment_status}]
    await _enrich_users(out)
    return out[0]


@router.patch("/employees/{eid}")
async def update_employee(eid: str, body: EmployeeUpdate, request: Request, user=Depends(require_permission("employee.manage")), session: AsyncSession = Depends(get_session)):
    e = (await session.execute(select(Employee).where(Employee.id == eid))).scalar_one_or_none()
    if not e:
        raise HTTPException(404, "Employee not found")
    if body.manager_id and body.manager_id == eid:
        raise HTTPException(400, "An employee cannot manage themselves")
    before = {"position": e.position, "primary_department_id": e.primary_department_id, "manager_id": e.manager_id, "employment_status": e.employment_status}
    for f in ("position", "primary_department_id", "manager_id", "employment_status"):
        v = getattr(body, f)
        if v is not None:
            setattr(e, f, v)
    e.updated_at = now_iso()
    await record_audit(session, user, "employee.update", "employee", eid, before=before, ip=request.client.host if request.client else None)
    await session.commit()
    return {"id": e.id, "user_id": e.user_id, "position": e.position, "primary_department_id": e.primary_department_id,
            "manager_id": e.manager_id, "employment_status": e.employment_status}


@router.delete("/employees/{eid}")
async def delete_employee(eid: str, request: Request, user=Depends(require_permission("employee.manage")), session: AsyncSession = Depends(get_session)):
    e = (await session.execute(select(Employee).where(Employee.id == eid))).scalar_one_or_none()
    if not e:
        raise HTTPException(404, "Employee not found")
    # Detach reports.
    for r in (await session.execute(select(Employee).where(Employee.manager_id == eid))).scalars().all():
        r.manager_id = None
    await session.delete(e)
    await record_audit(session, user, "employee.delete", "employee", eid, before={"user_id": e.user_id}, ip=request.client.host if request.client else None)
    await session.commit()
    return {"ok": True}
