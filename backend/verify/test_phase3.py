"""Phase 3 verification: the Intelligence Layer.

Covers Knowledge Base, AI daily-update + meeting summaries (with dedup + graceful
fallback), the Risk Detection Engine, Recommendations, weekly/monthly reports, the
Executive Intelligence dashboard, and Executive Digests. Exercises RBAC enforcement
(incl. department-scoped roles), Activity Feed, and Audit Log via the real app on
SQLite + in-memory Mongo.
"""
import asyncio
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
    P["admin"], P["admin_id"] = _register(client, "p3admin@opscore.app", "P3 Admin")
    P["mgr"], P["mgr_id"] = _register(client, "p3mgr@opscore.app", "P3 Manager")
    P["emp"], P["emp_id"] = _register(client, "p3emp@opscore.app", "P3 Employee")
    P["exec"], P["exec_id"] = _register(client, "p3exec@opscore.app", "P3 Exec")
    P["nobody"], P["nobody_id"] = _register(client, "p3nobody@opscore.app", "P3 Nobody")
    for uid in (P["mgr_id"], P["emp_id"], P["exec_id"], P["nobody_id"]):
        run(db.users.update_one({"id": uid}, {"$set": {"is_admin": False}}))

    P["dept"] = client.post("/api/departments", json={"name": "P3 Engineering"}, headers=H(P["admin"])).json()["id"]
    P["dept2"] = client.post("/api/departments", json={"name": "P3 Operations"}, headers=H(P["admin"])).json()["id"]
    P["mgr_emp"] = client.post("/api/employees", json={"user_id": P["mgr_id"], "primary_department_id": P["dept"]},
                               headers=H(P["admin"])).json()["id"]
    client.post("/api/employees", json={"user_id": P["emp_id"], "primary_department_id": P["dept"],
                "manager_id": P["mgr_emp"]}, headers=H(P["admin"]))

    roles = {r["key"]: r["id"] for r in client.get("/api/rbac/roles", headers=H(P["admin"])).json()}
    def assign(uid, key, scope_type="global", scope_id=None):
        body = {"user_id": uid, "role_id": roles[key], "scope_type": scope_type}
        if scope_id:
            body["scope_id"] = scope_id
        assert client.post("/api/rbac/assignments", json=body, headers=H(P["admin"])).status_code == 200
    assign(P["emp_id"], "employee")
    assign(P["mgr_id"], "employee")
    assign(P["mgr_id"], "department_manager", "department", P["dept"])
    assign(P["exec_id"], "executive")

    # Operational data the intelligence layer will analyse.
    client.post("/api/daily-updates", json={"today": "Shipped feature X", "tomorrow": "Code review",
                "blockers": "Waiting on infra access"}, headers=H(P["emp"]))
    # Overdue + blocked tasks owned by the employee (Engineering).
    past = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    for i in range(11):
        run(db.tasks.insert_one({"id": f"p3task{i}", "title": f"Overdue {i}", "status": "todo",
            "owner_id": P["emp_id"], "assignee_id": P["emp_id"], "due_date": past, "priority": "high",
            "created_at": past, "completed_at": None}))
    run(db.tasks.insert_one({"id": "p3blocked", "title": "Blocked task", "status": "blocked",
        "owner_id": P["emp_id"], "assignee_id": P["emp_id"], "created_at": past}))
    yield


# ============ MODULE 1 — KNOWLEDGE BASE ============
def test_kb_create_requires_permission(client):
    # employee has kb.view only -> cannot create
    assert client.post("/api/knowledge", json={"title": "X", "body": "y"}, headers=H(P["emp"])).status_code == 403
    # department manager can create in their department
    r = client.post("/api/knowledge", json={"title": "Incident Runbook", "body": "step one then two",
                    "article_type": "runbook", "category": "ops", "tags": ["incident", "oncall"],
                    "department_id": P["dept"]}, headers=H(P["mgr"]))
    assert r.status_code == 200, r.text
    P["kb"] = r.json()["id"]
    assert r.json()["version"] == 1
    # admin publishes a company-wide policy
    P["kb_company"] = client.post("/api/knowledge", json={"title": "Code of Conduct", "body": "be excellent",
                                  "article_type": "policy"}, headers=H(P["admin"])).json()["id"]
    # admin creates an Operations-only article (employee is NOT a member of Operations)
    P["kb_ops"] = client.post("/api/knowledge", json={"title": "Ops Secret", "body": "hidden",
                              "article_type": "department_doc", "department_id": P["dept2"]}, headers=H(P["admin"])).json()["id"]


def test_kb_invalid_type_rejected(client):
    assert client.post("/api/knowledge", json={"title": "Z", "article_type": "nope"}, headers=H(P["admin"])).status_code == 400


def test_kb_visibility_scoping(client):
    ids = {a["id"] for a in client.get("/api/knowledge", headers=H(P["emp"])).json()}
    assert P["kb_company"] in ids       # company-wide visible to any kb.view holder
    assert P["kb"] in ids               # own department visible (employee is in Engineering)
    assert P["kb_ops"] not in ids       # other department's doc is hidden
    # nobody (no kb.view) sees nothing
    assert client.get("/api/knowledge", headers=H(P["nobody"])).json() == []
    # direct fetch of the hidden article is forbidden for the employee
    assert client.get(f"/api/knowledge/{P['kb_ops']}", headers=H(P["emp"])).status_code == 403


def test_kb_search(client):
    res = client.get("/api/knowledge", headers=H(P["mgr"]), params={"q": "Runbook"}).json()
    assert any(a["id"] == P["kb"] for a in res)
    res2 = client.get("/api/knowledge", headers=H(P["mgr"]), params={"tag": "oncall"}).json()
    assert any(a["id"] == P["kb"] for a in res2)


def test_kb_versioning(client):
    r = client.patch(f"/api/knowledge/{P['kb']}", json={"body": "step one, two, then three"}, headers=H(P["mgr"]))
    assert r.status_code == 200 and r.json()["version"] == 2
    versions = client.get(f"/api/knowledge/{P['kb']}/versions", headers=H(P["mgr"])).json()
    assert len(versions) == 1 and versions[0]["version"] == 1  # pre-edit snapshot archived


def test_kb_activity_and_audit(client):
    feed_verbs = {e["verb"] for e in client.get("/api/activity", headers=H(P["admin"])).json()}
    assert "knowledge.created" in feed_verbs
    actions = {a["action"] for a in client.get("/api/audit", headers=H(P["admin"])).json()}
    assert {"kb.create", "kb.update"} <= actions


def test_kb_delete_permission(client):
    # employee cannot delete the manager's article
    assert client.delete(f"/api/knowledge/{P['kb']}", headers=H(P["emp"])).status_code == 403
    # owner (manager) can delete their own
    assert client.delete(f"/api/knowledge/{P['kb']}", headers=H(P["mgr"])).status_code == 200


# ============ MODULE 2 — AI DAILY UPDATE SUMMARIES ============
def test_daily_update_summary_generation_and_dedup(client):
    start = (date.today() - timedelta(days=7)).isoformat()
    end = date.today().isoformat()
    params = {"subject_type": "department", "subject_id": P["dept"], "period_start": start, "period_end": end}
    r = client.post("/api/intelligence/summaries/daily-update", headers=H(P["exec"]), params=params)
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["narrative"] and "completed" in s["structured"] and "blockers" in s["structured"]
    assert s["structured"]["blockers"]  # the employee reported a blocker
    assert s["deduped"] is False
    P["du_summary_id"] = s["id"]
    # second call with identical source -> deduped (not regenerated)
    again = client.post("/api/intelligence/summaries/daily-update", headers=H(P["exec"]), params=params).json()
    assert again["deduped"] is True and again["id"] == P["du_summary_id"]
    # force regenerates
    forced = client.post("/api/intelligence/summaries/daily-update", headers=H(P["exec"]),
                         params={**params, "force": True}).json()
    assert forced["deduped"] is False


def test_daily_update_summary_permissions(client):
    params = {"subject_type": "department", "subject_id": P["dept"]}
    # nobody has no view permission
    assert client.post("/api/intelligence/summaries/daily-update", headers=H(P["nobody"]), params=params).status_code == 403
    # department-scoped manager may summarize their department
    assert client.post("/api/intelligence/summaries/daily-update", headers=H(P["mgr"]), params=params).status_code == 200
    # employee may summarize themselves
    self_params = {"subject_type": "employee", "subject_id": P["emp_id"]}
    assert client.post("/api/intelligence/summaries/daily-update", headers=H(P["emp"]), params=self_params).status_code == 200
    # but not another employee
    other = {"subject_type": "employee", "subject_id": P["exec_id"]}
    assert client.post("/api/intelligence/summaries/daily-update", headers=H(P["emp"]), params=other).status_code == 403


# ============ MODULE 3 — AI MEETING SUMMARIES ============
def test_meeting_summary(client):
    mtg = client.post("/api/meetings", json={"title": "Weekly Fraud Review", "department_id": P["dept"],
                      "attendee_ids": [P["emp_id"]]}, headers=H(P["mgr"])).json()["id"]
    client.put(f"/api/meetings/{mtg}/mom", json={"notes": "Reviewed feeds", "decisions": ["Adopt OpenPhish"],
               "discussion_points": ["latency"]}, headers=H(P["mgr"]))
    client.post(f"/api/meetings/{mtg}/action-items", json={"title": "Review feed", "owner_user_id": P["emp_id"],
                "due_in_days": 7}, headers=H(P["mgr"]))
    P["mtg"] = mtg
    r = client.post(f"/api/intelligence/summaries/meeting/{mtg}", headers=H(P["mgr"]))
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["structured"]["key_decisions"] == ["Adopt OpenPhish"]
    assert s["structured"]["action_items"]["total"] == 1 and s["narrative"]
    # linked summary is retrievable for an attendee
    assert client.get(f"/api/intelligence/summaries/meeting/{mtg}", headers=H(P["emp"])).status_code == 200
    # a non-attendee with no permission cannot summarize/view
    assert client.post(f"/api/intelligence/summaries/meeting/{mtg}", headers=H(P["nobody"])).status_code == 403


# ============ MODULE 6 — RISK DETECTION ============
def test_risk_engine_company(client):
    r = client.get("/api/intelligence/risks", headers=H(P["exec"]))
    assert r.status_code == 200, r.text
    types = {x["type"]: x for x in r.json()["risks"]}
    assert "overdue_tasks" in types and "blocked_work" in types and "repeated_delays" in types
    # explainability: every risk carries a source object + a valid level
    for risk in r.json()["risks"]:
        assert risk["level"] in ("low", "medium", "high", "critical") and "source" in risk
    # 11 overdue for one person -> repeated_delays is critical
    assert types["repeated_delays"]["level"] == "critical"


def test_risk_engine_scoped_and_permissions(client):
    # department-scoped manager may view their department's risks
    rd = client.get("/api/intelligence/risks", headers=H(P["mgr"]), params={"department_id": P["dept"]})
    assert rd.status_code == 200 and rd.json()["count"] >= 1
    # employee cannot view company risks (no intelligence.view)
    assert client.get("/api/intelligence/risks", headers=H(P["emp"])).status_code == 403


# ============ MODULE 8 — RECOMMENDATIONS ============
def test_recommendations(client):
    assert client.get("/api/intelligence/recommendations", headers=H(P["emp"])).status_code == 403
    r = client.get("/api/intelligence/recommendations", headers=H(P["exec"]))
    assert r.status_code == 200, r.text
    recs = r.json()["recommendations"]
    assert recs  # delays/health should trigger at least one
    for rec in recs:
        assert rec["explanation"] and "source_data" in rec and rec["priority"] in ("low", "medium", "high", "critical")
    assert any(rec["type"] in ("department_attention", "too_many_delays") for rec in recs)


# ============ MODULE 7 — EXECUTIVE INTELLIGENCE DASHBOARD ============
def test_intelligence_dashboard(client):
    assert client.get("/api/intelligence/dashboard", headers=H(P["emp"])).status_code == 403
    r = client.get("/api/intelligence/dashboard", headers=H(P["exec"]))
    assert r.status_code == 200, r.text
    b = r.json()
    for key in ("company_health_score", "department_health", "operational_risks", "risk_indicators",
                "blocked_work", "pending_approvals", "escalations", "most_active_departments",
                "least_active_departments", "trend_analysis", "weekly_comparison", "monthly_comparison",
                "recommendations"):
        assert key in b, f"missing {key}"
    assert isinstance(b["company_health_score"], int) and 0 <= b["company_health_score"] <= 100
    assert "weekly" in b["trend_analysis"] and "completed" in b["weekly_comparison"]


# ============ MODULES 4/5 — WEEKLY + MONTHLY REPORTS ============
def test_weekly_department_report(client):
    # scoped manager generates their department report; reused reporting foundation persists it
    r = client.post("/api/intelligence/reports/weekly-department", headers=H(P["mgr"]),
                    params={"department_id": P["dept"]})
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert "metrics" in data and "participation" in data and "risks" in data and "health" in data
    assert r.json()["summary"]  # narrative present (fallback or AI)
    P["weekly_report_id"] = r.json()["id"]
    # cannot generate another department's report
    assert client.post("/api/intelligence/reports/weekly-department", headers=H(P["mgr"]),
                       params={"department_id": P["dept2"]}).status_code == 403
    # report is readable via the shared reporting API
    listed = {x["id"] for x in client.get("/api/reports", headers=H(P["exec"])).json()}
    assert P["weekly_report_id"] in listed


def test_monthly_executive_report(client):
    assert client.post("/api/intelligence/reports/monthly-executive", headers=H(P["emp"])).status_code == 403
    r = client.post("/api/intelligence/reports/monthly-executive", headers=H(P["exec"]))
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert "departments" in data and "health" in data and r.json()["summary"]
    assert any(d["department_id"] == P["dept"] for d in data["departments"])


# ============ MODULE 9 — EXECUTIVE DIGESTS ============
def test_digests(client):
    assert client.post("/api/intelligence/digests", headers=H(P["emp"]), params={"period_type": "weekly"}).status_code == 403
    r = client.post("/api/intelligence/digests", headers=H(P["exec"]), params={"period_type": "weekly"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["narrative"] and "top_risks" in d["structured"] and "top_recommendations" in d["structured"]
    assert "health" in d["structured"]
    # dedup
    again = client.post("/api/intelligence/digests", headers=H(P["exec"]), params={"period_type": "weekly"}).json()
    assert again["deduped"] is True
    # history listing + audit
    listed = client.get("/api/intelligence/digests", headers=H(P["exec"]), params={"period_type": "weekly"}).json()
    assert any(x["id"] == d["id"] for x in listed)
    assert client.get("/api/intelligence/digests", headers=H(P["emp"])).status_code == 403
    actions = {a["action"] for a in client.get("/api/audit", headers=H(P["admin"])).json()}
    assert "intelligence.digest.generate" in actions
