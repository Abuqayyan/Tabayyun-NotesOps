"""Phase 5 verification: platform maturity for Tabayyun NotesOps.

Covers Global Search, Notification Center, Observability + Audit search/export, the Admin
Operations Center, Data Exports, the Settings Center, the request-metrics middleware, and
permission enforcement — all reusing the existing RBAC/Activity/Audit seams without
touching any business module.
"""
import asyncio

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
    P["admin"], P["admin_id"] = _register(client, "p5admin@opscore.app", "P5 Admin")
    P["exec"], P["exec_id"] = _register(client, "p5exec@opscore.app", "P5 Exec")
    P["mgr"], P["mgr_id"] = _register(client, "p5mgr@opscore.app", "P5 Manager")
    P["emp"], P["emp_id"] = _register(client, "p5emp@opscore.app", "P5 Employee")
    P["nobody"], P["nobody_id"] = _register(client, "p5nobody@opscore.app", "P5 Nobody")
    for uid in (P["exec_id"], P["mgr_id"], P["emp_id"], P["nobody_id"]):
        run(db.users.update_one({"id": uid}, {"$set": {"is_admin": False}}))

    P["sales"] = client.post("/api/departments", json={"name": "P5 Sales"}, headers=H(P["admin"])).json()["id"]
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
    assign(P["exec_id"], "executive")        # ops.view, export.data, audit.view, crm view
    assign(P["emp_id"], "employee")          # crm write, no ops/audit/export
    assign(P["mgr_id"], "department_manager", "department", P["sales"])

    # Seed some searchable / auditable data.
    P["company"] = client.post("/api/crm/companies", json={"name": "Acme Analytics", "industry": "Data",
                               "department_id": P["sales"]}, headers=H(P["emp"])).json()["id"]
    client.post("/api/knowledge", json={"title": "Acme Onboarding Guide", "article_type": "internal_guide"},
                headers=H(P["admin"]))
    client.post("/api/tasks", json={"title": "Acme follow-up call"}, headers=H(P["emp"]))
    yield


# ============ MODULE 2 — GLOBAL SEARCH ============
def test_global_search_permission_aware(client):
    r = client.get("/api/search", headers=H(P["emp"]), params={"q": "Acme"})
    assert r.status_code == 200, r.text
    res = r.json()
    types = {x["type"] for x in res["results"]}
    assert "crm_company" in types and any(x["title"] == "Acme Analytics" for x in res["results"])
    # results are ranked (descending score)
    scores = [x["score"] for x in res["results"]]
    assert scores == sorted(scores, reverse=True)
    # nobody (no permissions) sees no CRM/KB results
    res2 = client.get("/api/search", headers=H(P["nobody"]), params={"q": "Acme"}).json()
    assert all(x["type"] not in ("crm_company", "knowledge") for x in res2["results"])
    # too-short query short-circuits
    assert client.get("/api/search", headers=H(P["emp"]), params={"q": "a"}).json()["count"] == 0


def test_search_type_filter_and_recent(client):
    r = client.get("/api/search", headers=H(P["exec"]), params={"q": "Acme", "types": "crm_company"}).json()
    assert all(x["type"] == "crm_company" for x in r["results"])
    recent = client.get("/api/search/recent", headers=H(P["exec"])).json()
    assert any(x["q"] == "Acme" for x in recent)
    assert "crm_company" in client.get("/api/search/types", headers=H(P["emp"])).json()["types"]


# ============ MODULE 3 — NOTIFICATION CENTER ============
def test_notification_center(client):
    # Drive a real per-recipient notification: an approval routed to the employee's manager.
    tmpl = client.post("/api/approvals/templates", json={"key": "p5leave", "name": "Leave",
                       "steps": [{"name": "Manager", "approver_type": "manager"}]}, headers=H(P["admin"])).json()["id"]
    client.post("/api/approvals/requests", json={"template_id": tmpl, "title": "Time off",
                "department_id": P["sales"]}, headers=H(P["emp"]))
    inbox = client.get("/api/notifications/center", headers=H(P["mgr"])).json()
    assert any(n["category"] == "approval" for n in inbox)
    nid = next(n["id"] for n in inbox if n["category"] == "approval")
    assert client.get("/api/notifications/center/unread-count", headers=H(P["mgr"])).json()["unread"] >= 1
    cats = client.get("/api/notifications/center/categories", headers=H(P["mgr"])).json()["unread_by_category"]
    assert cats["approval"] >= 1
    # read -> unread count drops; archive removes from default view
    assert client.post(f"/api/notifications/center/{nid}/read", headers=H(P["mgr"])).status_code == 200
    assert client.post(f"/api/notifications/center/{nid}/archive", headers=H(P["mgr"])).status_code == 200
    assert all(n["id"] != nid for n in client.get("/api/notifications/center", headers=H(P["mgr"])).json())
    # mark-all-read is idempotent and scoped to the user
    assert client.post("/api/notifications/center/read-all", headers=H(P["mgr"])).status_code == 200
    # a different user cannot mark someone else's notification
    assert client.post(f"/api/notifications/center/{nid}/read", headers=H(P["emp"])).status_code == 404


# ============ MODULE 4 — OBSERVABILITY + AUDIT ============
def test_audit_search_and_export(client):
    # filtered search
    rows = client.get("/api/audit", headers=H(P["exec"]), params={"q": "crm"}).json()
    assert rows and all("crm" in (r["action"] + r["entity_type"]).lower() for r in rows)
    # CSV export
    exp = client.get("/api/audit/export", headers=H(P["exec"]), params={"format": "csv"})
    assert exp.status_code == 200 and exp.headers["content-type"].startswith("text/csv")
    assert "X-Export-Rows" in exp.headers and exp.text.splitlines()[0].startswith("id,created_at")
    # employee lacks audit.view
    assert client.get("/api/audit", headers=H(P["emp"])).status_code == 403


def test_observability_analytics(client):
    ua = client.get("/api/observability/user-activity", headers=H(P["exec"]))
    assert ua.status_code == 200 and isinstance(ua.json(), list)
    mu = client.get("/api/observability/module-usage", headers=H(P["exec"])).json()
    assert any(m["module"] == "crm" for m in mu["by_module"])
    # the request-metrics middleware has been recording traffic
    metrics = client.get("/api/observability/metrics", headers=H(P["exec"])).json()
    assert metrics["total_requests"] > 0 and "slowest_routes" in metrics
    # a deliberate 403 is captured as a permission denial
    assert client.get("/api/ops/health", headers=H(P["emp"])).status_code == 403
    pu = client.get("/api/observability/permission-usage", headers=H(P["exec"])).json()
    assert pu["total_denials"] >= 1
    assert client.get("/api/observability/failed-operations", headers=H(P["exec"])).status_code == 200
    assert client.get("/api/observability/module-usage", headers=H(P["emp"])).status_code == 403


# ============ MODULE 7 — OPERATIONS CENTER ============
def test_operations_center(client):
    h = client.get("/api/ops/health", headers=H(P["exec"]))
    assert h.status_code == 200 and h.json()["mongo"] is True and "scheduler" in h.json()
    ov = client.get("/api/ops/overview", headers=H(P["exec"])).json()
    for k in ("health", "scheduler", "reminders", "escalations", "metrics", "users"):
        assert k in ov
    for path in ("/api/ops/reminders", "/api/ops/escalations", "/api/ops/metrics", "/api/ops/jobs"):
        assert client.get(path, headers=H(P["exec"])).status_code == 200
    # employee lacks ops.view
    assert client.get("/api/ops/overview", headers=H(P["emp"])).status_code == 403


# ============ MODULE 8 — DATA EXPORTS ============
def test_data_exports(client):
    r = client.get("/api/exports/crm_companies", headers=H(P["exec"]), params={"format": "csv"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "Acme Analytics" in r.text and int(r.headers["X-Export-Rows"]) >= 1
    # tasks export
    assert client.get("/api/exports/tasks", headers=H(P["exec"]), params={"format": "csv"}).status_code == 200
    # xlsx requested -> xlsx if openpyxl present, else transparent CSV fallback
    x = client.get("/api/exports/tasks", headers=H(P["exec"]), params={"format": "xlsx"})
    assert x.status_code == 200
    assert x.headers.get("X-Export-Fallback") == "csv" or "spreadsheet" in x.headers["content-type"]
    # export is audited
    actions = {a["action"] for a in client.get("/api/audit", headers=H(P["admin"])).json()}
    assert "export.crm_companies" in actions
    # permission enforcement
    assert client.get("/api/exports/tasks", headers=H(P["emp"])).status_code == 403
    assert client.get("/api/exports/unknown", headers=H(P["exec"])).status_code == 404


# ============ MODULE 9 — SETTINGS CENTER ============
def test_settings_center(client):
    allset = client.get("/api/settings/center", headers=H(P["emp"]))
    assert allset.status_code == 200 and allset.json()["company"]["name"] == "Tabayyun NotesOps"
    # admin can update (settings.manage)
    u = client.put("/api/settings/center/company", json={"values": {"name": "Tabayyun NotesOps", "primary_color": "#123456"}},
                   headers=H(P["admin"]))
    assert u.status_code == 200 and u.json()["primary_color"] == "#123456"
    # executive lacks settings.manage
    assert client.put("/api/settings/center/security", json={"values": {"session_hours": 8}}, headers=H(P["exec"])).status_code == 403
    # unknown section / no valid keys
    assert client.put("/api/settings/center/bogus", json={"values": {}}, headers=H(P["admin"])).status_code == 404
    assert client.put("/api/settings/center/company", json={"values": {"nope": 1}}, headers=H(P["admin"])).status_code == 400
    # audited
    assert "settings.update" in {a["action"] for a in client.get("/api/audit", headers=H(P["admin"])).json()}


# ============ CROSS-CUTTING — REQUEST ID + REGRESSION SANITY ============
def test_request_id_header(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and "X-Request-ID" in r.headers


def test_phase5_permissions_seeded(client):
    keys = {p["key"] for p in client.get("/api/rbac/permissions", headers=H(P["admin"])).json()}
    assert {"ops.view", "settings.manage", "export.data"} <= keys
