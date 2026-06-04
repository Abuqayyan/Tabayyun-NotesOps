"""Onboarding flow verification: the exact API chain the Organization → Employees
screen drives — list users, invite a new account, create an employee profile, and
assign a role. Guards the GET /users endpoint and the unified add-employee flow.
"""
import asyncio

import pytest

O = {}


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(scope="module", autouse=True)
def setup(client, db):
    r = client.post("/api/auth/register", json={"email": "onbadmin@opscore.app", "password": "adminpass1", "name": "Onb Admin"})
    O["admin"] = r.json()["token"]
    O["admin_id"] = r.json()["user"]["id"]
    # a non-admin member (register then demote)
    r2 = client.post("/api/auth/register", json={"email": "onbmember@opscore.app", "password": "memberpass1", "name": "Onb Member"})
    O["member"] = r2.json()["token"]
    O["member_id"] = r2.json()["user"]["id"]
    run(db.users.update_one({"id": O["member_id"]}, {"$set": {"is_admin": False}}))
    yield


def test_users_directory_lists_accounts(client):
    rows = client.get("/api/users", headers=H(O["admin"]))
    assert rows.status_code == 200, rows.text
    emails = {u["email"] for u in rows.json()}
    assert {"onbadmin@opscore.app", "onbmember@opscore.app"} <= emails
    # never leaks password hashes
    assert all("password_hash" not in u for u in rows.json())


def test_users_directory_search(client):
    rows = client.get("/api/users", params={"q": "onbmember"}, headers=H(O["admin"])).json()
    assert len(rows) == 1 and rows[0]["email"] == "onbmember@opscore.app"


def test_unified_add_employee_flow(client):
    # department to scope the role to
    dept = client.post("/api/departments", json={"name": "Onboarding Dept"}, headers=H(O["admin"]))
    assert dept.status_code == 200, dept.text
    O["dept_id"] = dept.json()["id"]

    # 1) invite a brand-new account (admin-only) → returns the new user_id
    inv = client.post("/api/team/invite", json={"email": "newhire@opscore.app", "name": "New Hire"}, headers=H(O["admin"]))
    assert inv.status_code == 200, inv.text
    new_user_id = inv.json()["user_id"]
    assert new_user_id
    assert inv.json()["existing_user"] is False

    # 2) employee profile for that user
    emp = client.post("/api/employees", json={
        "user_id": new_user_id, "position": "Analyst", "primary_department_id": O["dept_id"],
    }, headers=H(O["admin"]))
    assert emp.status_code == 200, emp.text

    # 3) assign the employee role scoped to the department
    roles = client.get("/api/rbac/roles", headers=H(O["admin"])).json()
    emp_role = next(r for r in roles if r["key"] == "employee")
    assign = client.post("/api/rbac/assignments", json={
        "user_id": new_user_id, "role_id": emp_role["id"], "scope_type": "department", "scope_id": O["dept_id"],
    }, headers=H(O["admin"]))
    assert assign.status_code == 200, assign.text

    # 4) employees list shows the new hire enriched with name/email
    emps = client.get("/api/employees", headers=H(O["admin"])).json()
    hire = next((e for e in emps if e["user_id"] == new_user_id), None)
    assert hire is not None
    assert hire["user_name"] == "New Hire" and hire["user_email"] == "newhire@opscore.app"
    assert hire["primary_department_id"] == O["dept_id"]


def test_invite_requires_admin(client):
    # non-admin cannot invite (would-be account creation is blocked)
    r = client.post("/api/team/invite", json={"email": "x@opscore.app"}, headers=H(O["member"]))
    assert r.status_code == 403
