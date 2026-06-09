"""OpsCore Phase-3 backend tests — Iteration 3.

Covers:
  - Auth: OTP/register-disabled/change-password/accept-invite
  - SMTP settings CRUD + test
  - Email templates CRUD/reset
  - Project sharing (roles, owner-only enforcement, member CRUD)
  - Team invite/list/revoke (with role)
  - Tasks: assignee email (no-500 path), scope=mine/all, project filter, day_of_week, non-member 403
  - Reminders CRUD (task/note)
  - Calendar events (create/list with synthetic task-* events, synthetic PATCH→400, DELETE)
  - Canvas/Graph CRUD
  - Security headers
"""

import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL"):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break
API = f"{BASE_URL}/api"

FOUNDER_EMAIL = "founder@opscore.app"
FOUNDER_PASSWORD = "test123"


# ---------------- fixtures ----------------
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


# ============ AUTH ============
class TestAuthV3:
    def test_login_returns_token_and_session_hours_when_no_smtp(self, http):
        r = http.post(f"{API}/auth/login", json={"email": FOUNDER_EMAIL, "password": FOUNDER_PASSWORD})
        assert r.status_code == 200, r.text
        d = r.json()
        # When SMTP not configured, we must get direct token (no OTP)
        assert d.get("otp_required") is False
        assert "token" in d and len(d["token"]) > 20
        assert d.get("session_hours") == 6
        assert d["user"]["email"] == FOUNDER_EMAIL
        assert "password_hash" not in d["user"]

    def test_register_disabled_403(self, http):
        email = f"TEST_reg_{uuid.uuid4().hex[:6]}@example.com"
        r = http.post(f"{API}/auth/register", json={"email": email, "password": "test1234", "name": "X"})
        # ALLOW_REGISTRATION=false in env
        assert r.status_code == 403, r.text

    def test_otp_verify_invalid_id_404(self, http):
        r = http.post(f"{API}/auth/otp/verify", json={"otp_id": "nope-" + uuid.uuid4().hex, "code": "000000"})
        assert r.status_code == 404, r.text

    def test_accept_invite_invalid_token_404(self, http):
        r = http.post(f"{API}/auth/accept-invite", json={"token": "bad_" + uuid.uuid4().hex, "temp_password": "x"})
        assert r.status_code == 404, r.text

    def test_change_password_wrong_current_400(self, http, auth):
        r = http.post(f"{API}/auth/change-password", headers=auth,
                      json={"current_password": "WRONG", "new_password": "newpass123"})
        assert r.status_code == 400

    def test_change_password_short_new_pwd_blocked(self, http, auth):
        # pydantic min_length=8 → 422; if not strict, server still returns 400 from len check
        r = http.post(f"{API}/auth/change-password", headers=auth,
                      json={"current_password": FOUNDER_PASSWORD, "new_password": "short"})
        assert r.status_code in (400, 422)

    def test_change_password_success_on_invitee(self, http, auth):
        """Use a fresh invitee user (not founder) to avoid clobbering shared credentials.
        Founder password is seeded shorter than the 8-char minimum and cannot be
        round-tripped through the API.
        """
        email = f"test_chpwd_{uuid.uuid4().hex[:6]}@example.com"
        inv = http.post(f"{API}/team/invite", headers=auth, json={"email": email, "name": "Pwd"}).json()
        temp_pwd = inv["temp_password"]
        # login
        rlog = http.post(f"{API}/auth/login", json={"email": email, "password": temp_pwd})
        assert rlog.status_code == 200, rlog.text
        h = {"Authorization": f"Bearer {rlog.json()['token']}", "Content-Type": "application/json"}
        # change
        new_pwd = "newSecret123"
        rc = http.post(f"{API}/auth/change-password", headers=h,
                       json={"current_password": temp_pwd, "new_password": new_pwd})
        assert rc.status_code == 200, rc.text
        assert rc.json().get("ok") is True
        # verify new password works
        rlog2 = http.post(f"{API}/auth/login", json={"email": email, "password": new_pwd})
        assert rlog2.status_code == 200, rlog2.text


# ============ SMTP SETTINGS ============
class TestSMTP:
    def test_smtp_get_default(self, http, auth):
        r = http.get(f"{API}/settings/smtp", headers=auth)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("host", "port", "username", "from_email", "use_tls", "start_tls", "enabled", "has_password"):
            assert k in d
        assert d["port"] >= 0

    def test_smtp_put_then_has_password_true(self, http, auth):
        payload = {
            "host": "smtp.example.com",
            "port": 587,
            "username": "test@example.com",
            "password": "TEST_secret_pwd",
            "from_email": "no-reply@example.com",
            "start_tls": True,
            "use_tls": False,
            "enabled": True,
        }
        r = http.put(f"{API}/settings/smtp", headers=auth, json=payload)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["host"] == "smtp.example.com"
        assert d["from_email"] == "no-reply@example.com"
        assert d["has_password"] is True
        # GET roundtrip
        r2 = http.get(f"{API}/settings/smtp", headers=auth)
        assert r2.status_code == 200
        assert r2.json()["has_password"] is True
        # NEVER leak raw password
        assert "password" not in r2.json()
        assert "password_encrypted" not in r2.json()
        # cleanup → clear host so login falls back to direct token (so OTHER tests work)
        rcl = http.put(f"{API}/settings/smtp", headers=auth, json={"host": "", "password": ""})
        assert rcl.status_code == 200
        assert rcl.json()["host"] == ""
        assert rcl.json()["has_password"] is False

    def test_smtp_test_returns_400_when_not_configured(self, http, auth):
        # ensure host cleared
        http.put(f"{API}/settings/smtp", headers=auth, json={"host": "", "password": ""})
        r = http.post(f"{API}/settings/smtp/test", headers=auth, json={"to": "x@example.com"})
        assert r.status_code == 400, r.text


# ============ EMAIL TEMPLATES ============
class TestEmailTemplates:
    def test_list_returns_4_keys(self, http, auth):
        r = http.get(f"{API}/settings/email-templates", headers=auth)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("otp", "invite", "task_assigned", "task_reminder"):
            assert k in d, f"missing template key {k}"
            assert "subject_ar" in d[k] and "subject_en" in d[k] and "html" in d[k]
            assert "is_default" in d[k]

    def test_put_override_then_reset(self, http, auth):
        body = {"key": "otp", "subject_en": "TEST_otp subject EN", "subject_ar": "TEST_otp AR", "html": "<p>CODE: {{otp}}</p>"}
        r = http.put(f"{API}/settings/email-templates", headers=auth, json=body)
        assert r.status_code == 200, r.text
        # verify saved
        r2 = http.get(f"{API}/settings/email-templates", headers=auth)
        assert r2.json()["otp"]["subject_en"] == "TEST_otp subject EN"
        assert r2.json()["otp"]["is_default"] is False
        # reset
        r3 = http.post(f"{API}/settings/email-templates/otp/reset", headers=auth)
        assert r3.status_code == 200, r3.text
        r4 = http.get(f"{API}/settings/email-templates", headers=auth)
        assert r4.json()["otp"]["is_default"] is True

    def test_put_unknown_key_400(self, http, auth):
        r = http.put(f"{API}/settings/email-templates", headers=auth, json={"key": "nope", "subject_en": "x"})
        assert r.status_code == 400


# ============ TEAM INVITE WITH ROLE ============
class TestTeamInviteRole:
    def test_invite_with_role_and_revoke(self, http, auth):
        email = f"test_inv_{uuid.uuid4().hex[:6]}@example.com"
        r = http.post(f"{API}/team/invite", headers=auth, json={"email": email, "name": "Tester", "role": "editor"})
        assert r.status_code == 200, r.text
        d = r.json()
        # backend normalises to lowercase
        assert d["email"] == email.lower()
        assert d["role"] == "editor"
        assert "invite_url" in d
        # SMTP not configured, so temp_password should be present for dev visibility
        assert d.get("emailed") is False
        assert "temp_password" in d
        iid = d["id"]

        # appears in invites list
        r2 = http.get(f"{API}/team/invites", headers=auth)
        assert r2.status_code == 200
        assert any(x["id"] == iid for x in r2.json())

        # revoke
        r3 = http.delete(f"{API}/team/invites/{iid}", headers=auth)
        assert r3.status_code == 200
        r4 = http.get(f"{API}/team/invites", headers=auth)
        rec = next((x for x in r4.json() if x["id"] == iid), None)
        assert rec and rec["status"] == "revoked"


# ============ PROJECT SHARING ============
@pytest.fixture(scope="class")
def shared_project(http, auth):
    r = http.post(f"{API}/projects", headers=auth, json={"name": "TEST_SharedProj_v3", "description": "share test"})
    pid = r.json()["id"]
    # my_role on list
    yield pid
    http.delete(f"{API}/projects/{pid}", headers=auth)


@pytest.fixture(scope="class")
def invitee_user(http, auth):
    """Create a real user via /team/invite so we can share a project with them."""
    email = f"test_inv_{uuid.uuid4().hex[:6]}@example.com"
    r = http.post(f"{API}/team/invite", headers=auth, json={"email": email, "name": "Invitee", "role": "viewer"})
    assert r.status_code == 200
    inv = r.json()
    return {"email": email.lower(), "user_id": inv["user_id"], "temp_password": inv["temp_password"]}


class TestProjectSharing:
    def test_list_projects_includes_my_role_field(self, http, auth, shared_project):
        r = http.get(f"{API}/projects", headers=auth)
        assert r.status_code == 200
        proj = next((p for p in r.json() if p["id"] == shared_project), None)
        assert proj is not None
        assert proj.get("my_role") == "owner"

    def test_share_with_editor_role(self, http, auth, shared_project, invitee_user):
        r = http.post(f"{API}/projects/{shared_project}/share", headers=auth,
                      json={"email": invitee_user["email"], "role": "editor"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["role"] == "editor"
        assert d["user_id"] == invitee_user["user_id"]

    def test_members_lists_owner_and_member(self, http, auth, shared_project, invitee_user):
        r = http.get(f"{API}/projects/{shared_project}/members", headers=auth)
        assert r.status_code == 200, r.text
        rows = r.json()
        roles_by_email = {u["email"]: u["role"] for u in rows}
        assert roles_by_email.get(FOUNDER_EMAIL) == "owner"
        assert roles_by_email.get(invitee_user["email"]) == "editor"

    def test_patch_member_role_to_viewer(self, http, auth, shared_project, invitee_user):
        r = http.patch(f"{API}/projects/{shared_project}/members/{invitee_user['user_id']}",
                       headers=auth, json={"role": "viewer"})
        assert r.status_code == 200, r.text
        r2 = http.get(f"{API}/projects/{shared_project}/members", headers=auth)
        roles_by_email = {u["email"]: u["role"] for u in r2.json()}
        assert roles_by_email[invitee_user["email"]] == "viewer"

    def test_non_owner_cannot_share_403(self, http, auth, shared_project, invitee_user):
        # log in as invitee using temp password
        rlog = http.post(f"{API}/auth/login", json={"email": invitee_user["email"], "password": invitee_user["temp_password"]})
        assert rlog.status_code == 200, rlog.text
        member_token = rlog.json()["token"]
        member_h = {"Authorization": f"Bearer {member_token}", "Content-Type": "application/json"}
        r = http.post(f"{API}/projects/{shared_project}/share", headers=member_h,
                      json={"email": "other@example.com", "role": "viewer"})
        assert r.status_code == 403, r.text

    def test_remove_member(self, http, auth, shared_project, invitee_user):
        r = http.delete(f"{API}/projects/{shared_project}/members/{invitee_user['user_id']}", headers=auth)
        assert r.status_code == 200
        r2 = http.get(f"{API}/projects/{shared_project}/members", headers=auth)
        emails = [u["email"] for u in r2.json()]
        assert invitee_user["email"] not in emails


# ============ TASKS — assignee email + scope + non-member access ============
class TestTaskAssignment:
    def test_create_task_with_assignee_no_500(self, http, auth, invitee_user):
        r = http.post(f"{API}/tasks", headers=auth, json={
            "title": "TEST_AssignedTask_v3",
            "status": "todo",
            "assignee_id": invitee_user["user_id"],
        })
        # SMTP not configured → email send should be skipped/failed gracefully
        assert r.status_code == 200, r.text
        t = r.json()
        assert t["assignee_id"] == invitee_user["user_id"]
        tid = t["id"]
        # PATCH change assignee back to founder
        r2 = http.patch(f"{API}/tasks/{tid}", headers=auth, json={"assignee_id": None})
        assert r2.status_code == 200, r2.text
        http.delete(f"{API}/tasks/{tid}", headers=auth)

    def test_tasks_scope_and_filters(self, http, auth):
        r = http.get(f"{API}/tasks?scope=mine", headers=auth)
        assert r.status_code == 200
        r2 = http.get(f"{API}/tasks?scope=all", headers=auth)
        assert r2.status_code == 200
        r3 = http.get(f"{API}/tasks?day_of_week=1", headers=auth)
        assert r3.status_code == 200

    def test_non_member_cannot_access_other_project_tasks(self, http, auth):
        # Create a fresh isolated user via invite
        email = f"test_outsider_{uuid.uuid4().hex[:6]}@example.com"
        inv = http.post(f"{API}/team/invite", headers=auth, json={"email": email, "name": "Outsider"}).json()
        rlog = http.post(f"{API}/auth/login", json={"email": email, "password": inv["temp_password"]})
        assert rlog.status_code == 200
        outsider_h = {"Authorization": f"Bearer {rlog.json()['token']}", "Content-Type": "application/json"}

        # Founder-only project
        proj = http.post(f"{API}/projects", headers=auth, json={"name": "TEST_PrivateProj"}).json()
        try:
            r = http.get(f"{API}/tasks?project_id={proj['id']}", headers=outsider_h)
            assert r.status_code == 403, r.text
        finally:
            http.delete(f"{API}/projects/{proj['id']}", headers=auth)


# ============ REMINDERS ============
class TestReminders:
    @pytest.fixture(scope="class")
    def task_id(self, http, auth):
        r = http.post(f"{API}/tasks", headers=auth, json={"title": "TEST_ReminderTask", "status": "todo"})
        tid = r.json()["id"]
        yield tid
        http.delete(f"{API}/tasks/{tid}", headers=auth)

    @pytest.fixture(scope="class")
    def note_id(self, http, auth):
        r = http.post(f"{API}/notes", headers=auth, json={"title": "TEST_ReminderNote", "content": "x"})
        nid = r.json()["id"]
        yield nid
        http.delete(f"{API}/notes/{nid}", headers=auth)

    def test_reminder_task_crud(self, http, auth, task_id):
        fire_at = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        r = http.post(f"{API}/reminders", headers=auth, json={
            "entity_type": "task", "entity_id": task_id, "fire_at": fire_at, "message": "wake up"
        })
        assert r.status_code == 200, r.text
        rid = r.json()["id"]
        assert r.json()["entity_id"] == task_id
        # list
        rl = http.get(f"{API}/reminders?entity_type=task&entity_id={task_id}", headers=auth)
        assert rl.status_code == 200
        assert any(x["id"] == rid for x in rl.json())
        # patch
        new_fire = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        rp = http.patch(f"{API}/reminders/{rid}", headers=auth, json={"fire_at": new_fire})
        assert rp.status_code == 200
        assert rp.json()["fire_at"] == new_fire
        # delete
        rd = http.delete(f"{API}/reminders/{rid}", headers=auth)
        assert rd.status_code == 200

    def test_reminder_note_crud(self, http, auth, note_id):
        fire_at = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        r = http.post(f"{API}/reminders", headers=auth, json={
            "entity_type": "note", "entity_id": note_id, "fire_at": fire_at,
        })
        assert r.status_code == 200, r.text
        rid = r.json()["id"]
        http.delete(f"{API}/reminders/{rid}", headers=auth)

    def test_reminder_invalid_entity_400(self, http, auth, task_id):
        r = http.post(f"{API}/reminders", headers=auth, json={
            "entity_type": "wrong", "entity_id": task_id,
            "fire_at": datetime.now(timezone.utc).isoformat(),
        })
        assert r.status_code == 400


# ============ CALENDAR ============
class TestCalendar:
    def test_create_list_synthetic_delete(self, http, auth):
        # Make a scheduled task → should appear as task-* synthetic event
        today = datetime.now(timezone.utc).date().isoformat()
        rt = http.post(f"{API}/tasks", headers=auth, json={
            "title": "TEST_CalSyntheticTask", "scheduled_for": today, "status": "todo"
        })
        tid = rt.json()["id"]

        # user-created event
        body = {
            "title": "TEST_CalEvent",
            "start": f"{today}T11:00:00+00:00",
            "end": f"{today}T12:00:00+00:00",
            "type": "event",
        }
        rc = http.post(f"{API}/calendar/events", headers=auth, json=body)
        assert rc.status_code == 200, rc.text
        eid = rc.json()["id"]

        rl = http.get(f"{API}/calendar/events", headers=auth)
        assert rl.status_code == 200
        ids = [e["id"] for e in rl.json()]
        assert eid in ids
        assert any(i.startswith("task-") for i in ids), "Expected synthetic task-* events in calendar list"

        # PATCH synthetic → 400
        rps = http.patch(f"{API}/calendar/events/task-{tid}", headers=auth, json={"title": "no"})
        assert rps.status_code == 400, rps.text

        # PATCH real event ok
        rpr = http.patch(f"{API}/calendar/events/{eid}", headers=auth, json={"title": "TEST_CalEvent_renamed"})
        assert rpr.status_code == 200

        # DELETE real
        rd = http.delete(f"{API}/calendar/events/{eid}", headers=auth)
        assert rd.status_code == 200

        http.delete(f"{API}/tasks/{tid}", headers=auth)


# ============ CANVAS / GRAPH ============
class TestCanvas:
    def test_canvas_full_crud(self, http, auth):
        r = http.post(f"{API}/canvases", headers=auth, json={
            "name": "TEST_Canvas_v3",
            "nodes": [{"id": "n1", "position": {"x": 0, "y": 0}, "data": {"label": "A"}}],
            "edges": [],
        })
        assert r.status_code == 200, r.text
        cid = r.json()["id"]
        assert r.json()["name"] == "TEST_Canvas_v3"
        assert "_id" not in r.json()

        # list with counts
        rl = http.get(f"{API}/canvases", headers=auth)
        assert rl.status_code == 200
        row = next((c for c in rl.json() if c["id"] == cid), None)
        assert row is not None
        assert row.get("node_count") == 1
        assert row.get("edge_count") == 0

        # get
        rg = http.get(f"{API}/canvases/{cid}", headers=auth)
        assert rg.status_code == 200
        assert len(rg.json()["nodes"]) == 1

        # patch — add edge & node
        rp = http.patch(f"{API}/canvases/{cid}", headers=auth, json={
            "nodes": [
                {"id": "n1", "position": {"x": 0, "y": 0}, "data": {"label": "A"}},
                {"id": "n2", "position": {"x": 200, "y": 0}, "data": {"label": "B"}},
            ],
            "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
        })
        assert rp.status_code == 200
        rg2 = http.get(f"{API}/canvases/{cid}", headers=auth)
        assert len(rg2.json()["nodes"]) == 2
        assert len(rg2.json()["edges"]) == 1

        # delete
        rd = http.delete(f"{API}/canvases/{cid}", headers=auth)
        assert rd.status_code == 200
        rg3 = http.get(f"{API}/canvases/{cid}", headers=auth)
        assert rg3.status_code == 404


# ============ SECURITY HEADERS ============
class TestSecurityHeaders:
    def test_security_headers_present(self, http):
        r = http.get(f"{API}/")
        assert r.status_code == 200
        h = {k.lower(): v for k, v in r.headers.items()}
        assert h.get("x-content-type-options", "").lower() == "nosniff"
        assert h.get("x-frame-options", "").upper() == "DENY"
        assert "referrer-policy" in h
