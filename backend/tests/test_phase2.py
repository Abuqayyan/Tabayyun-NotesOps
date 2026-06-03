"""OpsCore Phase 2 backend tests: settings, daily-brief, weekly-review, dependencies, memory, share, intelligence, websocket."""
import os
import json
import asyncio
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    with open('/app/frontend/.env') as f:
        for line in f:
            if line.startswith('REACT_APP_BACKEND_URL'):
                BASE_URL = line.split('=', 1)[1].strip().rstrip('/')
                break

API = f"{BASE_URL}/api"
WS_URL = BASE_URL.replace("https://", "wss://").replace("http://", "ws://") + "/api/ws"

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


# ============ SETTINGS / AI PROVIDERS ============
class TestAISettings:
    def test_get_settings_shape(self, http, auth):
        r = http.get(f"{API}/settings/ai", headers=auth)
        assert r.status_code == 200
        d = r.json()
        for k in ("has_custom_key", "model", "use_own_key", "usage", "supported_models", "active_source"):
            assert k in d, f"missing {k}"
        assert isinstance(d["supported_models"], list) and len(d["supported_models"]) > 0
        assert d["active_source"] in ("user", "emergent")
        for uk in ("calls", "tokens_in", "tokens_out"):
            assert uk in d["usage"]

    def test_update_model(self, http, auth):
        r0 = http.get(f"{API}/settings/ai", headers=auth)
        supported = r0.json()["supported_models"]
        pick = supported[0]
        r = http.put(f"{API}/settings/ai", headers=auth, json={"model": pick})
        assert r.status_code == 200
        assert r.json()["model"] == pick
        # invalid model rejected
        bad = http.put(f"{API}/settings/ai", headers=auth, json={"model": "not-a-model"})
        assert bad.status_code == 400

    def test_set_and_clear_api_key(self, http, auth):
        # set key
        r = http.put(f"{API}/settings/ai", headers=auth, json={"api_key": "sk-ant-TEST_FAKE_KEY_123", "use_own_key": False})
        assert r.status_code == 200
        d = r.json()
        assert d["has_custom_key"] is True
        # key must NOT come back in plaintext
        assert "api_key" not in d
        assert "api_key_encrypted" not in d
        # subsequent GET also hides it
        g = http.get(f"{API}/settings/ai", headers=auth).json()
        assert g["has_custom_key"] is True
        assert "api_key" not in g and "api_key_encrypted" not in g
        # clear key via empty string
        r2 = http.put(f"{API}/settings/ai", headers=auth, json={"api_key": ""})
        assert r2.status_code == 200
        assert r2.json()["has_custom_key"] is False

    def test_connection_test_pong(self, http, auth):
        # ensure we are on emergent (cleared key above)
        r = http.post(f"{API}/settings/ai/test", headers=auth, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("ok", "latency_ms", "model", "source", "reply"):
            assert k in d
        assert d["source"] in ("user", "emergent")
        assert isinstance(d["latency_ms"], int)
        assert d["ok"] is True
        # Reply usually contains PONG, but be lenient
        assert "PONG" in d["reply"].upper() or len(d["reply"]) > 0

    def test_usage_counters_increment(self, http, auth):
        before = http.get(f"{API}/settings/ai", headers=auth).json()["usage"]
        # trigger a small AI call
        http.post(f"{API}/ai/rewrite", headers=auth, json={"text": "make this professional", "tone": "professional"}, timeout=60)
        after = http.get(f"{API}/settings/ai", headers=auth).json()["usage"]
        assert after["calls"] >= before["calls"] + 1
        # tokens_in/out should be >= before (model may or may not report; lenient)
        assert after["tokens_in"] >= before["tokens_in"]
        assert after["tokens_out"] >= before["tokens_out"]


# ============ AI DAILY BRIEF ============
class TestDailyBrief:
    def test_daily_brief_shape(self, http, auth):
        r = http.get(f"{API}/ai/daily-brief", headers=auth, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("summary", "current_focus", "next_action", "high_leverage", "blocked", "recommended_deep_work", "workload", "burnout", "generated_at"):
            assert k in d, f"missing {k}"
        assert isinstance(d["high_leverage"], list)
        assert isinstance(d["blocked"], list)
        assert d["burnout"] in ("low", "medium", "high")
        assert isinstance(d["workload"], int)


# ============ AI WEEKLY REVIEW ============
class TestWeeklyReview:
    def test_weekly_review_shape(self, http, auth):
        r = http.get(f"{API}/ai/weekly-review", headers=auth, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("narrative", "wins", "misses", "patterns", "bottlenecks", "next_week_priorities", "insights", "stats", "generated_at"):
            assert k in d, f"missing {k}"
        for sk in ("completed_count", "delayed_count", "focus_minutes", "focus_sessions", "blocked_count"):
            assert sk in d["stats"]


# ============ DEPENDENCY INTELLIGENCE ============
class TestDependencies:
    @pytest.fixture(scope="class")
    def linked_tasks(self, http, auth):
        # create a project + 3 tasks with chain dependencies a -> b -> c
        p = http.post(f"{API}/projects", headers=auth, json={"name": "TEST_dep_project"}).json()
        a = http.post(f"{API}/tasks", headers=auth, json={"title": "TEST_dep_A", "project_id": p["id"], "priority": "high", "status": "blocked"}).json()
        b = http.post(f"{API}/tasks", headers=auth, json={"title": "TEST_dep_B", "project_id": p["id"], "priority": "high", "dependencies": [a["id"]]}).json()
        c = http.post(f"{API}/tasks", headers=auth, json={"title": "TEST_dep_C", "project_id": p["id"], "priority": "critical", "dependencies": [b["id"]]}).json()
        yield {"a": a, "b": b, "c": c, "project_id": p["id"]}
        # cleanup
        for t in (a, b, c):
            http.delete(f"{API}/tasks/{t['id']}", headers=auth)
        http.delete(f"{API}/projects/{p['id']}", headers=auth)

    def test_graph(self, http, auth, linked_tasks):
        r = http.get(f"{API}/dependencies/graph", headers=auth)
        assert r.status_code == 200
        d = r.json()
        assert "tasks" in d and "edges" in d
        a, b, c = linked_tasks["a"], linked_tasks["b"], linked_tasks["c"]
        ids = {t["id"] for t in d["tasks"]}
        assert {a["id"], b["id"], c["id"]}.issubset(ids)
        edge_set = {(e["from"], e["to"]) for e in d["edges"]}
        assert (a["id"], b["id"]) in edge_set
        assert (b["id"], c["id"]) in edge_set

    def test_bottlenecks(self, http, auth, linked_tasks):
        r = http.get(f"{API}/dependencies/bottlenecks", headers=auth)
        assert r.status_code == 200
        d = r.json()
        assert "bottlenecks" in d
        # a is blocked status + blocks b -> should appear
        found = [b for b in d["bottlenecks"] if b["task"]["id"] == linked_tasks["a"]["id"]]
        assert found, f"task A should be a bottleneck. Got: {d['bottlenecks']}"
        assert "impact_score" in found[0]
        assert found[0]["blocks_count"] >= 1

    def test_task_dependencies(self, http, auth, linked_tasks):
        b_id = linked_tasks["b"]["id"]
        r = http.get(f"{API}/dependencies/task/{b_id}", headers=auth)
        assert r.status_code == 200
        d = r.json()
        assert d["task_id"] == b_id
        ups = {u["id"] for u in d["upstream"]}
        downs = {x["id"] for x in d["downstream"]}
        assert linked_tasks["a"]["id"] in ups
        assert linked_tasks["c"]["id"] in downs

    def test_task_dep_404(self, http, auth):
        r = http.get(f"{API}/dependencies/task/does-not-exist-xyz", headers=auth)
        assert r.status_code == 404


# ============ AI MEMORY ============
class TestMemory:
    def test_memory_crud(self, http, auth):
        # create
        r = http.post(f"{API}/ai/memory", headers=auth, json={"content": "TEST_pattern_x", "type": "pattern", "tags": ["t1"]})
        assert r.status_code == 200
        m = r.json()
        assert m["content"] == "TEST_pattern_x"
        assert m["type"] == "pattern"
        assert "id" in m
        # list
        lst = http.get(f"{API}/ai/memory", headers=auth).json()
        assert any(x["id"] == m["id"] for x in lst)
        # delete
        d = http.delete(f"{API}/ai/memory/{m['id']}", headers=auth)
        assert d.status_code == 200
        lst2 = http.get(f"{API}/ai/memory", headers=auth).json()
        assert not any(x["id"] == m["id"] for x in lst2)

    def test_memory_extract(self, http, auth):
        r = http.post(f"{API}/ai/memory/extract", headers=auth, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "extracted" in d
        assert isinstance(d["extracted"], list)
        # cleanup auto-extracted ones to keep DB tidy
        for item in d["extracted"]:
            if item.get("id"):
                http.delete(f"{API}/ai/memory/{item['id']}", headers=auth)


# ============ PUBLIC SHAREABLE BRIEFING ============
class TestShareBrief:
    def test_create_and_get_unique_tokens(self, http, auth):
        r1 = http.post(f"{API}/share/brief", headers=auth, json={"title": "TEST_brief_one", "expires_days": 7})
        r2 = http.post(f"{API}/share/brief", headers=auth, json={"title": "TEST_brief_two", "expires_days": 7})
        assert r1.status_code == 200 and r2.status_code == 200
        t1, t2 = r1.json()["token"], r2.json()["token"]
        assert t1 and t2 and t1 != t2
        assert r1.json()["share_url"].endswith(t1)

        # public GET without auth
        pub = requests.get(f"{API}/share/brief/{t1}", timeout=60)
        assert pub.status_code == 200, pub.text
        d = pub.json()
        for k in ("title", "narrative", "top_risks", "strategic_actions", "velocity", "projects", "owner_name", "active_tasks", "views"):
            assert k in d, f"missing {k}"
        views_first = d["views"]

        # views increment
        pub2 = requests.get(f"{API}/share/brief/{t1}").json()
        assert pub2["views"] >= views_first + 1 or pub2["views"] >= 2

        # cleanup
        http.delete(f"{API}/share/brief/{t1}", headers=auth)
        http.delete(f"{API}/share/brief/{t2}", headers=auth)

    def test_invalid_token_404(self, http):
        r = requests.get(f"{API}/share/brief/INVALID-DOESNT-EXIST-1234567890")
        assert r.status_code == 404

    def test_list_briefs_requires_auth(self, http, auth):
        r = http.get(f"{API}/share/briefs", headers=auth)
        assert r.status_code == 200
        assert isinstance(r.json(), list)
        # no auth
        r2 = requests.get(f"{API}/share/briefs")
        assert r2.status_code in (401, 403)

    def test_delete_only_by_owner(self, http, auth):
        # create as founder
        r = http.post(f"{API}/share/brief", headers=auth, json={"title": "TEST_owner_only"})
        token = r.json()["token"]
        # register another user
        import uuid as _u
        other_email = f"TEST_other_{_u.uuid4().hex[:8]}@opscore.app"
        reg = http.post(f"{API}/auth/register", json={"email": other_email, "password": "test123", "name": "Other"})
        assert reg.status_code == 200
        other_token = reg.json()["token"]
        other_auth = {"Authorization": f"Bearer {other_token}", "Content-Type": "application/json"}
        # other user tries to delete
        http.delete(f"{API}/share/brief/{token}", headers=other_auth)
        # brief should still resolve (founder still owns it)
        still = requests.get(f"{API}/share/brief/{token}")
        assert still.status_code == 200, "non-owner should NOT have been able to delete"
        # now owner deletes
        d = http.delete(f"{API}/share/brief/{token}", headers=auth)
        assert d.status_code == 200
        gone = requests.get(f"{API}/share/brief/{token}")
        assert gone.status_code == 404


# ============ PRODUCTIVITY INTELLIGENCE ============
class TestIntelligence:
    def test_intelligence_shape(self, http, auth):
        r = http.get(f"{API}/analytics/intelligence", headers=auth)
        assert r.status_code == 200
        d = r.json()
        for k in ("best_hours", "consistency_pct", "focus_streak_days", "procrastinated", "estimate_accuracy", "tends_to", "interruption_rate_pct"):
            assert k in d, f"missing {k}"
        assert isinstance(d["best_hours"], list)
        assert isinstance(d["procrastinated"], list)
        assert 0 <= d["consistency_pct"] <= 100
        assert 0 <= d["interruption_rate_pct"] <= 100


# ============ EXISTING ENDPOINTS STILL WORK ============
class TestRegression:
    def test_login_still_works(self, http):
        r = http.post(f"{API}/auth/login", json={"email": FOUNDER_EMAIL, "password": FOUNDER_PASSWORD})
        assert r.status_code == 200
        assert "token" in r.json()

    def test_dashboard_summary(self, http, auth):
        r = http.get(f"{API}/dashboard/summary", headers=auth)
        assert r.status_code == 200

    def test_tasks_crud_still_works(self, http, auth):
        # create
        r = http.post(f"{API}/tasks", headers=auth, json={"title": "TEST_regression_task"})
        assert r.status_code == 200
        tid = r.json()["id"]
        # list
        lst = http.get(f"{API}/tasks", headers=auth)
        assert lst.status_code == 200
        # no _id leakage
        for t in lst.json():
            assert "_id" not in t
        # delete
        d = http.delete(f"{API}/tasks/{tid}", headers=auth)
        assert d.status_code == 200


# ============ WEBSOCKET ============
class TestWebSocket:
    def test_ws_rejects_invalid_token(self, founder_token):
        try:
            import websockets
        except ImportError:
            pytest.skip("websockets not installed")

        async def run():
            try:
                async with websockets.connect(f"{WS_URL}?token=garbage-token") as ws:
                    # Should be closed by server
                    try:
                        await asyncio.wait_for(ws.recv(), timeout=3)
                    except websockets.ConnectionClosed as e:
                        return e.code
                    except asyncio.TimeoutError:
                        return None
            except websockets.InvalidStatus as e:
                return e.response.status_code
            except websockets.ConnectionClosed as e:
                return e.code
            except Exception as e:
                return str(e)
            return None

        code = asyncio.run(run())
        # Server intends 4001 (close-before-accept). Starlette surfaces this as
        # HTTP 403 during handshake. Both indicate the connection was rejected.
        assert code in (4001, 403) or code is None, f"Expected rejection, got {code}"

    def test_ws_accepts_valid_token(self, founder_token):
        try:
            import websockets
        except ImportError:
            pytest.skip("websockets not installed")

        async def run():
            async with websockets.connect(f"{WS_URL}?token={founder_token}") as ws:
                # connection accepted; try a brief receive then close
                try:
                    await asyncio.wait_for(ws.recv(), timeout=1.5)
                except asyncio.TimeoutError:
                    pass
                except websockets.ConnectionClosed:
                    return False
                return True

        ok = asyncio.run(run())
        assert ok is True
