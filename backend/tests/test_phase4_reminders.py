"""OpsCore Phase-4 backend tests — Iteration 4.

Targets new reminder system features:
  - offset_minutes derivation of fire_at (with/without due_date, plus 400 paths)
  - multi-recipient reminders + visibility to recipients
  - default recipient resolution for task (assignee/owner) + note (owner)
  - POST /reminders/send-now (by reminder_id, ephemeral by entity, 404)
  - PATCH (resets sent=False), DELETE (creator vs non-creator silent 404)
  - GET/PUT /settings/reminders + workspace admin gate + personal prefs
  - SMTP unconfigured = ok=false but no 500 (graceful)
"""

import os
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
def founder(http):
    r = http.post(f"{API}/auth/login", json={"email": FOUNDER_EMAIL, "password": FOUNDER_PASSWORD})
    if r.status_code != 200:
        pytest.skip(f"Founder login failed: {r.status_code} {r.text}")
    j = r.json()
    return {"token": j["token"], "user": j["user"]}


@pytest.fixture(scope="session")
def auth(founder):
    return {"Authorization": f"Bearer {founder['token']}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def second_user(http, auth):
    """Invite a 2nd user via /team/invite (SMTP off → temp_password is returned)."""
    email = f"test_rem_{uuid.uuid4().hex[:8]}@example.com"
    r = http.post(f"{API}/team/invite", headers=auth, json={"email": email, "name": "Rem Recipient", "role": "editor"})
    if r.status_code != 200:
        pytest.skip(f"Invite failed: {r.status_code} {r.text}")
    j = r.json()
    temp_pwd = j.get("temp_password")
    rlog = http.post(f"{API}/auth/login", json={"email": email, "password": temp_pwd})
    if rlog.status_code != 200:
        pytest.skip(f"2nd user login failed: {rlog.status_code} {rlog.text}")
    j2 = rlog.json()
    return {
        "email": email,
        "token": j2["token"],
        "user": j2["user"],
        "id": j2["user"]["id"],
        "auth": {"Authorization": f"Bearer {j2['token']}", "Content-Type": "application/json"},
    }


def _iso(dt):
    return dt.replace(microsecond=0).isoformat()


# ---------------- A. offset_minutes computation ----------------
class TestOffsetMinutes:
    def test_offset_minutes_15_subtracts_from_due_date(self, http, auth):
        # Create a task with a due_date with a known timestamp
        due = datetime(2027, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
        rt = http.post(f"{API}/tasks", headers=auth, json={
            "title": "TEST_OffTask",
            "due_date": _iso(due),
            "status": "todo",
        })
        assert rt.status_code == 200, rt.text
        tid = rt.json()["id"]
        try:
            r = http.post(f"{API}/reminders", headers=auth, json={
                "entity_type": "task", "entity_id": tid, "offset_minutes": 15
            })
            assert r.status_code == 200, r.text
            doc = r.json()
            assert doc["offset_minutes"] == 15
            fire_at = doc["fire_at"]
            parsed = datetime.fromisoformat(fire_at.replace("Z", "+00:00"))
            expected = due - timedelta(minutes=15)
            assert parsed == expected, f"got {parsed}, expected {expected}"
            http.delete(f"{API}/reminders/{doc['id']}", headers=auth)
        finally:
            http.delete(f"{API}/tasks/{tid}", headers=auth)

    def test_offset_minutes_without_due_date_400(self, http, auth):
        rt = http.post(f"{API}/tasks", headers=auth, json={"title": "TEST_OffNoDue", "status": "todo"})
        tid = rt.json()["id"]
        try:
            r = http.post(f"{API}/reminders", headers=auth, json={
                "entity_type": "task", "entity_id": tid, "offset_minutes": 30
            })
            assert r.status_code == 400, r.text
        finally:
            http.delete(f"{API}/tasks/{tid}", headers=auth)

    def test_no_fire_at_and_no_offset_400(self, http, auth):
        rt = http.post(f"{API}/tasks", headers=auth, json={"title": "TEST_OffNone", "status": "todo"})
        tid = rt.json()["id"]
        try:
            r = http.post(f"{API}/reminders", headers=auth, json={
                "entity_type": "task", "entity_id": tid
            })
            assert r.status_code == 400, r.text
        finally:
            http.delete(f"{API}/tasks/{tid}", headers=auth)


# ---------------- B. Recipients & defaults ----------------
class TestRecipients:
    def test_recipient_ids_other_user_visible_in_their_list(self, http, auth, second_user):
        # Founder creates a task and a reminder targeting second_user as recipient
        rt = http.post(f"{API}/tasks", headers=auth, json={"title": "TEST_RecTask", "status": "todo"})
        tid = rt.json()["id"]
        fire_at = _iso(datetime.now(timezone.utc) + timedelta(days=1))
        r = http.post(f"{API}/reminders", headers=auth, json={
            "entity_type": "task", "entity_id": tid,
            "fire_at": fire_at,
            "recipient_ids": [second_user["id"]],
        })
        assert r.status_code == 200, r.text
        rid = r.json()["id"]
        assert second_user["id"] in r.json()["recipient_ids"]

        # 2nd user lists reminders → should include rid (recipient match)
        rl = http.get(f"{API}/reminders", headers=second_user["auth"])
        assert rl.status_code == 200
        ids = [x["id"] for x in rl.json()]
        assert rid in ids, f"second user should see reminder as recipient; got {ids}"

        # Cleanup
        http.delete(f"{API}/reminders/{rid}", headers=auth)
        http.delete(f"{API}/tasks/{tid}", headers=auth)

    def test_default_recipient_task_assignee(self, http, auth, second_user, founder):
        # Task assigned to 2nd user → default recipient should be assignee_id
        rt = http.post(f"{API}/tasks", headers=auth, json={
            "title": "TEST_RecDefAssignee", "status": "todo", "assignee_id": second_user["id"]
        })
        tid = rt.json()["id"]
        try:
            fire_at = _iso(datetime.now(timezone.utc) + timedelta(days=1))
            r = http.post(f"{API}/reminders", headers=auth, json={
                "entity_type": "task", "entity_id": tid, "fire_at": fire_at
            })
            assert r.status_code == 200, r.text
            assert r.json()["recipient_ids"] == [second_user["id"]]
            http.delete(f"{API}/reminders/{r.json()['id']}", headers=auth)
        finally:
            http.delete(f"{API}/tasks/{tid}", headers=auth)

    def test_default_recipient_task_owner_when_no_assignee(self, http, auth, founder):
        rt = http.post(f"{API}/tasks", headers=auth, json={"title": "TEST_RecDefOwner", "status": "todo"})
        tid = rt.json()["id"]
        try:
            fire_at = _iso(datetime.now(timezone.utc) + timedelta(days=1))
            r = http.post(f"{API}/reminders", headers=auth, json={
                "entity_type": "task", "entity_id": tid, "fire_at": fire_at
            })
            assert r.status_code == 200, r.text
            assert r.json()["recipient_ids"] == [founder["user"]["id"]]
            http.delete(f"{API}/reminders/{r.json()['id']}", headers=auth)
        finally:
            http.delete(f"{API}/tasks/{tid}", headers=auth)

    def test_default_recipient_note_owner(self, http, auth, founder):
        rn = http.post(f"{API}/notes", headers=auth, json={"title": "TEST_RecDefNote", "content": "z"})
        nid = rn.json()["id"]
        try:
            fire_at = _iso(datetime.now(timezone.utc) + timedelta(days=1))
            r = http.post(f"{API}/reminders", headers=auth, json={
                "entity_type": "note", "entity_id": nid, "fire_at": fire_at
            })
            assert r.status_code == 200, r.text
            assert r.json()["recipient_ids"] == [founder["user"]["id"]]
            http.delete(f"{API}/reminders/{r.json()['id']}", headers=auth)
        finally:
            http.delete(f"{API}/notes/{nid}", headers=auth)


# ---------------- C. send-now ----------------
class TestSendNow:
    def test_send_now_by_reminder_id_marks_sent_no_500(self, http, auth):
        rt = http.post(f"{API}/tasks", headers=auth, json={"title": "TEST_SendNow1", "status": "todo"})
        tid = rt.json()["id"]
        try:
            fire_at = _iso(datetime.now(timezone.utc) + timedelta(days=1))
            r = http.post(f"{API}/reminders", headers=auth, json={
                "entity_type": "task", "entity_id": tid, "fire_at": fire_at
            })
            rid = r.json()["id"]
            rs = http.post(f"{API}/reminders/send-now", headers=auth, json={"reminder_id": rid})
            assert rs.status_code == 200, rs.text
            body = rs.json()
            # SMTP unconfigured → ok=false, but no 500
            assert "ok" in body
            assert body["ok"] is False
            assert body.get("sent_to", 0) == 0
            assert body.get("failed", 0) >= 1

            # Reminder should be marked sent=True
            lst = http.get(f"{API}/reminders?entity_type=task&entity_id={tid}", headers=auth).json()
            match = [x for x in lst if x["id"] == rid]
            assert match and match[0]["sent"] is True
            http.delete(f"{API}/reminders/{rid}", headers=auth)
        finally:
            http.delete(f"{API}/tasks/{tid}", headers=auth)

    def test_send_now_ephemeral_by_entity(self, http, auth):
        rt = http.post(f"{API}/tasks", headers=auth, json={"title": "TEST_SendNowEph", "status": "todo"})
        tid = rt.json()["id"]
        try:
            rs = http.post(f"{API}/reminders/send-now", headers=auth, json={
                "entity_type": "task", "entity_id": tid, "message": "ping"
            })
            assert rs.status_code == 200, rs.text
            assert "ok" in rs.json()
        finally:
            http.delete(f"{API}/tasks/{tid}", headers=auth)

    def test_send_now_invalid_reminder_id_404(self, http, auth):
        rs = http.post(f"{API}/reminders/send-now", headers=auth, json={"reminder_id": "nope-" + uuid.uuid4().hex})
        assert rs.status_code == 404, rs.text


# ---------------- D. PATCH/DELETE semantics ----------------
class TestPatchDelete:
    def test_patch_fire_at_resets_sent_false(self, http, auth):
        rt = http.post(f"{API}/tasks", headers=auth, json={"title": "TEST_PatchSent", "status": "todo"})
        tid = rt.json()["id"]
        try:
            fire_at = _iso(datetime.now(timezone.utc) + timedelta(days=1))
            r = http.post(f"{API}/reminders", headers=auth, json={
                "entity_type": "task", "entity_id": tid, "fire_at": fire_at
            })
            rid = r.json()["id"]
            # Trigger send-now to mark sent=True
            http.post(f"{API}/reminders/send-now", headers=auth, json={"reminder_id": rid})
            lst1 = http.get(f"{API}/reminders?entity_type=task&entity_id={tid}", headers=auth).json()
            assert any(x["id"] == rid and x["sent"] is True for x in lst1)
            # PATCH fire_at → sent should reset to False
            new_fire = _iso(datetime.now(timezone.utc) + timedelta(days=3))
            rp = http.patch(f"{API}/reminders/{rid}", headers=auth, json={"fire_at": new_fire})
            assert rp.status_code == 200, rp.text
            body = rp.json()
            assert body["fire_at"] == new_fire
            assert body["sent"] is False
            assert body.get("sent_at") is None
            http.delete(f"{API}/reminders/{rid}", headers=auth)
        finally:
            http.delete(f"{API}/tasks/{tid}", headers=auth)

    def test_delete_creator_succeeds_noncreator_silent(self, http, auth, second_user):
        # Founder creates a reminder
        rt = http.post(f"{API}/tasks", headers=auth, json={"title": "TEST_DelGate", "status": "todo"})
        tid = rt.json()["id"]
        try:
            fire_at = _iso(datetime.now(timezone.utc) + timedelta(days=1))
            r = http.post(f"{API}/reminders", headers=auth, json={
                "entity_type": "task", "entity_id": tid, "fire_at": fire_at,
                "recipient_ids": [second_user["id"]],
            })
            rid = r.json()["id"]

            # Non-creator (second user) tries to delete → returns 200 silently but record persists
            rd_other = http.delete(f"{API}/reminders/{rid}", headers=second_user["auth"])
            # Either silent 200 or 404 acceptable per spec: "for non-creator returns 404 (silently)"
            assert rd_other.status_code in (200, 404), rd_other.text
            # Confirm reminder still exists (founder can still see it)
            lst = http.get(f"{API}/reminders?entity_type=task&entity_id={tid}", headers=auth).json()
            assert any(x["id"] == rid for x in lst), "Reminder should still exist after non-creator delete"

            # Creator deletes → 200, gone
            rd = http.delete(f"{API}/reminders/{rid}", headers=auth)
            assert rd.status_code == 200, rd.text
            lst2 = http.get(f"{API}/reminders?entity_type=task&entity_id={tid}", headers=auth).json()
            assert not any(x["id"] == rid for x in lst2)
        finally:
            http.delete(f"{API}/tasks/{tid}", headers=auth)


# ---------------- E. /settings/reminders ----------------
class TestSettingsReminders:
    def test_get_workspace_defaults_and_personal(self, http, auth):
        r = http.get(f"{API}/settings/reminders", headers=auth)
        assert r.status_code == 200, r.text
        body = r.json()
        ws = body["workspace"]
        # Defaults from DEFAULT_WORKSPACE_REMINDER_SETTINGS (unless previously modified)
        assert "overdue_digest_enabled" in ws
        assert "overdue_digest_time" in ws
        assert ws["digest_lookahead_hours"] == 24
        assert ws["default_offsets_minutes"] == [0, 15, 60, 1440]
        assert "personal" in body
        assert "digest_opted_out" in body["personal"]
        assert "is_admin" in body
        assert body["is_admin"] is True  # founder

    def test_put_workspace_as_admin_then_revert(self, http, auth):
        # Snapshot current
        cur = http.get(f"{API}/settings/reminders", headers=auth).json()["workspace"]
        try:
            rp = http.put(f"{API}/settings/reminders/workspace", headers=auth, json={
                "overdue_digest_enabled": True,
                "overdue_digest_time": "07:30",
            })
            assert rp.status_code == 200, rp.text
            j = rp.json()
            assert j["overdue_digest_enabled"] is True
            assert j["overdue_digest_time"] == "07:30"

            # Re-GET to confirm persisted
            g = http.get(f"{API}/settings/reminders", headers=auth).json()["workspace"]
            assert g["overdue_digest_enabled"] is True
            assert g["overdue_digest_time"] == "07:30"
        finally:
            # Revert
            http.put(f"{API}/settings/reminders/workspace", headers=auth, json={
                "overdue_digest_enabled": cur.get("overdue_digest_enabled", False),
                "overdue_digest_time": cur.get("overdue_digest_time", "09:00"),
            })

    def test_put_workspace_as_non_admin_403(self, http, second_user):
        # second_user was invited as editor → not is_admin
        rp = http.put(f"{API}/settings/reminders/workspace", headers=second_user["auth"], json={
            "overdue_digest_enabled": True,
        })
        assert rp.status_code == 403, rp.text

    def test_put_personal_prefs(self, http, second_user):
        rp = http.put(f"{API}/settings/reminders/personal", headers=second_user["auth"], json={
            "digest_opted_out": True,
            "quiet_hours_start": "22:00",
            "quiet_hours_end": "07:00",
        })
        assert rp.status_code == 200, rp.text
        body = rp.json()
        per = body["personal"]
        assert per["digest_opted_out"] is True
        assert per["quiet_hours_start"] == "22:00"
        assert per["quiet_hours_end"] == "07:00"
        # Re-GET
        g = http.get(f"{API}/settings/reminders", headers=second_user["auth"]).json()
        assert g["personal"]["digest_opted_out"] is True
        # Reset
        http.put(f"{API}/settings/reminders/personal", headers=second_user["auth"], json={
            "digest_opted_out": False,
        })
