"""Phase 2 verification: operational core.

Covers Daily Updates, Meetings + MOM, Action Items -> Tasks, Approval Workflows,
Department + CEO dashboards, Reporting foundation, and the Escalation engine.
Runs the real app with the relational layer on SQLite (stand-in for Postgres) and an
in-memory Mongo, exercising RBAC enforcement (incl. department-scoped roles), the
Activity Feed, and the Audit Log end to end.
"""
import asyncio
import os
from datetime import datetime, timezone, timedelta, date

import pytest

P = {}


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


def run(coro):
    return asyncio.run(coro)


def _register(client, email, name):
    r = client.post("/api/auth/register", json={"email": email, "password": "password1", "name": name})
    assert r.status_code == 200, r.text
    return r.json()["token"], r.json()["user"]["id"]


@pytest.fixture(scope="module", autouse=True)
def setup(client, db):
    # Admin stays admin; everyone else is demoted to a normal account driven purely by roles.
    P["admin"], P["admin_id"] = _register(client, "p2admin@opscore.app", "P2 Admin")
    P["mgr"], P["mgr_id"] = _register(client, "p2mgr@opscore.app", "P2 Manager")
    P["emp"], P["emp_id"] = _register(client, "p2emp@opscore.app", "P2 Employee")
    P["exec"], P["exec_id"] = _register(client, "p2exec@opscore.app", "P2 Exec")
    P["nobody"], P["nobody_id"] = _register(client, "p2nobody@opscore.app", "P2 Nobody")
    for uid in (P["mgr_id"], P["emp_id"], P["exec_id"], P["nobody_id"]):
        run(db.users.update_one({"id": uid}, {"$set": {"is_admin": False}}))

    # Departments
    P["dept"] = client.post("/api/departments", json={"name": "Engineering"}, headers=H(P["admin"])).json()["id"]
    P["dept2"] = client.post("/api/departments", json={"name": "Operations"}, headers=H(P["admin"])).json()["id"]

    # Employees + reporting line: emp reports to mgr, both in Engineering.
    P["mgr_emp"] = client.post("/api/employees", json={"user_id": P["mgr_id"], "position": "Eng Manager",
                               "primary_department_id": P["dept"]}, headers=H(P["admin"])).json()["id"]
    P["emp_emp"] = client.post("/api/employees", json={"user_id": P["emp_id"], "position": "Engineer",
                               "primary_department_id": P["dept"], "manager_id": P["mgr_emp"]}, headers=H(P["admin"])).json()["id"]

    # Roles + assignments
    roles = {r["key"]: r["id"] for r in client.get("/api/rbac/roles", headers=H(P["admin"])).json()}
    def assign(uid, role_key, scope_type="global", scope_id=None):
        body = {"user_id": uid, "role_id": roles[role_key], "scope_type": scope_type}
        if scope_id:
            body["scope_id"] = scope_id
        r = client.post("/api/rbac/assignments", json=body, headers=H(P["admin"]))
        assert r.status_code == 200, r.text
    assign(P["emp_id"], "employee")
    assign(P["mgr_id"], "employee")
    assign(P["mgr_id"], "department_manager", "department", P["dept"])
    assign(P["exec_id"], "executive")
    yield


# ============ RBAC catalog ============
def test_phase2_permissions_seeded(client):
    keys = {p["key"] for p in client.get("/api/rbac/permissions", headers=H(P["admin"])).json()}
    assert {"daily_update.submit", "daily_update.view_team", "daily_update.view_department", "daily_update.view_all",
            "meeting.create", "meeting.edit", "meeting.cancel", "meeting.view", "meeting.mom.edit", "meeting.mom.view",
            "approval.create", "approval.approve", "approval.view", "approval.manage"} <= keys


# ============ MODULE 1 — DAILY UPDATES ============
def test_daily_update_submit_and_one_per_day(client):
    r = client.post("/api/daily-updates", json={"today": "Shipped auth", "tomorrow": "Reviews", "blockers": "none"},
                    headers=H(P["emp"]))
    assert r.status_code == 200, r.text
    P["du_id"] = r.json()["id"]
    assert r.json()["department_id"] == P["dept"]  # denormalised from employee profile
    # second submit same day -> rejected
    assert client.post("/api/daily-updates", json={"today": "again"}, headers=H(P["emp"])).status_code == 400


def test_daily_update_requires_permission(client):
    assert client.post("/api/daily-updates", json={"today": "x"}, headers=H(P["nobody"])).status_code == 403


def test_daily_update_same_day_edit(client):
    r = client.patch(f"/api/daily-updates/{P['du_id']}", json={"blockers": "waiting on infra"}, headers=H(P["emp"]))
    assert r.status_code == 200 and r.json()["blockers"] == "waiting on infra"
    # a different user cannot edit it
    assert client.patch(f"/api/daily-updates/{P['du_id']}", json={"today": "hack"}, headers=H(P["mgr"])).status_code == 403


def test_daily_update_visibility(client):
    # employee sees only their own
    own = client.get("/api/daily-updates", headers=H(P["emp"])).json()
    assert all(u["user_id"] == P["emp_id"] for u in own) and any(u["id"] == P["du_id"] for u in own)
    # department-scoped manager sees the department's updates (scoped RBAC, not global)
    mgr_view = client.get("/api/daily-updates", headers=H(P["mgr"])).json()
    assert any(u["id"] == P["du_id"] for u in mgr_view)
    # executive (view_all) sees it too
    exec_view = client.get("/api/daily-updates", headers=H(P["exec"])).json()
    assert any(u["id"] == P["du_id"] for u in exec_view)
    # nobody sees nothing but their own (empty)
    assert client.get("/api/daily-updates", headers=H(P["nobody"])).json() == []


def test_daily_update_activity_and_audit(client):
    feed = client.get("/api/activity", headers=H(P["admin"])).json()
    assert any(e["verb"] == "daily_update.submitted" and e["object_id"] == P["du_id"] for e in feed)
    audit = client.get("/api/audit", headers=H(P["admin"]), params={"action": "daily_update.submit"}).json()
    assert any(a["entity_id"] == P["du_id"] for a in audit)


# ============ MODULE 2 — MEETINGS ============
def test_meeting_create_requires_scoped_permission(client):
    # employee lacks meeting.create -> 403
    assert client.post("/api/meetings", json={"title": "X", "department_id": P["dept"]}, headers=H(P["emp"])).status_code == 403
    # department-scoped manager can create in their department
    r = client.post("/api/meetings", json={"title": "Weekly Fraud Review", "department_id": P["dept"],
                    "meeting_at": "2026-06-10T10:00:00+00:00", "agenda": "Review feeds", "attendee_ids": [P["emp_id"]]},
                    headers=H(P["mgr"]))
    assert r.status_code == 200, r.text
    P["mtg"] = r.json()["id"]
    # manager cannot create in a department they don't manage
    assert client.post("/api/meetings", json={"title": "Nope", "department_id": P["dept2"]}, headers=H(P["mgr"])).status_code == 403


def test_meeting_view_and_attendees(client):
    # attendee (employee) can view the meeting detail
    r = client.get(f"/api/meetings/{P['mtg']}", headers=H(P["emp"]))
    assert r.status_code == 200 and any(a["user_id"] == P["emp_id"] for a in r.json()["attendees"])
    # add + list attendees
    client.post(f"/api/meetings/{P['mtg']}/attendees", json={"user_id": P["exec_id"]}, headers=H(P["mgr"]))
    att = client.get(f"/api/meetings/{P['mtg']}/attendees", headers=H(P["mgr"])).json()
    assert {a["user_id"] for a in att} >= {P["emp_id"], P["exec_id"]}


def test_meeting_activity_emitted(client):
    feed = client.get("/api/activity", headers=H(P["admin"])).json()
    assert any(e["verb"] == "meeting.created" and e["object_id"] == P["mtg"] for e in feed)


# ============ MODULE 3 — MOM ============
def test_mom_edit_and_view(client):
    # employee can view MOM but not edit it
    assert client.put(f"/api/meetings/{P['mtg']}/mom", json={"notes": "x"}, headers=H(P["emp"])).status_code == 403
    r = client.put(f"/api/meetings/{P['mtg']}/mom", json={
        "notes": "Discussed phishing feeds", "decisions": ["Adopt OpenPhish"],
        "discussion_points": ["Feed latency", "Coverage gaps"]}, headers=H(P["mgr"]))
    assert r.status_code == 200, r.text
    got = client.get(f"/api/meetings/{P['mtg']}/mom", headers=H(P["emp"])).json()
    assert got["decisions"] == ["Adopt OpenPhish"] and len(got["discussion_points"]) == 2


# ============ MODULE 4 — ACTION ITEMS -> TASKS ============
def test_action_item_creates_linked_task(client, db):
    r = client.post(f"/api/meetings/{P['mtg']}/action-items", json={
        "title": "Review OpenPhish Feed", "owner_user_id": P["emp_id"], "due_in_days": 7}, headers=H(P["mgr"]))
    assert r.status_code == 200, r.text
    ai = r.json()
    P["ai"] = ai["id"]
    P["ai_task"] = ai["task_id"]
    assert ai["task_id"] and ai["status"] == "open"
    # the spawned task exists, is owned by the action owner, and links back to the meeting
    task = run(db.tasks.find_one({"id": P["ai_task"]}, {"_id": 0}))
    assert task and task["source_meeting_id"] == P["mtg"] and task["assignee_id"] == P["emp_id"]
    assert task["action_item_id"] == P["ai"]
    # a reminder was queued for the owner via the existing reminder engine
    rem = run(db.reminders.find_one({"entity_type": "task", "entity_id": P["ai_task"]}, {"_id": 0}))
    assert rem and P["emp_id"] in rem["recipient_ids"]


def test_action_item_status_syncs_with_task(client, db):
    # the action owner completes the action item -> linked task is marked done
    r = client.patch(f"/api/action-items/{P['ai']}", json={"status": "done"}, headers=H(P["emp"]))
    assert r.status_code == 200, r.text
    task = run(db.tasks.find_one({"id": P["ai_task"]}, {"_id": 0}))
    assert task["status"] == "done"
    # meeting view reflects the live (done) status
    items = client.get(f"/api/meetings/{P['mtg']}/action-items", headers=H(P["mgr"])).json()
    assert any(i["id"] == P["ai"] and i["status"] == "done" for i in items)


def test_action_item_activity(client):
    feed = client.get("/api/activity", headers=H(P["admin"])).json()
    assert any(e["verb"] == "action_item.created" and e["object_id"] == P["ai"] for e in feed)


# ============ MODULE 5 — APPROVAL WORKFLOWS ============
def test_create_template_requires_manage(client):
    # only approval.manage (admin) can author templates
    body = {"key": "leave", "name": "Leave Request", "category": "leave", "steps": [
        {"name": "Manager", "approver_type": "manager"},
        {"name": "Executive", "approver_type": "role", "approver_value": "executive"}]}
    assert client.post("/api/approvals/templates", json=body, headers=H(P["emp"])).status_code == 403
    r = client.post("/api/approvals/templates", json=body, headers=H(P["admin"]))
    assert r.status_code == 200, r.text
    P["tmpl"] = r.json()["id"]
    assert len(r.json()["steps"]) == 2


def test_submit_request_resolves_manager(client, db):
    r = client.post("/api/approvals/requests", json={"template_id": P["tmpl"], "title": "Annual leave",
                    "department_id": P["dept"], "form_data": {"days": 3}}, headers=H(P["emp"]))
    assert r.status_code == 200, r.text
    req = r.json()
    P["req"] = req["id"]
    active = next(s for s in req["steps"] if s["step_order"] == req["current_step"])
    assert active["approver_user_id"] == P["mgr_id"]  # resolved from the reporting chain
    # an approval reminder was enqueued for the manager
    rem = run(db.reminders.find_one({"entity_type": "approval", "entity_id": P["req"]}, {"_id": 0}))
    assert rem and P["mgr_id"] in rem["recipient_ids"]


def test_only_assigned_approver_can_decide(client):
    # requester cannot approve their own step
    assert client.post(f"/api/approvals/requests/{P['req']}/decision", json={"decision": "approve"},
                       headers=H(P["emp"])).status_code == 403
    # exec is not the step-1 approver yet
    assert client.post(f"/api/approvals/requests/{P['req']}/decision", json={"decision": "approve"},
                       headers=H(P["exec"])).status_code == 403


def test_multi_step_approval_flow(client):
    # step 1: manager approves -> advances to the role-based step
    r1 = client.post(f"/api/approvals/requests/{P['req']}/decision", json={"decision": "approve", "comment": "ok"},
                     headers=H(P["mgr"]))
    assert r1.status_code == 200 and r1.json()["status"] == "pending" and r1.json()["current_step"] == 2
    # step 2: any holder of the 'executive' role can decide
    r2 = client.post(f"/api/approvals/requests/{P['req']}/decision", json={"decision": "approve"}, headers=H(P["exec"]))
    assert r2.status_code == 200 and r2.json()["status"] == "approved"


def test_reject_path_and_cancel(client):
    # new request -> manager rejects
    rid = client.post("/api/approvals/requests", json={"template_id": P["tmpl"], "title": "Leave 2",
                      "department_id": P["dept"]}, headers=H(P["emp"])).json()["id"]
    rej = client.post(f"/api/approvals/requests/{rid}/decision", json={"decision": "reject", "comment": "no"},
                      headers=H(P["mgr"]))
    assert rej.status_code == 200 and rej.json()["status"] == "rejected"
    # cancel path: requester cancels a fresh pending request
    rid2 = client.post("/api/approvals/requests", json={"template_id": P["tmpl"], "title": "Leave 3",
                       "department_id": P["dept"]}, headers=H(P["emp"])).json()["id"]
    assert client.post(f"/api/approvals/requests/{rid2}/cancel", headers=H(P["emp"])).status_code == 200


def test_approval_audit_and_activity(client):
    actions = {a["action"] for a in client.get("/api/audit", headers=H(P["admin"])).json()}
    assert {"approval.submit", "approval.approve", "approval.reject", "approval_template.create"} <= actions
    feed_verbs = {e["verb"] for e in client.get("/api/activity", headers=H(P["admin"])).json()}
    assert {"approval.submitted", "approval.approved", "approval.rejected"} <= feed_verbs


def test_approval_listing_scopes(client):
    # requester sees their own
    mine = client.get("/api/approvals/requests", headers=H(P["emp"]), params={"mine": "requested"}).json()
    assert all(r["requester_id"] == P["emp_id"] for r in mine) and mine
    # executive (approval.view) sees company-wide
    all_reqs = client.get("/api/approvals/requests", headers=H(P["exec"])).json()
    assert any(r["id"] == P["req"] for r in all_reqs)


# ============ MODULE 6 — DEPARTMENT DASHBOARD ============
def test_department_dashboard_scoped(client):
    # department-scoped manager can view their department dashboard
    r = client.get(f"/api/departments/{P['dept']}/dashboard", headers=H(P["mgr"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert "tasks" in body and "pending_approvals" in body and body["headcount"] >= 2
    # manager cannot view another department's dashboard
    assert client.get(f"/api/departments/{P['dept2']}/dashboard", headers=H(P["mgr"])).status_code == 403
    # plain employee cannot view the dashboard
    assert client.get(f"/api/departments/{P['dept']}/dashboard", headers=H(P["emp"])).status_code == 403


# ============ MODULE 7 — CEO EXECUTIVE DASHBOARD ============
def test_executive_dashboard(client):
    assert client.get("/api/executive/dashboard", headers=H(P["emp"])).status_code == 403
    r = client.get("/api/executive/dashboard", headers=H(P["exec"]))
    assert r.status_code == 200, r.text
    body = r.json()
    for key in ("company_health", "department_performance", "upcoming_meetings", "pending_approvals", "risks", "recent_activity"):
        assert key in body
    assert any(d["id"] == P["dept"] for d in body["department_performance"])


# ============ MODULE 9 — REPORTING FOUNDATION ============
def test_reporting_generate_and_scope(client):
    today = date.today().isoformat()
    start = (date.today() - timedelta(days=7)).isoformat()
    # executive generates a company/executive report
    r = client.post("/api/reports/generate", json={"report_type": "executive",
                    "period_start": start, "period_end": today}, headers=H(P["exec"]))
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["summary"] == "" and "tasks" in rep["data"] and "departments" in rep["data"]
    P["report"] = rep["id"]
    # department-scoped manager can generate their department report
    rd = client.post("/api/reports/generate", json={"report_type": "weekly_department",
                     "department_id": P["dept"], "period_start": start, "period_end": today}, headers=H(P["mgr"]))
    assert rd.status_code == 200, rd.text
    # ...but not another department's
    assert client.post("/api/reports/generate", json={"report_type": "weekly_department",
                       "department_id": P["dept2"], "period_start": start, "period_end": today},
                       headers=H(P["mgr"])).status_code == 403
    # employee cannot generate company reports
    assert client.post("/api/reports/generate", json={"report_type": "executive",
                       "period_start": start, "period_end": today}, headers=H(P["emp"])).status_code == 403


def test_reporting_read(client):
    got = client.get(f"/api/reports/{P['report']}", headers=H(P["exec"]))
    assert got.status_code == 200 and got.json()["report_type"] == "executive"
    listed = client.get("/api/reports", headers=H(P["exec"])).json()
    assert any(r["id"] == P["report"] for r in listed)


# ============ MODULE 8 — ESCALATIONS ============
def test_escalation_climbs_reporting_chain(client, db):
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from app.shared.escalation import _escalate_tasks
    from app.core.utils import new_id, now_iso

    # An overdue task owned by the employee (48h past due -> should reach L2 = manager).
    tid = new_id()
    overdue_due = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    run(db.tasks.insert_one({
        "id": tid, "title": "Overdue thing", "status": "todo", "owner_id": P["emp_id"],
        "assignee_id": P["emp_id"], "due_date": overdue_due, "created_at": now_iso(),
    }))

    async def _go():
        eng = create_async_engine(os.environ["DATABASE_URL"])
        Session = async_sessionmaker(eng, expire_on_commit=False)
        async with Session() as s:
            n = await _escalate_tasks(s, datetime.now(timezone.utc))
        await eng.dispose()
        return n

    n = run(_go())
    assert n >= 1
    # escalation level recorded at >= 2
    esc = run(db.escalations.find_one({"entity_type": "task", "entity_id": tid}, {"_id": 0}))
    assert esc and esc["level"] >= 2
    # reminders were enqueued to the owner (L1) and the manager (L2) via the reminder engine
    rems = run(db.reminders.find({"entity_id": tid, "source": "escalation"}, {"_id": 0}).to_list(10))
    recipients = {uid for r in rems for uid in r["recipient_ids"]}
    assert P["emp_id"] in recipients and P["mgr_id"] in recipients
    # an escalation activity event was emitted
    feed = run(db.activity_feed.find({"verb": "task.escalated", "object_id": tid}, {"_id": 0}).to_list(10))
    assert feed and feed[0]["metadata"]["level"] >= 1
