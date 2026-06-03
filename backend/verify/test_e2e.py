"""End-to-end functional verification against the real app + in-memory Mongo.

Covers: auth (positive/negative), invite security fix, projects, tasks, notes, files,
reminders, calendar, AI, realtime, security (CORS/headers/rate-limit), and persistence.
"""
import asyncio
from datetime import date, datetime, timezone, timedelta

import pytest

S = {}  # shared state across ordered tests


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


def run(coro):
    return asyncio.run(coro)


# ============ AUTH ============
def test_register_admin(client):
    r = client.post("/api/auth/register", json={"email": "admin@opscore.app", "password": "secret123", "name": "Admin"})
    assert r.status_code == 200, r.text
    S["admin_tok"] = r.json()["token"]
    S["admin_id"] = r.json()["user"]["id"]
    assert r.json()["user"]["is_admin"] is True


def test_register_duplicate_rejected(client):
    r = client.post("/api/auth/register", json={"email": "admin@opscore.app", "password": "secret123", "name": "Dup"})
    assert r.status_code == 400


def test_login_ok_and_jwt(client):
    r = client.post("/api/auth/login", json={"email": "admin@opscore.app", "password": "secret123"})
    assert r.status_code == 200, r.text
    assert r.json()["otp_required"] is False
    assert r.json()["token"]
    S["admin_tok"] = r.json()["token"]


def test_login_wrong_password(client):
    r = client.post("/api/auth/login", json={"email": "admin@opscore.app", "password": "WRONG"})
    assert r.status_code == 401


def test_me_requires_valid_token(client):
    assert client.get("/api/auth/me").status_code in (401, 403)            # missing
    assert client.get("/api/auth/me", headers=H("garbage.token")).status_code == 401  # invalid
    r = client.get("/api/auth/me", headers=H(S["admin_tok"]))             # valid
    assert r.status_code == 200 and r.json()["email"] == "admin@opscore.app"


def test_change_password(client):
    bad = client.post("/api/auth/change-password", json={"current_password": "WRONG", "new_password": "newsecret123"}, headers=H(S["admin_tok"]))
    assert bad.status_code == 400
    ok = client.post("/api/auth/change-password", json={"current_password": "secret123", "new_password": "newsecret123"}, headers=H(S["admin_tok"]))
    assert ok.status_code == 200
    # login with new password works; old fails
    assert client.post("/api/auth/login", json={"email": "admin@opscore.app", "password": "newsecret123"}).status_code == 200
    assert client.post("/api/auth/login", json={"email": "admin@opscore.app", "password": "secret123"}).status_code == 401


# ============ INVITE SECURITY FIX ============
def test_invite_new_user(client, db):
    r = client.post("/api/team/invite", json={"email": "member@opscore.app", "name": "Member", "role": "viewer"}, headers=H(S["admin_tok"]))
    assert r.status_code == 200, r.text
    assert r.json().get("existing_user") is False
    u = run(db.users.find_one({"email": "member@opscore.app"}))
    assert u and u["is_admin"] is False
    S["member_pwhash_before"] = u["password_hash"]


def test_invite_existing_user_does_not_reset_credentials(client, db):
    before = run(db.users.find_one({"email": "member@opscore.app"}))
    r = client.post("/api/team/invite", json={"email": "member@opscore.app", "role": "editor"}, headers=H(S["admin_tok"]))
    assert r.status_code == 200, r.text
    assert r.json().get("existing_user") is True
    after = run(db.users.find_one({"email": "member@opscore.app"}))
    # CRITICAL: password hash and must_change_password are UNCHANGED.
    assert after["password_hash"] == before["password_hash"]
    assert after.get("must_change_password") == before.get("must_change_password")


def test_invite_requires_admin(client, db):
    # Set a known password for the invited (non-admin) member so they can log in.
    from app.core.security import pwd_context
    run(db.users.update_one({"email": "member@opscore.app"},
                            {"$set": {"password_hash": pwd_context.hash("memberpass1"), "must_change_password": False}}))
    tok = client.post("/api/auth/login", json={"email": "member@opscore.app", "password": "memberpass1"}).json()["token"]
    S["member_tok"] = tok
    # Non-admin invite attempt -> 403
    r = client.post("/api/team/invite", json={"email": "newinvitee@opscore.app", "role": "viewer"}, headers=H(tok))
    assert r.status_code == 403


# ============ PROJECTS ============
def test_project_crud_and_progress(client):
    r = client.post("/api/projects", json={"name": "Proj A", "description": "d", "priority": "high",
                                           "milestones": [{"title": "M1"}]}, headers=H(S["admin_tok"]))
    assert r.status_code == 200, r.text
    pid = r.json()["id"]; S["pid"] = pid
    assert r.json()["milestones"] == [{"title": "M1"}]
    # edit
    assert client.patch(f"/api/projects/{pid}", json={"status": "active", "name": "Proj A2"}, headers=H(S["admin_tok"])).status_code == 200
    # two tasks, one done -> progress 50
    for st in ("todo", "done"):
        client.post("/api/tasks", json={"title": f"t-{st}", "project_id": pid, "status": st}, headers=H(S["admin_tok"]))
    g = client.get(f"/api/projects/{pid}", headers=H(S["admin_tok"])).json()
    assert g["progress"] == 50, g["progress"]
    lst = client.get("/api/projects", headers=H(S["admin_tok"])).json()
    assert any(p["id"] == pid and p["task_count"] == 2 for p in lst)


def test_project_sharing_and_permissions(client):
    pid = S["pid"]
    # share with member as viewer
    r = client.post(f"/api/projects/{pid}/share", json={"email": "member@opscore.app", "role": "viewer"}, headers=H(S["admin_tok"]))
    assert r.status_code == 200, r.text
    # member can view
    assert client.get(f"/api/projects/{pid}", headers=H(S["member_tok"])).status_code == 200
    # viewer cannot delete (admin-only) -> 403
    assert client.delete(f"/api/projects/{pid}", headers=H(S["member_tok"])).status_code == 403
    # members list includes both
    members = client.get(f"/api/projects/{pid}/members", headers=H(S["admin_tok"])).json()
    assert len(members) >= 2


# ============ TASKS ============
def test_task_lifecycle(client):
    pid = S["pid"]
    r = client.post("/api/tasks", json={"title": "Main task", "project_id": pid, "priority": "high"}, headers=H(S["admin_tok"]))
    assert r.status_code == 200
    tid = r.json()["id"]; S["tid"] = tid
    # status change -> completed_at set
    up = client.patch(f"/api/tasks/{tid}", json={"status": "done"}, headers=H(S["admin_tok"])).json()
    assert up["status"] == "done" and up["completed_at"]
    # assign to member
    asg = client.patch(f"/api/tasks/{tid}", json={"assignee_id": "member@x", "status": "todo"}, headers=H(S["admin_tok"]))
    assert asg.status_code == 200
    # get + delete
    assert client.get(f"/api/tasks/{tid}", headers=H(S["admin_tok"])).status_code == 200


def test_task_dependencies_and_search(client):
    pid = S["pid"]
    a = client.post("/api/tasks", json={"title": "Dep A", "project_id": pid}, headers=H(S["admin_tok"])).json()
    b = client.post("/api/tasks", json={"title": "FindMeXYZ", "project_id": pid, "dependencies": [a["id"]]}, headers=H(S["admin_tok"])).json()
    graph = client.get("/api/dependencies/graph", headers=H(S["admin_tok"])).json()
    assert {"from": a["id"], "to": b["id"]} in graph["edges"]
    found = client.get("/api/tasks?q=FindMeXYZ", headers=H(S["admin_tok"])).json()
    assert any(t["id"] == b["id"] for t in found)


def test_task_today_week_views(client):
    today = date.today().isoformat()
    t = client.post("/api/tasks", json={"title": "Pinned today", "scheduled_for": today}, headers=H(S["admin_tok"])).json()
    tv = client.get(f"/api/tasks?view=today&today={today}", headers=H(S["admin_tok"])).json()
    assert any(x["id"] == t["id"] for x in tv)
    wv = client.get(f"/api/tasks?view=week&today={today}", headers=H(S["admin_tok"])).json()
    assert any(x["id"] == t["id"] for x in wv)
    # today-hints endpoint (was previously shadowed) now returns data
    hints = client.get(f"/api/tasks/today-hints?today={today}", headers=H(S["admin_tok"]))
    assert hints.status_code == 200 and "overdue_unpinned" in hints.json()


def test_task_updates_log(client):
    tid = S["tid"]
    up = client.post(f"/api/tasks/{tid}/updates", json={"content": "progress note"}, headers=H(S["admin_tok"]))
    assert up.status_code == 200
    lst = client.get(f"/api/tasks/{tid}/updates", headers=H(S["admin_tok"])).json()
    assert len(lst) == 1
    assert client.delete(f"/api/tasks/{tid}/updates/{up.json()['id']}", headers=H(S["admin_tok"])).status_code == 200


def test_ai_breakdown_creates_subtasks(client):
    tid = S["tid"]
    r = client.post("/api/ai/breakdown", json={"task_id": tid}, headers=H(S["admin_tok"]))
    assert r.status_code == 200
    assert len(r.json()["subtasks"]) >= 1


# ============ NOTES ============
def test_notes_crud(client):
    pid = S["pid"]
    r = client.post("/api/notes", json={"title": "N1", "content": "body", "project_id": pid, "task_id": S["tid"], "tags": ["a", "b"]}, headers=H(S["admin_tok"]))
    assert r.status_code == 200
    nid = r.json()["id"]
    assert r.json()["tags"] == ["a", "b"]
    assert client.patch(f"/api/notes/{nid}", json={"content": "updated"}, headers=H(S["admin_tok"])).json()["content"] == "updated"
    assert client.get("/api/notes", headers=H(S["admin_tok"])).status_code == 200
    assert client.delete(f"/api/notes/{nid}", headers=H(S["admin_tok"])).status_code == 200


# ============ FILES ============
def test_files_upload_download_delete_and_perms(client):
    pid = S["pid"]
    up = client.post(f"/api/projects/{pid}/files", files={"file": ("hello.txt", b"hello world", "text/plain")}, headers=H(S["admin_tok"]))
    assert up.status_code == 200, up.text
    fid = up.json()["id"]
    dl = client.get(f"/api/projects/{pid}/files/{fid}/download", headers=H(S["admin_tok"]))
    assert dl.status_code == 200 and dl.content == b"hello world"
    # a non-member user cannot access
    client.post("/api/auth/register", json={"email": "outsider@opscore.app", "password": "outsider123", "name": "Out"})
    otok = client.post("/api/auth/login", json={"email": "outsider@opscore.app", "password": "outsider123"}).json()["token"]
    assert client.get(f"/api/projects/{pid}/files", headers=H(otok)).status_code == 404
    assert client.delete(f"/api/projects/{pid}/files/{fid}", headers=H(S["admin_tok"])).status_code == 200


# ============ REMINDERS ============
def test_reminder_offset_and_sendnow(client):
    due = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    t = client.post("/api/tasks", json={"title": "Rem task", "due_date": due}, headers=H(S["admin_tok"])).json()
    r = client.post("/api/reminders", json={"entity_type": "task", "entity_id": t["id"], "offset_minutes": 60}, headers=H(S["admin_tok"]))
    assert r.status_code == 200, r.text
    fire = datetime.fromisoformat(r.json()["fire_at"])
    expected = datetime.fromisoformat(due) - timedelta(minutes=60)
    assert abs((fire - expected).total_seconds()) < 2
    S["rem_id"] = r.json()["id"]
    assert client.get("/api/reminders", headers=H(S["admin_tok"])).status_code == 200
    # send-now with SMTP unconfigured -> ok False but NO 500
    sn = client.post("/api/reminders/send-now", json={"reminder_id": S["rem_id"]}, headers=H(S["admin_tok"]))
    assert sn.status_code == 200 and sn.json()["ok"] is False
    assert client.delete(f"/api/reminders/{S['rem_id']}", headers=H(S["admin_tok"])).status_code == 200


def test_reminder_settings(client):
    assert client.get("/api/settings/reminders", headers=H(S["admin_tok"])).status_code == 200
    # admin can set workspace digest config
    r = client.put("/api/settings/reminders/workspace", json={"overdue_digest_enabled": True, "overdue_digest_time": "09:00"}, headers=H(S["admin_tok"]))
    assert r.status_code == 200
    # bad time rejected
    assert client.put("/api/settings/reminders/workspace", json={"overdue_digest_time": "99:99"}, headers=H(S["admin_tok"])).status_code == 400


# ============ CALENDAR ============
def test_calendar_events_and_task_integration(client):
    start = (datetime.now(timezone.utc)).isoformat()
    end = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    ev = client.post("/api/calendar/events", json={"title": "Meeting", "start": start, "end": end}, headers=H(S["admin_tok"]))
    assert ev.status_code == 200
    eid = ev.json()["id"]
    assert client.patch(f"/api/calendar/events/{eid}", json={"title": "Meeting2"}, headers=H(S["admin_tok"])).json()["title"] == "Meeting2"
    # end<start rejected
    assert client.post("/api/calendar/events", json={"title": "bad", "start": end, "end": start}, headers=H(S["admin_tok"])).status_code == 400
    # synthetic task events present (task pinned today exists)
    evs = client.get("/api/calendar/events", headers=H(S["admin_tok"])).json()
    assert any(str(e["id"]).startswith("task-") for e in evs)
    assert client.delete(f"/api/calendar/events/{eid}", headers=H(S["admin_tok"])).status_code == 200


# ============ AI (stubbed model) ============
def test_ai_endpoints(client):
    chat = client.post("/api/ai/chat", json={"message": "hi"}, headers=H(S["admin_tok"]))
    assert chat.status_code == 200 and chat.json()["reply"]
    sid = chat.json()["session_id"]
    assert client.get(f"/api/ai/conversations/{sid}", headers=H(S["admin_tok"])).status_code == 200
    assert client.post("/api/ai/rewrite", json={"text": "raw"}, headers=H(S["admin_tok"])).status_code == 200
    assert client.get("/api/ai/daily-brief", headers=H(S["admin_tok"])).status_code == 200
    assert client.get("/api/ai/weekly-review", headers=H(S["admin_tok"])).status_code == 200
    assert client.get("/api/ai/prioritize", headers=H(S["admin_tok"])).status_code == 200
    assert client.post("/api/ai/summarize-project", json={"project_id": S["pid"]}, headers=H(S["admin_tok"])).status_code == 200
    m = client.post("/api/ai/memory", json={"content": "remember", "type": "note"}, headers=H(S["admin_tok"]))
    assert m.status_code == 200
    assert any(x["id"] == m.json()["id"] for x in client.get("/api/ai/memory", headers=H(S["admin_tok"])).json())
    assert client.delete(f"/api/ai/memory/{m.json()['id']}", headers=H(S["admin_tok"])).status_code == 200


# ============ DASHBOARD / ANALYTICS / FOCUS / NOTIFS / CANVAS / SHARE ============
def test_misc_read_endpoints(client):
    for url in ("/api/dashboard/summary", "/api/dashboard/greeting", "/api/analytics/overview",
                "/api/analytics/intelligence", "/api/notifications", "/api/timeline/insights"):
        assert client.get(url, headers=H(S["admin_tok"])).status_code == 200, url
    fs = client.post("/api/focus/sessions", json={"duration_minutes": 25, "completed": True}, headers=H(S["admin_tok"]))
    assert fs.status_code == 200
    cv = client.post("/api/canvases", json={"name": "C1", "nodes": [], "edges": []}, headers=H(S["admin_tok"]))
    assert cv.status_code == 200
    sb = client.post("/api/share/brief", json={"title": "Brief"}, headers=H(S["admin_tok"]))
    assert sb.status_code == 200
    tok = sb.json()["token"]
    assert client.get(f"/api/share/brief/{tok}").status_code == 200  # public, no auth


# ============ REALTIME / WEBSOCKET ============
def test_websocket_auth(client):
    from starlette.websockets import WebSocketDisconnect
    # valid token connects
    with client.websocket_connect(f"/api/ws?token={S['admin_tok']}") as ws:
        ws.send_text("ping")  # keepalive accepted
    # invalid token -> closed by server
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/ws?token=bad") as ws:
            ws.receive_text()


def test_broadcast_mechanics():
    from app.shared.websocket import ws_manager, broadcast

    class FakeWS:
        def __init__(self):
            self.sent = []
        async def send_json(self, payload):
            self.sent.append(payload)

    fake = FakeWS()
    ws_manager.connections.setdefault("u1", []).append(fake)
    run(broadcast("u1", "task.created", {"id": "x"}))
    assert fake.sent and fake.sent[0]["event"] == "task.created"
    ws_manager.connections["u1"].remove(fake)


# ============ SECURITY ============
def test_security_headers_and_cors(client):
    r = client.get("/api/", headers={"Origin": "http://localhost:3000"})
    assert r.headers.get("x-frame-options") == "DENY"
    assert r.headers.get("x-content-type-options") == "nosniff"
    # CORS reflects the allowed origin, not a wildcard
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_rate_limiting_active(client):
    from app.shared.rate_limit import limiter
    limiter.enabled = True
    try:
        codes = [client.post("/api/auth/login", json={"email": "nobody@opscore.app", "password": "x"}).status_code for _ in range(14)]
        assert 429 in codes, codes
    finally:
        limiter.enabled = False


# ============ PERSISTENCE ============
def test_persistence(client):
    # project created earlier is still retrievable (data persisted in the store)
    assert client.get(f"/api/projects/{S['pid']}", headers=H(S["admin_tok"])).status_code == 200
