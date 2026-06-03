"""OpsCore backend API tests."""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    # fallback to reading frontend/.env
    try:
        with open('/app/frontend/.env') as f:
            for line in f:
                if line.startswith('REACT_APP_BACKEND_URL'):
                    BASE_URL = line.split('=', 1)[1].strip().rstrip('/')
                    break
    except Exception:
        pass

API = f"{BASE_URL}/api"

FOUNDER_EMAIL = "founder@opscore.app"
FOUNDER_PASSWORD = "test123"


# ---- Fixtures ----
@pytest.fixture(scope="session")
def http():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def founder_token(http):
    r = http.post(f"{API}/auth/login", json={"email": FOUNDER_EMAIL, "password": FOUNDER_PASSWORD})
    if r.status_code != 200:
        pytest.skip(f"Founder login failed: {r.status_code} {r.text}")
    return r.json()["token"]


@pytest.fixture(scope="session")
def auth(founder_token):
    return {"Authorization": f"Bearer {founder_token}", "Content-Type": "application/json"}


# ---- Health/root ----
def test_root(http):
    r = http.get(f"{API}/")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


# ---- AUTH ----
class TestAuth:
    def test_register_new_user(self, http):
        email = f"TEST_user_{uuid.uuid4().hex[:8]}@opscore.app"
        r = http.post(f"{API}/auth/register", json={
            "email": email, "password": "test12345", "name": "Test User"
        })
        assert r.status_code == 200, r.text
        data = r.json()
        assert "token" in data and len(data["token"]) > 20
        assert data["user"]["email"] == email.lower()
        assert "password_hash" not in data["user"]
        assert "_id" not in data["user"]

    def test_register_duplicate_fails(self, http):
        r = http.post(f"{API}/auth/register", json={
            "email": FOUNDER_EMAIL, "password": "test123", "name": "Dup"
        })
        assert r.status_code == 400

    def test_login_success(self, http):
        r = http.post(f"{API}/auth/login", json={"email": FOUNDER_EMAIL, "password": FOUNDER_PASSWORD})
        assert r.status_code == 200, r.text
        d = r.json()
        assert "token" in d
        assert d["user"]["email"] == FOUNDER_EMAIL
        assert "password_hash" not in d["user"]

    def test_login_invalid(self, http):
        r = http.post(f"{API}/auth/login", json={"email": FOUNDER_EMAIL, "password": "wrong"})
        assert r.status_code == 401

    def test_me_requires_token(self, http):
        r = http.get(f"{API}/auth/me")
        assert r.status_code in (401, 403)

    def test_me_invalid_token(self, http):
        r = http.get(f"{API}/auth/me", headers={"Authorization": "Bearer bad.token.here"})
        assert r.status_code == 401

    def test_me_with_valid_token(self, http, auth):
        r = http.get(f"{API}/auth/me", headers=auth)
        assert r.status_code == 200
        d = r.json()
        assert d["email"] == FOUNDER_EMAIL
        assert "password_hash" not in d


# ---- PROJECTS ----
class TestProjects:
    def test_project_crud(self, http, auth):
        # create
        r = http.post(f"{API}/projects", headers=auth, json={
            "name": "TEST_Project_Alpha", "description": "test", "priority": "high"
        })
        assert r.status_code == 200, r.text
        p = r.json()
        assert p["name"] == "TEST_Project_Alpha"
        assert p["priority"] == "high"
        assert "id" in p
        assert "_id" not in p
        pid = p["id"]

        # list
        r = http.get(f"{API}/projects", headers=auth)
        assert r.status_code == 200
        ids = [x["id"] for x in r.json()]
        assert pid in ids

        # get
        r = http.get(f"{API}/projects/{pid}", headers=auth)
        assert r.status_code == 200
        assert r.json()["id"] == pid
        assert "tasks" in r.json()

        # patch
        r = http.patch(f"{API}/projects/{pid}", headers=auth, json={"status": "paused"})
        assert r.status_code == 200
        assert r.json()["status"] == "paused"

        # verify persist
        r = http.get(f"{API}/projects/{pid}", headers=auth)
        assert r.json()["status"] == "paused"

        # delete
        r = http.delete(f"{API}/projects/{pid}", headers=auth)
        assert r.status_code == 200

        # verify gone
        r = http.get(f"{API}/projects/{pid}", headers=auth)
        assert r.status_code == 404

    def test_project_requires_auth(self, http):
        r = http.post(f"{API}/projects", json={"name": "x"})
        assert r.status_code in (401, 403)


# ---- TASKS ----
class TestTasks:
    @pytest.fixture(scope="class")
    def project_id(self, http, auth):
        r = http.post(f"{API}/projects", headers=auth, json={"name": "TEST_TasksProject"})
        pid = r.json()["id"]
        yield pid
        http.delete(f"{API}/projects/{pid}", headers=auth)

    def test_task_full_crud(self, http, auth, project_id):
        r = http.post(f"{API}/tasks", headers=auth, json={
            "title": "TEST_Task_1",
            "project_id": project_id,
            "status": "todo",
            "priority": "high",
            "complexity": "medium",
            "estimated_minutes": 45,
            "due_date": "2026-12-31T10:00:00+00:00",
        })
        assert r.status_code == 200, r.text
        t = r.json()
        assert t["title"] == "TEST_Task_1"
        assert t["priority"] == "high"
        assert t["complexity"] == "medium"
        assert "_id" not in t
        tid = t["id"]

        # list
        r = http.get(f"{API}/tasks", headers=auth)
        assert r.status_code == 200
        assert any(x["id"] == tid for x in r.json())

        # get single
        r = http.get(f"{API}/tasks/{tid}", headers=auth)
        assert r.status_code == 200
        assert r.json()["title"] == "TEST_Task_1"

        # patch to done
        r = http.patch(f"{API}/tasks/{tid}", headers=auth, json={"status": "done"})
        assert r.status_code == 200
        upd = r.json()
        assert upd["status"] == "done"
        assert upd.get("completed_at") is not None

        # verify persisted
        r = http.get(f"{API}/tasks/{tid}", headers=auth)
        assert r.json()["status"] == "done"

        # delete
        r = http.delete(f"{API}/tasks/{tid}", headers=auth)
        assert r.status_code == 200
        r = http.get(f"{API}/tasks/{tid}", headers=auth)
        assert r.status_code == 404


# ---- NOTES ----
class TestNotes:
    def test_note_crud(self, http, auth):
        r = http.post(f"{API}/notes", headers=auth, json={
            "title": "TEST_Note", "content": "hello world", "tags": ["test"]
        })
        assert r.status_code == 200, r.text
        n = r.json()
        assert n["title"] == "TEST_Note"
        assert "_id" not in n
        nid = n["id"]

        # list
        r = http.get(f"{API}/notes", headers=auth)
        assert r.status_code == 200
        assert any(x["id"] == nid for x in r.json())

        # update
        r = http.patch(f"{API}/notes/{nid}", headers=auth, json={"content": "updated"})
        assert r.status_code == 200
        assert r.json()["content"] == "updated"

        # delete
        r = http.delete(f"{API}/notes/{nid}", headers=auth)
        assert r.status_code == 200


# ---- DASHBOARD ----
class TestDashboard:
    def test_summary_shape(self, http, auth):
        r = http.get(f"{API}/dashboard/summary", headers=auth)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ["projects_active", "tasks_total", "tasks_done", "tasks_blocked",
                  "tasks_delayed", "focus_score", "execution_score", "burnout_risk",
                  "upcoming_deadlines", "projects"]:
            assert k in d, f"missing key {k}"
        assert d["burnout_risk"] in ("low", "medium", "high")
        assert isinstance(d["focus_score"], int)
        assert isinstance(d["execution_score"], int)


# ---- ANALYTICS ----
class TestAnalytics:
    def test_overview(self, http, auth):
        r = http.get(f"{API}/analytics/overview", headers=auth)
        assert r.status_code == 200, r.text
        d = r.json()
        assert isinstance(d["daily"], list) and len(d["daily"]) == 14
        assert isinstance(d["heatmap"], list) and len(d["heatmap"]) == 7
        assert all(len(row) == 24 for row in d["heatmap"])
        for k in ["low", "medium", "high", "critical"]:
            assert k in d["priority_distribution"]
        assert isinstance(d["estimate_accuracy"], int)


# ---- TEAM ----
class TestTeam:
    def test_invite_without_resend_key(self, http, auth):
        r = http.post(f"{API}/team/invite", headers=auth, json={
            "email": f"TEST_invitee_{uuid.uuid4().hex[:6]}@example.com",
            "role": "member",
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("emailed") is False, "should be False when RESEND_API_KEY blank"
        assert "invite_url" in d
        assert d["invite_url"].startswith("http")
        assert "_id" not in d

    def test_list_invites(self, http, auth):
        r = http.get(f"{API}/team/invites", headers=auth)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_list_members(self, http, auth):
        r = http.get(f"{API}/team/members", headers=auth)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        assert any(u["email"] == FOUNDER_EMAIL for u in rows)
        for u in rows:
            assert "password_hash" not in u
            assert "_id" not in u
            assert "active_tasks" in u


# ---- NOTIFICATIONS ----
class TestNotifications:
    def test_overdue_and_blocked_detection(self, http, auth):
        # create an overdue task
        r = http.post(f"{API}/tasks", headers=auth, json={
            "title": "TEST_Overdue_Task",
            "due_date": "2020-01-01T00:00:00+00:00",
            "status": "todo",
        })
        overdue_id = r.json()["id"]

        # due-soon (in 12 hours)
        from datetime import datetime, timezone, timedelta
        due_soon = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
        r = http.post(f"{API}/tasks", headers=auth, json={
            "title": "TEST_DueSoon_Task", "due_date": due_soon, "status": "todo"
        })
        due_id = r.json()["id"]

        # blocked
        r = http.post(f"{API}/tasks", headers=auth, json={
            "title": "TEST_Blocked_Task", "status": "blocked",
        })
        blocked_id = r.json()["id"]

        r = http.get(f"{API}/notifications", headers=auth)
        assert r.status_code == 200, r.text
        types = {n["type"] for n in r.json()}
        task_ids = {n.get("task_id") for n in r.json()}
        assert "overdue" in types
        assert "blocked" in types
        # due_soon should be present
        assert "due_soon" in types
        assert overdue_id in task_ids
        assert blocked_id in task_ids
        assert due_id in task_ids

        # cleanup
        for tid in (overdue_id, due_id, blocked_id):
            http.delete(f"{API}/tasks/{tid}", headers=auth)


# ---- FOCUS SESSIONS ----
class TestFocus:
    def test_focus_increments_task_actual(self, http, auth):
        r = http.post(f"{API}/tasks", headers=auth, json={
            "title": "TEST_Focus_Task", "estimated_minutes": 60, "actual_minutes": 0
        })
        tid = r.json()["id"]

        r = http.post(f"{API}/focus/sessions", headers=auth, json={
            "task_id": tid, "duration_minutes": 25, "completed": True
        })
        assert r.status_code == 200, r.text
        assert r.json()["duration_minutes"] == 25
        assert "_id" not in r.json()

        # verify task incremented
        r = http.get(f"{API}/tasks/{tid}", headers=auth)
        assert r.json()["actual_minutes"] >= 25

        # list focus
        r = http.get(f"{API}/focus/sessions", headers=auth)
        assert r.status_code == 200
        assert any(s.get("task_id") == tid for s in r.json())

        http.delete(f"{API}/tasks/{tid}", headers=auth)


# ---- AI ENDPOINTS (real Claude calls) ----
AI_TIMEOUT = 60


class TestAI:
    def test_ai_chat_and_multi_turn(self, http, auth):
        r = http.post(f"{API}/ai/chat", headers=auth, json={
            "message": "In one sentence, what should I focus on today?",
        }, timeout=AI_TIMEOUT)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "reply" in d and len(d["reply"]) > 0
        assert "AI error" not in d["reply"], d["reply"]
        assert "AI service unavailable" not in d["reply"]
        sid = d["session_id"]
        assert sid

        # multi-turn
        r2 = http.post(f"{API}/ai/chat", headers=auth, json={
            "message": "Repeat your last suggestion shortly.", "session_id": sid,
        }, timeout=AI_TIMEOUT)
        assert r2.status_code == 200, r2.text
        d2 = r2.json()
        assert d2["session_id"] == sid
        assert len(d2["messages"]) >= 4  # 2 user + 2 assistant

    def test_ai_conversations_list_and_get(self, http, auth):
        # ensure at least one convo exists
        r = http.post(f"{API}/ai/chat", headers=auth, json={"message": "hi quick"}, timeout=AI_TIMEOUT)
        sid = r.json()["session_id"]

        r = http.get(f"{API}/ai/conversations", headers=auth)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list) and len(rows) >= 1
        assert any("preview" in c for c in rows)

        r = http.get(f"{API}/ai/conversations/{sid}", headers=auth)
        assert r.status_code == 200
        assert r.json()["session_id"] == sid
        assert "messages" in r.json()

    def test_ai_rewrite(self, http, auth):
        r = http.post(f"{API}/ai/rewrite", headers=auth, json={
            "text": "team meeting tmrw 3pm discuss launch and stuff",
            "tone": "professional",
        }, timeout=AI_TIMEOUT)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "rewritten" in d
        assert len(d["rewritten"]) > 10
        assert "AI error" not in d["rewritten"]

    def test_ai_breakdown_persists_subtasks(self, http, auth):
        r = http.post(f"{API}/tasks", headers=auth, json={
            "title": "TEST_Launch_landing_page",
            "description": "Build and ship a landing page for product launch",
            "priority": "high",
            "complexity": "high",
        })
        tid = r.json()["id"]

        r = http.post(f"{API}/ai/breakdown", headers=auth, json={"task_id": tid}, timeout=AI_TIMEOUT)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "subtasks" in d
        assert isinstance(d["subtasks"], list)
        # Should parse JSON properly
        assert len(d["subtasks"]) > 0, f"No subtasks parsed. raw: {d.get('raw','')[:300]}"

        # verify persistence on task
        r = http.get(f"{API}/tasks/{tid}", headers=auth)
        task = r.json()
        assert isinstance(task.get("subtasks"), list)
        assert len(task["subtasks"]) > 0

        http.delete(f"{API}/tasks/{tid}", headers=auth)

    def test_ai_summarize_project(self, http, auth):
        r = http.post(f"{API}/projects", headers=auth, json={
            "name": "TEST_Summarize_Project", "description": "ai test project", "priority": "high"
        })
        pid = r.json()["id"]
        # add a task
        http.post(f"{API}/tasks", headers=auth, json={
            "title": "TEST_SummTask", "project_id": pid, "status": "todo"
        })

        r = http.post(f"{API}/ai/summarize-project", headers=auth, json={"project_id": pid}, timeout=AI_TIMEOUT)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "summary" in d
        assert len(d["summary"]) > 20
        assert "AI error" not in d["summary"]

        http.delete(f"{API}/projects/{pid}", headers=auth)

    def test_ai_prioritize(self, http, auth):
        # ensure at least one open task
        r = http.post(f"{API}/tasks", headers=auth, json={
            "title": "TEST_Prio_Task", "priority": "high", "status": "todo",
            "due_date": "2026-12-01T10:00:00+00:00", "complexity": "medium",
        })
        tid = r.json()["id"]

        r = http.get(f"{API}/ai/prioritize", headers=auth, timeout=AI_TIMEOUT)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "ranked" in d
        assert isinstance(d["ranked"], list)
        # at least one ranked or insight
        assert len(d["ranked"]) > 0 or len(d.get("insights", [])) > 0, f"Empty AI response: {d}"

        http.delete(f"{API}/tasks/{tid}", headers=auth)
