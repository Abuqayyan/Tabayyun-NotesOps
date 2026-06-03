"""Tests for the dynamic language toggle feature (X-Lang header).

Verifies backend endpoints respect the X-Lang header and respond in the selected language:
- /dashboard/greeting (no AI; deterministic strings)
- /ai/daily-brief (Claude)
- /ai/weekly-review (Claude)
- /ai/prioritize (Claude)
- /ai/chat (Claude)
- /notifications (static title labels)
- /timeline/insights (static insight messages)
"""

import os
import re
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL"):
                    BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                    break
    except Exception:
        pass
API = f"{BASE_URL}/api"

EMAIL = "founder@opscore.app"
PASSWORD = "test123"

ARABIC_RE = re.compile(r"[\u0600-\u06FF]")


def has_arabic(text: str) -> bool:
    return bool(ARABIC_RE.search(text or ""))


def is_english_only(text: str) -> bool:
    # No Arabic letters present and at least one ASCII letter
    return (not has_arabic(text or "")) and bool(re.search(r"[A-Za-z]", text or ""))


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{API}/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def hdrs(token, lang):
    return {"Authorization": f"Bearer {token}", "X-Lang": lang, "Content-Type": "application/json"}


# ---------- /dashboard/greeting (fast, deterministic) ----------
class TestGreeting:
    def test_greeting_arabic(self, token):
        r = requests.get(f"{API}/dashboard/greeting", headers=hdrs(token, "ar"), timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert has_arabic(d.get("greeting", "")), f"Expected Arabic greeting, got: {d}"

    def test_greeting_english(self, token):
        r = requests.get(f"{API}/dashboard/greeting", headers=hdrs(token, "en"), timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        g = d.get("greeting", "")
        assert is_english_only(g), f"Expected English greeting, got: {d}"

    def test_greeting_default_is_arabic(self, token):
        # No X-Lang header -> defaults to ar
        h = {"Authorization": f"Bearer {token}"}
        r = requests.get(f"{API}/dashboard/greeting", headers=h, timeout=30)
        assert r.status_code == 200
        assert has_arabic(r.json().get("greeting", ""))


# ---------- /notifications (static labels localized) ----------
class TestNotifications:
    def test_notifications_arabic(self, token):
        r = requests.get(f"{API}/notifications", headers=hdrs(token, "ar"), timeout=30)
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)
        # If notifications exist, titles should be Arabic; if empty, still 200 OK
        for it in items:
            t = it.get("title", "")
            if t:
                assert has_arabic(t) or t == "", f"Non-Arabic notification title: {t}"

    def test_notifications_english(self, token):
        r = requests.get(f"{API}/notifications", headers=hdrs(token, "en"), timeout=30)
        assert r.status_code == 200
        items = r.json()
        for it in items:
            t = it.get("title", "")
            if t:
                assert is_english_only(t), f"Non-English notification title: {t}"


# ---------- /timeline/insights ----------
class TestTimelineInsights:
    def test_timeline_arabic(self, token):
        r = requests.get(f"{API}/timeline/insights", headers=hdrs(token, "ar"), timeout=30)
        assert r.status_code == 200
        d = r.json()
        msgs = d.get("messages") or d.get("insights") or []
        # If any messages exist, must be Arabic
        for m in msgs:
            txt = m if isinstance(m, str) else (m.get("text") or m.get("message") or "")
            if txt:
                assert has_arabic(txt), f"Non-Arabic insight: {txt}"

    def test_timeline_english(self, token):
        r = requests.get(f"{API}/timeline/insights", headers=hdrs(token, "en"), timeout=30)
        assert r.status_code == 200
        d = r.json()
        msgs = d.get("messages") or d.get("insights") or []
        for m in msgs:
            txt = m if isinstance(m, str) else (m.get("text") or m.get("message") or "")
            if txt:
                assert is_english_only(txt), f"Non-English insight: {txt}"


# ---------- AI: /ai/chat ----------
class TestAIChat:
    def test_chat_arabic(self, token):
        body = {"message": "Say hello in one short sentence."}
        r = requests.post(f"{API}/ai/chat", headers=hdrs(token, "ar"), json=body, timeout=90)
        assert r.status_code == 200, r.text
        reply = r.json().get("reply", "")
        assert has_arabic(reply), f"AI chat did not reply in Arabic. Got: {reply!r}"

    def test_chat_english(self, token):
        body = {"message": "قل مرحباً بجملة قصيرة."}
        r = requests.post(f"{API}/ai/chat", headers=hdrs(token, "en"), json=body, timeout=90)
        assert r.status_code == 200, r.text
        reply = r.json().get("reply", "")
        assert is_english_only(reply), f"AI chat did not reply in English. Got: {reply!r}"


# ---------- AI: /ai/daily-brief ----------
class TestDailyBrief:
    def test_daily_brief_arabic(self, token):
        r = requests.get(f"{API}/ai/daily-brief", headers=hdrs(token, "ar"), timeout=120)
        assert r.status_code == 200, r.text
        summary = r.json().get("summary", "")
        assert summary, "Empty daily-brief summary"
        assert has_arabic(summary), f"Daily brief not Arabic. Got: {summary[:160]!r}"

    def test_daily_brief_english(self, token):
        r = requests.get(f"{API}/ai/daily-brief", headers=hdrs(token, "en"), timeout=120)
        assert r.status_code == 200, r.text
        summary = r.json().get("summary", "")
        assert summary, "Empty daily-brief summary"
        assert is_english_only(summary), f"Daily brief not English. Got: {summary[:160]!r}"


# ---------- AI: /ai/weekly-review ----------
class TestWeeklyReview:
    def test_weekly_review_arabic(self, token):
        r = requests.get(f"{API}/ai/weekly-review", headers=hdrs(token, "ar"), timeout=120)
        assert r.status_code == 200, r.text
        d = r.json()
        narrative = d.get("narrative") or ""
        wins = d.get("wins") or []
        misses = d.get("misses") or []
        text_blob = " ".join([narrative, " ".join(map(str, wins)), " ".join(map(str, misses))])
        assert text_blob.strip(), "Empty weekly-review payload"
        assert has_arabic(text_blob), f"Weekly review not Arabic. Got: {text_blob[:200]!r}"

    def test_weekly_review_english(self, token):
        r = requests.get(f"{API}/ai/weekly-review", headers=hdrs(token, "en"), timeout=120)
        assert r.status_code == 200, r.text
        d = r.json()
        narrative = d.get("narrative") or ""
        wins = d.get("wins") or []
        misses = d.get("misses") or []
        text_blob = " ".join([narrative, " ".join(map(str, wins)), " ".join(map(str, misses))])
        assert text_blob.strip(), "Empty weekly-review payload"
        assert is_english_only(text_blob), f"Weekly review not English. Got: {text_blob[:200]!r}"


# ---------- AI: /ai/prioritize ----------
class TestPrioritize:
    def test_prioritize_arabic(self, token):
        r = requests.get(f"{API}/ai/prioritize", headers=hdrs(token, "ar"), timeout=120)
        assert r.status_code == 200, r.text
        d = r.json()
        insights = d.get("insights") or ""
        ranked = d.get("ranked") or []
        reasons = " ".join([(item.get("reason") or "") for item in ranked if isinstance(item, dict)])
        blob = f"{insights} {reasons}".strip()
        if blob:
            assert has_arabic(blob), f"Prioritize not Arabic. Got: {blob[:200]!r}"

    def test_prioritize_english(self, token):
        r = requests.get(f"{API}/ai/prioritize", headers=hdrs(token, "en"), timeout=120)
        assert r.status_code == 200, r.text
        d = r.json()
        insights = d.get("insights") or ""
        ranked = d.get("ranked") or []
        reasons = " ".join([(item.get("reason") or "") for item in ranked if isinstance(item, dict)])
        blob = f"{insights} {reasons}".strip()
        if blob:
            assert is_english_only(blob), f"Prioritize not English. Got: {blob[:200]!r}"
