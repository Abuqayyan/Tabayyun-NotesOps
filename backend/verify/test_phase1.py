"""Phase 1 verification: dynamic RBAC, org (departments/employees/members), audit, activity.

Runs the real app with the relational layer on SQLite (stand-in for Postgres).
"""
import asyncio
import os

import pytest

P = {}


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(scope="module", autouse=True)
def setup(client, db):
    # Admin (register sets is_admin True)
    r = client.post("/api/auth/register", json={"email": "p1admin@opscore.app", "password": "adminpass1", "name": "P1 Admin"})
    P["admin"] = r.json()["token"]
    P["admin_id"] = r.json()["user"]["id"]
    # Member: register then demote to non-admin
    r2 = client.post("/api/auth/register", json={"email": "p1member@opscore.app", "password": "memberpass1", "name": "P1 Member"})
    P["member"] = r2.json()["token"]
    P["member_id"] = r2.json()["user"]["id"]
    run(db.users.update_one({"id": P["member_id"]}, {"$set": {"is_admin": False}}))
    yield


# ---- Seeding ----
def test_seeded_permissions_and_roles(client):
    perms = client.get("/api/rbac/permissions", headers=H(P["admin"])).json()
    keys = {p["key"] for p in perms}
    assert {"role.manage", "department.view", "department.manage", "activity.view_all", "audit.view"} <= keys
    roles = client.get("/api/rbac/roles", headers=H(P["admin"])).json()
    by_key = {r["key"]: r for r in roles}
    assert {"administrator", "executive", "department_manager", "employee"} <= set(by_key)
    assert by_key["administrator"]["is_system"] is True
    assert "role.manage" in by_key["administrator"]["permissions"]


def test_my_permissions_admin(client):
    me = client.get("/api/rbac/my-permissions", headers=H(P["admin"])).json()
    assert me["is_admin"] is True and "role.manage" in me["permissions"]


# ---- Dynamic RBAC enforcement ----
def test_member_denied_without_role(client):
    assert client.get("/api/departments", headers=H(P["member"])).status_code == 403
    assert client.post("/api/departments", json={"name": "X"}, headers=H(P["member"])).status_code == 403
    me = client.get("/api/rbac/my-permissions", headers=H(P["member"])).json()
    assert me["is_admin"] is False and me["permissions"] == []


def test_admin_creates_department(client):
    r = client.post("/api/departments", json={"name": "Fraud Investigation", "description": "SOC-adjacent"}, headers=H(P["admin"]))
    assert r.status_code == 200, r.text
    P["dept_id"] = r.json()["id"]
    assert any(d["id"] == P["dept_id"] for d in client.get("/api/departments", headers=H(P["admin"])).json())


def test_dynamic_grant_and_revoke(client):
    # custom role with department.view
    role = client.post("/api/rbac/roles", json={"key": "dept_viewer", "name": "Dept Viewer", "permissions": ["department.view"]}, headers=H(P["admin"]))
    assert role.status_code == 200, role.text
    rid = role.json()["id"]
    # still denied (no assignment)
    assert client.get("/api/departments", headers=H(P["member"])).status_code == 403
    # assign globally
    a = client.post("/api/rbac/assignments", json={"user_id": P["member_id"], "role_id": rid, "scope_type": "global"}, headers=H(P["admin"]))
    assert a.status_code == 200, a.text
    aid = a.json()["id"]
    # now allowed
    assert client.get("/api/departments", headers=H(P["member"])).status_code == 200
    me = client.get("/api/rbac/my-permissions", headers=H(P["member"])).json()
    assert "department.view" in me["permissions"]
    # revoke -> denied again
    assert client.delete(f"/api/rbac/assignments/{aid}", headers=H(P["admin"])).status_code == 200
    assert client.get("/api/departments", headers=H(P["member"])).status_code == 403


def test_role_assignment_scope_is_enforced(client):
    # role with a permission the member has nowhere else
    role = client.post("/api/rbac/roles", json={"key": "dept_reporter", "name": "Dept Reporter", "permissions": ["report.view_department"]}, headers=H(P["admin"])).json()
    # assign with DEPARTMENT scope on dept_id
    client.post("/api/rbac/assignments", json={"user_id": P["member_id"], "role_id": role["id"], "scope_type": "department", "scope_id": P["dept_id"]}, headers=H(P["admin"]))

    async def _scope_check():
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
        from app.modules.rbac.resolver import get_permission_keys
        eng = create_async_engine(os.environ["DATABASE_URL"])
        Session = async_sessionmaker(eng, expire_on_commit=False)
        mu = {"id": P["member_id"], "is_admin": False}
        async with Session() as s:
            g = await get_permission_keys(s, mu)                                   # global scope
            d = await get_permission_keys(s, mu, department_id=P["dept_id"])        # matching dept
            o = await get_permission_keys(s, mu, department_id="some-other-dept")   # other dept
        await eng.dispose()
        return g, d, o

    g, d, o = run(_scope_check())
    assert "report.view_department" not in g       # not granted globally
    assert "report.view_department" in d           # granted within its department
    assert "report.view_department" not in o       # not in a different department


# ---- Employees ----
def test_employees_crud(client):
    r = client.post("/api/employees", json={"user_id": P["member_id"], "position": "Analyst", "primary_department_id": P["dept_id"]}, headers=H(P["admin"]))
    assert r.status_code == 200, r.text
    eid = r.json()["id"]
    # duplicate -> 400
    assert client.post("/api/employees", json={"user_id": P["member_id"]}, headers=H(P["admin"])).status_code == 400
    # list enriches with user name/email
    emps = client.get("/api/employees", headers=H(P["admin"])).json()
    me = next(e for e in emps if e["id"] == eid)
    assert me["user_email"] == "p1member@opscore.app" and me["position"] == "Analyst"
    # patch
    assert client.patch(f"/api/employees/{eid}", json={"position": "Senior Analyst"}, headers=H(P["admin"])).json()["position"] == "Senior Analyst"
    # member lacks employee.view -> 403
    assert client.get("/api/employees", headers=H(P["member"])).status_code == 403
    assert client.delete(f"/api/employees/{eid}", headers=H(P["admin"])).status_code == 200


def test_department_members(client):
    add = client.post(f"/api/departments/{P['dept_id']}/members", json={"user_id": P["member_id"], "is_primary": True}, headers=H(P["admin"]))
    assert add.status_code == 200, add.text
    mem = client.get(f"/api/departments/{P['dept_id']}/members", headers=H(P["admin"])).json()
    assert any(m["user_id"] == P["member_id"] for m in mem)
    assert client.delete(f"/api/departments/{P['dept_id']}/members/{P['member_id']}", headers=H(P["admin"])).status_code == 200


def test_system_role_undeletable(client):
    roles = client.get("/api/rbac/roles", headers=H(P["admin"])).json()
    admin_role = next(r for r in roles if r["key"] == "administrator")
    assert client.delete(f"/api/rbac/roles/{admin_role['id']}", headers=H(P["admin"])).status_code == 400


# ---- Audit log ----
def test_audit_log(client):
    rows = client.get("/api/audit", headers=H(P["admin"])).json()
    actions = {r["action"] for r in rows}
    assert {"department.create", "role.create", "role.assign"} <= actions
    # member lacks audit.view
    assert client.get("/api/audit", headers=H(P["member"])).status_code == 403


# ---- Activity feed ----
def test_activity_feed_visibility(client):
    # admin action that emits an activity event
    proj = client.post("/api/projects", json={"name": "Activity Proj"}, headers=H(P["admin"]))
    assert proj.status_code == 200
    # admin (activity.view_all via is_admin) sees it
    admin_feed = client.get("/api/activity", headers=H(P["admin"])).json()
    assert any(e["verb"] == "project.created" and e["object_id"] == proj.json()["id"] for e in admin_feed)
    # member (no activity perms) sees only their own actions -> not the admin's event
    member_feed = client.get("/api/activity", headers=H(P["member"])).json()
    assert all(e["actor_id"] == P["member_id"] for e in member_feed)
    # grant member activity.view_all -> now they can see company events
    role = client.post("/api/rbac/roles", json={"key": "watcher", "name": "Watcher", "permissions": ["activity.view_all"]}, headers=H(P["admin"])).json()
    client.post("/api/rbac/assignments", json={"user_id": P["member_id"], "role_id": role["id"], "scope_type": "global"}, headers=H(P["admin"]))
    member_feed2 = client.get("/api/activity", headers=H(P["member"])).json()
    assert any(e["object_id"] == proj.json()["id"] for e in member_feed2)
