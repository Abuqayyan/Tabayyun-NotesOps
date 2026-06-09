"""AI narration wrapper.

`narrate()` asks Claude (via the existing claude_chat) to turn already-computed facts into
a short narrative. It NEVER raises and NEVER blocks a pipeline: when no API key is set, or
Claude errors, it returns the supplied deterministic fallback and flags ai_used=False. This
is what keeps the whole intelligence layer functional (and tests deterministic) without AI.
"""
import hashlib
import json
import logging
from typing import Optional, Tuple

from app.modules.ai.service import claude_chat

log = logging.getLogger("opscore.intelligence")

# Sentinels returned by claude_chat when AI is unavailable / errored.
_UNAVAILABLE_PREFIXES = ("AI service unavailable", "AI error")


async def narrate(system: str, payload: dict, fallback: str, user_id: Optional[str] = None,
                  session_id: str = "intelligence") -> Tuple[str, bool]:
    """Return (narrative, ai_used). Facts are passed as JSON; the model only prose-wraps them."""
    user_text = (
        "Summarize the following operational data for an executive audience. "
        "Be concise and factual; do not invent numbers beyond what is given.\n\n"
        + json.dumps(payload, ensure_ascii=False, default=str)
    )
    try:
        text = await claude_chat(session_id, system, user_text, user_id=user_id)
    except Exception as e:  # noqa: BLE001 - defensive; claude_chat already guards
        log.warning(f"narrate failed: {e}")
        return fallback, False
    if not text or text.startswith(_UNAVAILABLE_PREFIXES):
        return fallback, False
    return text.strip(), True


def source_hash(payload: dict) -> str:
    """Stable hash of the source facts, used to avoid regenerating identical summaries."""
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]
