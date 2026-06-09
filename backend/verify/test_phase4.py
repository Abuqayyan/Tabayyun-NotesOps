"""Phase 4 verification: CRM as a deeply-integrated Company-OS module.

Covers Companies, Contacts, Leads (stages/history/conversion), Opportunities (pipeline/
forecast/history), the unified client timeline, meeting + task linking, CRM dashboards,
CRM intelligence, the client-portal schema foundation, and RBAC enforcement (incl.
department-scoped roles) + Activity Feed + Audit Log integration.
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
    P["admin"], P["admin_id"] = _register(client, "p4admin@opscore.app", "P4 Admin")
    P["mgr"], P["mgr_id"] = _register(client, "p4mgr@opscore.app", "P4 Manager")
    P["emp"], P["emp_id"] = _register(client, "p4emp@opscore.app", "P4 Employee")
    P["exec"], P["exec_id"] = _register(client, "p4exec@opscore.app", "P4 Exec")
    P["nobody"], P["nobody_id"] = _register(client, "p4nobody@opscore.app", "P4 Nobody")
    for uid in (P["mgr_id"], P["emp_id"], P["exec_id"], P["nobody_id"]):
        run(db.users.update_one({"id": uid}, {"$set": {"is_admin": False}}))

    P["sales"] = client.post("/api/departments", json={"name": "P4 Sales"}, headers=H(P["admin"])).json()["id"]
    P["ops"] = client.post("/api/departments", json={"name": "P4 Ops"}, headers=H(P["admin"])).json()["id"]
    P["mgr_emp"] = client.post("/api/employees", json={"user_id": P["mgr_id"], "primary_department_id": P["sales"]},
                               headers=H(P["admin"])).json()["id"]
    client.post("/api/employees", json={"user_id": P["emp_id"], "primary_department_id": P["sales"],
                "manager_id": P["mgr_emp"]}, headers=H(P["admin"]))

    roles = {r["key"]: r["id"] for r in client.get("/api/rbac/roles", headers=H(P["admin"])).json()}
    def assign(uid, key, scope_type="global", scope_id=None):
        body = {"user_id": uid, "role_id": roles[key], "scope_type": scope_type}
        if scope_id:
            body["scope_id"] = scope_id
        assert client.post("/api/rbac/assignments", json=body, headers=H(P["admin"])).status_code == 200
    assign(P["emp_id"], "employee")          # CRM view+create+edit (no delete), GLOBAL
    # mgr is PURELY department-scoped to Sales (no global role) so scoping is testable.
    assign(P["mgr_id"], "department_manager", "department", P["sales"])  # CRM full within Sales
    assign(P["exec_id"], "executive")        # CRM view only + company.dashboard.view
    yield


# ============ MODULE 1 — COMPANIES ============
def test_company_crud_and_permissions(client):
    assert client.post("/api/crm/companies", json={"name": "X"}, headers=H(P["nobody"])).status_code == 403
    r = client.post("/api/crm/companies", json={"name": "Acme Corp", "industry": "Fintech", "country": "UAE",
                    "city": "Dubai", "department_id": P["sales"], "tags": ["vip"]}, headers=H(P["emp"]))
    assert r.status_code == 200, r.text
    P["company"] = r.json()["id"]
    assert r.json()["owner_id"] == P["emp_id"]
    # visibility: owner + exec (global view) see it
    assert any(c["id"] == P["company"] for c in client.get("/api/crm/companies", headers=H(P["emp"])).json())
    assert any(c["id"] == P["company"] for c in client.get("/api/crm/companies", headers=H(P["exec"])).json())
    assert client.get("/api/crm/companies", headers=H(P["nobody"])).status_code == 403
    # search + filter
    assert any(c["id"] == P["company"] for c in client.get("/api/crm/companies", headers=H(P["emp"]), params={"q": "Acme"}).json())
    assert all(c["country"] == "UAE" for c in client.get("/api/crm/companies", headers=H(P["emp"]), params={"q": "Acme"}).json())


def test_company_edit_delete_scope(client):
    # employee can edit (owner) but cannot delete (no crm.company.delete)
    assert client.patch(f"/api/crm/companies/{P['company']}", json={"status": "active"}, headers=H(P["emp"])).json()["status"] == "active"
    assert client.delete(f"/api/crm/companies/{P['company']}", headers=H(P["emp"])).status_code == 403
    # a throwaway company the Sales manager can delete (department-scoped crm.company.delete)
    cid = client.post("/api/crm/companies", json={"name": "Temp", "department_id": P["sales"]}, headers=H(P["mgr"])).json()["id"]
    assert client.delete(f"/api/crm/companies/{cid}", headers=H(P["mgr"])).status_code == 200


# ============ MODULE 2 — CONTACTS ============
def test_contact_crud(client):
    r = client.post("/api/crm/contacts", json={"full_name": "Sara Ali", "email": "sara@acme.com", "position": "CTO",
                    "company_id": P["company"], "department_id": P["sales"]}, headers=H(P["emp"]))
    assert r.status_code == 200, r.text
    P["contact"] = r.json()["id"]
    assert any(c["id"] == P["contact"] for c in client.get("/api/crm/contacts", headers=H(P["emp"]), params={"q": "Sara"}).json())
    assert client.get(f"/api/crm/contacts/{P['contact']}", headers=H(P["exec"])).status_code == 200
    assert client.post("/api/crm/contacts", json={"full_name": "Y"}, headers=H(P["nobody"])).status_code == 403


# ============ MODULE 3 — LEADS ============
def test_lead_pipeline_and_history(client):
    r = client.post("/api/crm/leads", json={"title": "Acme expansion", "source": "referral", "value": 50000,
                    "probability": 40, "company_id": P["company"], "contact_id": P["contact"],
                    "department_id": P["sales"]}, headers=H(P["emp"]))
    assert r.status_code == 200, r.text
    P["lead"] = r.json()["id"]
    assert r.json()["stage"] == "new" and r.json()["status"] == "open"
    # move stage -> stage history records the transition
    u = client.patch(f"/api/crm/leads/{P['lead']}", json={"stage": "contacted", "stage_note": "called"}, headers=H(P["emp"]))
    assert u.status_code == 200 and u.json()["stage"] == "contacted"
    hist = client.get(f"/api/crm/leads/{P['lead']}/history", headers=H(P["emp"])).json()
    assert [h["to_stage"] for h in hist] == ["new", "contacted"]
    assert client.post("/api/crm/leads", json={"title": "z"}, headers=H(P["nobody"])).status_code == 403


def test_lead_conversion(client):
    r = client.post(f"/api/crm/leads/{P['lead']}/convert", json={"name": "Acme Deal", "expected_revenue": 60000,
                    "expected_close_date": (date.today() + timedelta(days=30)).isoformat()}, headers=H(P["emp"]))
    assert r.status_code == 200, r.text
    assert r.json()["lead"]["status"] == "won" and r.json()["lead"]["converted_opportunity_id"]
    P["conv_opp"] = r.json()["opportunity_id"]
    # double convert rejected
    assert client.post(f"/api/crm/leads/{P['lead']}/convert", json={}, headers=H(P["emp"])).status_code == 400


# ============ MODULE 4 — OPPORTUNITIES ============
def test_opportunity_pipeline_forecast(client):
    r = client.post("/api/crm/opportunities", json={"name": "Big Deal", "expected_revenue": 100000, "probability": 50,
                    "stage": "proposal", "company_id": P["company"], "department_id": P["sales"]}, headers=H(P["emp"]))
    assert r.status_code == 200, r.text
    P["opp"] = r.json()["id"]
    assert r.json()["weighted_value"] == 50000.0
    # pipeline board groups by stage
    board = client.get("/api/crm/pipeline", headers=H(P["emp"])).json()["board"]
    assert board["proposal"]["count"] >= 1 and board["proposal"]["value"] >= 100000
    # forecast
    fc = client.get("/api/crm/forecast", headers=H(P["emp"])).json()
    assert fc["total_pipeline"] >= 100000 and fc["weighted_forecast"] >= 50000
    # stage change -> won updates status + records history
    w = client.patch(f"/api/crm/opportunities/{P['opp']}", json={"stage": "won"}, headers=H(P["emp"]))
    assert w.status_code == 200 and w.json()["status"] == "won"
    hist = client.get(f"/api/crm/opportunities/{P['opp']}/history", headers=H(P["emp"])).json()
    assert hist[-1]["to_stage"] == "won"


# ============ MODULES 5/6/7 — TIMELINE + LINKING ============
def test_client_activity_logging(client):
    a = client.post(f"/api/crm/company/{P['company']}/activities", json={"activity_type": "call",
                    "title": "Intro call", "body": "discussed scope"}, headers=H(P["emp"]))
    assert a.status_code == 200, a.text
    tl = client.get(f"/api/crm/company/{P['company']}/timeline", headers=H(P["emp"])).json()
    assert any(e["kind"] == "activity" and e["title"] == "Intro call" for e in tl)


def test_crm_task_linking(client, db):
    r = client.post(f"/api/crm/opportunity/{P['opp']}/tasks", json={"title": "Send proposal",
                    "assignee_id": P["emp_id"]}, headers=H(P["emp"]))
    assert r.status_code == 200, r.text
    tid = r.json()["task_id"]
    task = run(db.tasks.find_one({"id": tid}, {"_id": 0}))
    assert task["crm_entity_type"] == "opportunity" and task["crm_entity_id"] == P["opp"]
    tl = client.get(f"/api/crm/opportunity/{P['opp']}/timeline", headers=H(P["emp"])).json()
    assert any(e["kind"] == "task" and e["ref"]["id"] == tid for e in tl)


def test_crm_meeting_linking(client):
    r = client.post(f"/api/crm/company/{P['company']}/meetings", json={"title": "Acme QBR",
                    "attendee_ids": [P["emp_id"]]}, headers=H(P["mgr"]))
    assert r.status_code == 200, r.text
    mid = r.json()["meeting_id"]
    P["crm_meeting"] = mid
    tl = client.get(f"/api/crm/company/{P['company']}/timeline", headers=H(P["emp"])).json()
    assert any(e["kind"] == "meeting" and e["ref"]["id"] == mid for e in tl)
    # generic link of the same meeting to the lead, then unlink
    ln = client.post(f"/api/crm/lead/{P['lead']}/link", json={"target_type": "meeting", "target_id": mid}, headers=H(P["emp"]))
    assert ln.status_code == 200
    assert client.delete(f"/api/crm/links/{ln.json()['id']}", headers=H(P["emp"])).status_code == 200


def test_timeline_includes_stage_history(client):
    tl = client.get(f"/api/crm/lead/{P['lead']}/timeline", headers=H(P["emp"])).json()
    assert any(e["kind"] == "stage_change" for e in tl)


# ============ MODULE 8 — CRM DASHBOARDS ============
def test_department_crm_dashboard(client):
    r = client.get(f"/api/crm/dashboards/department/{P['sales']}", headers=H(P["mgr"]))
    assert r.status_code == 200, r.text
    b = r.json()
    assert "leads" in b and "opportunities" in b and "revenue_forecast" in b and "conversion_rates" in b
    # manager cannot view another department's CRM dashboard
    assert client.get(f"/api/crm/dashboards/department/{P['ops']}", headers=H(P["mgr"])).status_code == 403
    assert client.get(f"/api/crm/dashboards/department/{P['sales']}", headers=H(P["nobody"])).status_code == 403


def test_executive_crm_dashboard(client):
    assert client.get("/api/crm/dashboards/executive", headers=H(P["emp"])).status_code == 403
    r = client.get("/api/crm/dashboards/executive", headers=H(P["exec"]))
    assert r.status_code == 200, r.text
    b = r.json()
    for k in ("total_pipeline", "won_revenue", "lost_revenue", "conversion_trends", "top_opportunities", "team_performance"):
        assert k in b
    assert b["won_revenue"] >= 100000  # the won 'Big Deal'


# ============ MODULE 9 — CRM INTELLIGENCE ============
def test_crm_intelligence(client):
    # create explainable risk signals: an overdue-close deal + a high-value low-probability lead
    client.post("/api/crm/opportunities", json={"name": "Stale Deal", "expected_revenue": 40000, "probability": 20,
                "stage": "negotiation", "expected_close_date": (date.today() - timedelta(days=10)).isoformat(),
                "department_id": P["sales"]}, headers=H(P["emp"]))
    client.post("/api/crm/leads", json={"title": "Whale", "value": 80000, "probability": 10,
                "department_id": P["sales"]}, headers=H(P["emp"]))
    # employee lacks company-scope intelligence
    assert client.get("/api/crm/intelligence", headers=H(P["emp"])).status_code == 403
    r = client.get("/api/crm/intelligence", headers=H(P["exec"]))
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["risks"] and "forecast_insights" in b and "follow_up_recommendations" in b and b["narrative"]
    types = {x["type"] for x in b["risks"]}
    assert "opportunity_risk" in types or "lead_risk" in types
    for risk in b["risks"]:
        assert "source" in risk and risk["level"] in ("low", "medium", "high", "critical")
    # department-scoped intelligence is allowed for the scoped manager / employee with crm view
    assert client.get("/api/crm/intelligence", headers=H(P["mgr"]), params={"department_id": P["sales"]}).status_code == 200


# ============ INTEGRATION — ACTIVITY FEED + AUDIT ============
def test_activity_and_audit_integration(client):
    verbs = {e["verb"] for e in client.get("/api/activity", headers=H(P["admin"])).json()}
    assert {"crm.company.created", "crm.lead.created", "crm.opportunity.created", "crm.lead.converted"} <= verbs
    actions = {a["action"] for a in client.get("/api/audit", headers=H(P["admin"])).json()}
    assert {"crm.company.create", "crm.lead.create", "crm.lead.convert", "crm.opportunity.create"} <= actions


# ============ MODULE 10 — CLIENT PORTAL FOUNDATION (schema only) ============
def test_portal_foundation_schema_exists(client):
    async def _check():
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
        from sqlalchemy import select
        from app.modules.crm.portal_models import ClientAccount, PortalUser, SharedDocument, ClientRequest, ClientTicket
        eng = create_async_engine(os.environ["DATABASE_URL"])
        Session = async_sessionmaker(eng, expire_on_commit=False)
        async with Session() as s:
            # Tables exist and are queryable (foundation only — no rows yet).
            for model in (ClientAccount, PortalUser, SharedDocument, ClientRequest, ClientTicket):
                rows = (await s.execute(select(model))).scalars().all()
                assert rows == []
        await eng.dispose()
    run(_check())
    # No portal endpoints are exposed in Phase 4 (foundation only).
    assert client.get("/api/client-accounts", headers=H(P["admin"])).status_code == 404
