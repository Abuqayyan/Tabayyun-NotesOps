"""AI service helpers: Claude client wrapper, per-user config, usage tracking, scoring."""
import logging
from datetime import datetime
from typing import Optional

from cryptography.fernet import InvalidToken
from emergentintegrations.llm.chat import LlmChat, UserMessage

from app.core.config import FERNET, EMERGENT_LLM_KEY, DEFAULT_CLAUDE_MODEL
from app.core.db_mongo import db
from app.core.utils import now_iso, lang_directive

log = logging.getLogger("opscore.ai")


def build_user_context(user_data: dict, projects: list, tasks: list) -> str:
    ctx = f"USER: {user_data.get('name')} ({user_data.get('email')})\n\n"
    if projects:
        ctx += "ACTIVE PROJECTS:\n"
        for p in projects[:10]:
            ctx += f"- {p.get('name')} [{p.get('status')}, priority={p.get('priority')}, progress={p.get('progress',0)}%]: {p.get('description','')[:120]}\n"
    if tasks:
        ctx += "\nCURRENT TASKS:\n"
        for t in tasks[:20]:
            ctx += f"- {t.get('title')} [{t.get('status')}, priority={t.get('priority')}]\n"
    return ctx


async def get_user_ai_config(user_id: str) -> dict:
    """Returns {api_key, provider, model, source}. Falls back to the Emergent key."""
    s = await db.user_settings.find_one({"user_id": user_id}, {"_id": 0})
    if s and s.get("api_key_encrypted"):
        try:
            key = FERNET.decrypt(s["api_key_encrypted"].encode()).decode()
            return {"api_key": key, "provider": "anthropic", "model": s.get("model", DEFAULT_CLAUDE_MODEL), "source": "user"}
        except InvalidToken:
            log.error(f"Failed to decrypt key for user {user_id}")
    return {
        "api_key": EMERGENT_LLM_KEY,
        "provider": "anthropic",
        "model": (s.get("model") if s else None) or DEFAULT_CLAUDE_MODEL,
        "source": "emergent",
    }


async def track_usage(user_id: str, prompt_chars: int, reply_chars: int):
    tokens_in = max(1, prompt_chars // 4)
    tokens_out = max(1, reply_chars // 4)
    await db.user_settings.update_one(
        {"user_id": user_id},
        {"$inc": {"usage.tokens_in": tokens_in, "usage.tokens_out": tokens_out, "usage.calls": 1},
         "$set": {"usage.last_call_at": now_iso()}},
        upsert=True,
    )


async def claude_chat(session_id: str, system: str, user_text: str, user_id: Optional[str] = None, lang: Optional[str] = None) -> str:
    if user_id:
        cfg = await get_user_ai_config(user_id)
    else:
        cfg = {"api_key": EMERGENT_LLM_KEY, "model": DEFAULT_CLAUDE_MODEL, "source": "emergent"}
    if not cfg["api_key"]:
        return "AI service unavailable. Add your Anthropic API key in Settings."
    final_system = system + lang_directive(lang) if lang else system
    chat = LlmChat(api_key=cfg["api_key"], session_id=session_id, system_message=final_system).with_model("anthropic", cfg["model"])
    try:
        resp = await chat.send_message(UserMessage(text=user_text))
        text = resp if isinstance(resp, str) else str(resp)
        if user_id:
            await track_usage(user_id, len(final_system) + len(user_text), len(text))
        return text
    except Exception as e:  # noqa: BLE001
        log.error(f"Claude error: {e}")
        return f"AI error: {str(e)[:160]}"


def compute_priority_score(task: dict, now: datetime) -> int:
    """Heuristic score 0-100 used to pick 'next action' before AI confirms."""
    score = 0
    p = task.get("priority", "medium")
    score += {"low": 10, "medium": 30, "high": 60, "critical": 90}.get(p, 30)
    c = task.get("complexity", "medium")
    score += {"low": 15, "medium": 5, "high": -10}.get(c, 5)
    if task.get("status") == "in_progress":
        score += 25
    if task.get("due_date"):
        try:
            d = datetime.fromisoformat(task["due_date"].replace("Z", "+00:00"))
            delta = (d - now).total_seconds() / 86400
            if delta < 0:
                score += 80
            elif delta < 1:
                score += 60
            elif delta < 3:
                score += 30
            elif delta < 7:
                score += 10
        except Exception:
            pass
    return max(0, min(100, score))
