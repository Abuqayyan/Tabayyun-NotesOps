"""Stub of emergentintegrations.llm.chat for the offline verification harness.

Returns a deterministic canned reply so AI endpoints can be exercised without network.
"""


class UserMessage:
    def __init__(self, text: str = ""):
        self.text = text


class LlmChat:
    def __init__(self, api_key=None, session_id=None, system_message=None):
        self.api_key = api_key
        self.session_id = session_id
        self.system_message = system_message or ""
        self.model = None

    def with_model(self, provider, model):
        self.model = model
        return self

    async def send_message(self, message):
        # If the system prompt asks for JSON, return minimal valid JSON so parsers succeed.
        sys = (self.system_message or "").lower()
        if "pong" in sys:
            return "PONG"
        if "json" in sys:
            if "subtasks" in sys:
                return '{"subtasks": [{"title": "Step 1", "estimated_minutes": 30, "rationale": "test"}]}'
            if "ranked" in sys:
                return '{"ranked": [], "insights": ["test insight"]}'
            if "patterns" in sys:
                return '{"patterns": [{"type": "pattern", "content": "test pattern"}]}'
            if "narrative" in sys and "wins" in sys:
                return '{"narrative": "ok", "wins": [], "misses": [], "patterns": [], "bottlenecks": [], "next_week_priorities": [], "insights": []}'
            if "top_risks" in sys:
                return '{"narrative": "ok", "top_risks": [], "strategic_actions": []}'
            if "start_date" in sys:
                return '{"start_date": "2026-06-02T09:00:00+00:00", "end_date": "2026-06-09T17:00:00+00:00", "rationale": "test", "focus_blocks_per_week": 5, "sprint_weeks": 1, "warnings": []}'
            return "{}"
        return "This is a stubbed AI reply for verification."
