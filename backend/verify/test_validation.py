"""Phase 5.5 — Production validation: real end-to-end workflows against the actual app.

Traces actual code paths (no mocks of business logic) for the four canonical workflows,
dashboard correctness, RBAC scope, and cross-database referential integrity (the FK-orphan
fixes). Run on the real FastAPI app with the relational layer on SQLite + in-memory Mongo.
"""
import asyncio
import os
from datetime import datetime, timezone, timedelta, date

import pytest

V = {}


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
    V["admin"], V["admin_id"] = _register(client, "valadmin@opscore.app", "Val Admin")
    V["exec"], V["exec_id"] = _register(client, "valexec@opscore.app", "Val CEO")
    V["mgr"], V["mgr_id"] = _register(client, "valmgr@opscore.app", "Val Manager")
    V["emp"], V["emp_id"] = _register(client, "valemp@opscore.app", "Val Employee")
    for uid in (V["exec_id"], V["mgr_id"], V["emp_id"]):
        run(db.users.update_one({"id": uid}, {"$set": {"is_admin": False}}))

    V["sales"] = client.post("/api/departments", json={"name": "Val Sales"}, headers=H(V["admin"])).json()["id"]
    # Reporting chain: emp -> mgr -> exec (drives approvals + escalation)
    V["exec_emp"] = client.post("/api/employees", json={"user_id": V["exec_id"], "primary_department_id": V["sales"]},
                                headers=H(V["admin"])).json()["id"]
    V["mgr_emp"] = client.post("/api/employees", json={"user_id": V["mgr_id"], "primary_department_id": V["sales"],
                               "manager_id": V["exec_emp"]}, headers=H(V["admin"])).json()["id"]
    V["emp_emp"] = client.post("/api/employees", json={"user_id": V["emp_id"], "primary_department_id": V["sales"],
                               "manager_id": V["mgr_emp"]}, headers=H(V["admin"])).json()["id"]

    roles = {r["key"]: r["id"] for r in client.get("/api/rbac/roles", headers=H(V["admin"])).json()}
    def assign(uid, key, scope_type="global", scope_id=None):
        body = {"user_id": uid, "role_id": roles[key], "scope_type": scope_type}
        if scope_id:
            body["scope_id"] = scope_id
        assert client.post("/api/rbac/assignments", json=body, headers=H(V["admin"])).status_code == 200
    assign(V["exec_id"], "executive")
    assign(V["mgr_id"], "department_manager", "department", V["sales"])
    assign(V["emp_id"], "employee")

    # Approval template used by workflows 1 & 4 (manager-approves).
    V["tmpl"] = client.post("/api/approvals/templates", json={"key": "valdeal", "name": "Deal Approval",
                            "steps": [{"name": "Manager", "approver_type": "manager"}]}, headers=H(V["admin"])).json()["id"]
    yield


# ============ WORKFLOW 1 — Lead → Opportunity → Meeting → Task → Approval → Closed ============
def test_workflow1_full_sales_cycle(client, db):
    company = client.post("/api/crm/companies", json={"name": "Globex", "department_id": V["sales"]}, headers=H(V["emp"])).json()["id"]
    contact = client.post("/api/crm/contacts", json={"full_name": "Lin Wu", "company_id": company,
                          "department_id": V["sales"]}, headers=H(V["emp"])).json()["id"]
    lead = client.post("/api/crm/leads", json={"title": "Globex deal", "value": 75000, "probability": 50,
                       "company_id": company, "contact_id": contact, "department_id": V["sales"]}, headers=H(V["emp"])).json()["id"]
    # convert -> opportunity
    opp = client.post(f"/api/crm/leads/{lead}/convert", json={"name": "Globex Opp", "expected_revenue": 75000,
                      "expected_close_date": (date.today() + timedelta(days=20)).isoformat()}, headers=H(V["emp"])).json()["opportunity_id"]
    assert opp
    # meeting linked to the opportunity (manager schedules it)
    mtg = client.post(f"/api/crm/opportunity/{opp}/meetings", json={"title": "Globex pricing",
                      "attendee_ids": [V["emp_id"]]}, headers=H(V["mgr"]))
    assert mtg.status_code == 200, mtg.text
    # task linked to the opportunity
    task = client.post(f"/api/crm/opportunity/{opp}/tasks", json={"title": "Prepare quote"}, headers=H(V["emp"]))
    assert task.status_code == 200, task.text
    # approval (deal) -> routed to manager -> approved
    req = client.post("/api/approvals/requests", json={"template_id": V["tmpl"], "title": "Discount 10%",
                      "department_id": V["sales"]}, headers=H(V["emp"])).json()["id"]
    dec = client.post(f"/api/approvals/requests/{req}/decision", json={"decision": "approve"}, headers=H(V["mgr"]))
    assert dec.status_code == 200 and dec.json()["status"] == "approved"
    # close the opportunity (won)
    won = client.patch(f"/api/crm/opportunities/{opp}", json={"stage": "won"}, headers=H(V["emp"]))
    assert won.status_code == 200 and won.json()["status"] == "won"
    # the opportunity timeline reflects the whole journey
    tl = client.get(f"/api/crm/opportunity/{opp}/timeline", headers=H(V["emp"])).json()
    kinds = {e["kind"] for e in tl}
    assert {"meeting", "task", "stage_change"} <= kinds
    V["wf1"] = {"company": company, "contact": contact, "lead": lead, "opp": opp}


# ============ WORKFLOW 2 — Daily Update → Manager Review → Dept Report → Exec Dashboard ============
def test_workflow2_update_to_executive(client):
    du = client.post("/api/daily-updates", json={"today": "Closed Globex", "tomorrow": "Onboarding",
                     "blockers": "Need legal sign-off"}, headers=H(V["emp"]))
    assert du.status_code == 200, du.text
    # manager reviews the department's updates (department-scoped visibility)
    mgr_view = client.get("/api/daily-updates", headers=H(V["mgr"])).json()
    assert any(u["user_id"] == V["emp_id"] for u in mgr_view)
    # manager generates the weekly department report
    rep = client.post("/api/intelligence/reports/weekly-department", headers=H(V["mgr"]),
                      params={"department_id": V["sales"]})
    assert rep.status_code == 200 and rep.json()["summary"]
    # executive sees the company picture
    ed = client.get("/api/executive/dashboard", headers=H(V["exec"]))
    assert ed.status_code == 200 and any(d["id"] == V["sales"] for d in ed.json()["department_performance"])
    idash = client.get("/api/intelligence/dashboard", headers=H(V["exec"]))
    assert idash.status_code == 200 and isinstance(idash.json()["company_health_score"], int)


# ============ WORKFLOW 3 — Meeting → MOM → Action Items → Tasks → Completion ============
def test_workflow3_meeting_to_completion(client, db):
    mtg = client.post("/api/meetings", json={"title": "Sprint review", "department_id": V["sales"],
                      "attendee_ids": [V["emp_id"]]}, headers=H(V["mgr"])).json()["id"]
    client.put(f"/api/meetings/{mtg}/mom", json={"notes": "reviewed", "decisions": ["Ship v2"],
               "discussion_points": ["scope"]}, headers=H(V["mgr"]))
    ai = client.post(f"/api/meetings/{mtg}/action-items", json={"title": "Write release notes",
                     "owner_user_id": V["emp_id"], "due_in_days": 3}, headers=H(V["mgr"])).json()
    assert ai["task_id"]
    # employee completes the action item -> linked task completes -> meeting reflects done
    upd = client.patch(f"/api/action-items/{ai['id']}", json={"status": "done"}, headers=H(V["emp"]))
    assert upd.status_code == 200
    task = run(db.tasks.find_one({"id": ai["task_id"]}, {"_id": 0}))
    assert task["status"] == "done"
    items = client.get(f"/api/meetings/{mtg}/action-items", headers=H(V["mgr"])).json()
    assert any(i["id"] == ai["id"] and i["status"] == "done" for i in items)


# ============ WORKFLOW 4 — Approval → Escalation → Resolution ============
def test_workflow4_approval_escalation(client, db):
    req = client.post("/api/approvals/requests", json={"template_id": V["tmpl"], "title": "Budget sign-off",
                      "department_id": V["sales"]}, headers=H(V["emp"])).json()["id"]

    # Simulate time passing so the pending step breaches SLA, then run the real escalation engine.
    async def _esc():
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
        from app.shared.escalation import _escalate_approvals
        eng = create_async_engine(os.environ["DATABASE_URL"])
        Session = async_sessionmaker(eng, expire_on_commit=False)
        future = datetime.now(timezone.utc) + timedelta(hours=72)
        async with Session() as s:
            n = await _escalate_approvals(s, future)
        await eng.dispose()
        return n
    n = run(_esc())
    assert n >= 1
    esc = run(db.escalations.find_one({"entity_type": "approval", "entity_id": req}, {"_id": 0}))
    assert esc and esc["level"] >= 2
    # escalation notified up the chain (manager + manager's manager) via reminders
    rems = run(db.reminders.find({"entity_id": req, "source": "escalation"}, {"_id": 0}).to_list(10))
    recipients = {u for r in rems for u in r["recipient_ids"]}
    assert V["mgr_id"] in recipients and V["exec_id"] in recipients
    # resolution: manager approves -> closed
    dec = client.post(f"/api/approvals/requests/{req}/decision", json={"decision": "approve"}, headers=H(V["mgr"]))
    assert dec.status_code == 200 and dec.json()["status"] == "approved"


# ============ MODULE 5 — DASHBOARD VALIDATION (real data, no broken sections) ============
def test_dashboards_real_data(client):
    # Department dashboard (manager scope)
    dd = client.get(f"/api/departments/{V['sales']}/dashboard", headers=H(V["mgr"])).json()
    assert dd["headcount"] >= 3 and "tasks" in dd and "pending_approvals" in dd
    # CRM department + executive dashboards
    cdd = client.get(f"/api/crm/dashboards/department/{V['sales']}", headers=H(V["mgr"])).json()
    assert "opportunities" in cdd and "revenue_forecast" in cdd
    ced = client.get("/api/crm/dashboards/executive", headers=H(V["exec"])).json()
    assert ced["won_revenue"] >= 75000  # the Globex opp we closed
    # CRM intelligence (explainable)
    ci = client.get("/api/crm/intelligence", headers=H(V["exec"])).json()
    assert "forecast_insights" in ci and "risks" in ci


# ============ MODULE 6 — DATA CONSISTENCY (FK detach fixes) ============
def test_referential_integrity_on_delete(client, db):
    company = client.post("/api/crm/companies", json={"name": "DelCo", "department_id": V["sales"]}, headers=H(V["mgr"])).json()["id"]
    contact = client.post("/api/crm/contacts", json={"full_name": "Temp", "company_id": company,
                          "department_id": V["sales"]}, headers=H(V["mgr"])).json()["id"]
    lead = client.post("/api/crm/leads", json={"title": "DelLead", "company_id": company, "contact_id": contact,
                       "department_id": V["sales"]}, headers=H(V["mgr"])).json()["id"]
    opp = client.post("/api/crm/opportunities", json={"name": "DelOpp", "company_id": company, "contact_id": contact,
                      "department_id": V["sales"]}, headers=H(V["mgr"])).json()["id"]
    # delete the contact -> lead/opp contact_id detached, no error
    assert client.delete(f"/api/crm/contacts/{contact}", headers=H(V["mgr"])).status_code == 200
    assert client.get(f"/api/crm/leads/{lead}", headers=H(V["mgr"])).json()["contact_id"] is None
    assert client.get(f"/api/crm/opportunities/{opp}", headers=H(V["mgr"])).json()["contact_id"] is None
    # delete the company -> lead/opp company_id detached, no error
    assert client.delete(f"/api/crm/companies/{company}", headers=H(V["mgr"])).status_code == 200
    assert client.get(f"/api/crm/leads/{lead}", headers=H(V["mgr"])).json()["company_id"] is None
    assert client.get(f"/api/crm/opportunities/{opp}", headers=H(V["mgr"])).json()["company_id"] is None


# ============ MODULE 3 — RBAC SCOPE (negative paths from real roles) ============
def test_rbac_scope_enforcement(client):
    # employee cannot see audit, ops, or executive dashboards
    assert client.get("/api/audit", headers=H(V["emp"])).status_code == 403
    assert client.get("/api/ops/overview", headers=H(V["emp"])).status_code == 403
    assert client.get("/api/executive/dashboard", headers=H(V["emp"])).status_code == 403
    assert client.get("/api/intelligence/dashboard", headers=H(V["emp"])).status_code == 403
    # manager scoped to Sales cannot manage settings (admin-only)
    assert client.put("/api/settings/center/security", json={"values": {"session_hours": 9}}, headers=H(V["mgr"])).status_code == 403
    # unauthenticated is rejected everywhere
    assert client.get("/api/crm/companies").status_code in (401, 403)
    assert client.get("/api/executive/dashboard").status_code in (401, 403)
