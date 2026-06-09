"""Security helpers — OTP, rate limiting, permissions."""
import secrets
import string
from datetime import datetime, timezone, timedelta
from typing import Optional


def generate_otp(length: int = 6) -> str:
    """Cryptographically secure numeric OTP."""
    return "".join(secrets.choice(string.digits) for _ in range(length))


def generate_temp_password(length: int = 14) -> str:
    """Strong temp password with mixed case, digits, symbols."""
    alphabet = string.ascii_letters + string.digits + "!@#$%&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_invite_token() -> str:
    """URL-safe invite token."""
    return secrets.token_urlsafe(32)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def project_role(project: dict, user_id: str) -> Optional[str]:
    """Returns 'owner' | 'editor' | 'viewer' | None for the user in the given project."""
    if not project or not user_id:
        return None
    if project.get("owner_id") == user_id:
        return "owner"
    roles = project.get("roles", {}) or {}
    if user_id in roles:
        return roles[user_id]
    # Legacy fallback: presence in members array means viewer
    if user_id in (project.get("members") or []):
        return "viewer"
    return None


def can_view(project: dict, user_id: str) -> bool:
    return project_role(project, user_id) in ("owner", "editor", "viewer")


def can_edit(project: dict, user_id: str) -> bool:
    return project_role(project, user_id) in ("owner", "editor")


def can_admin(project: dict, user_id: str) -> bool:
    return project_role(project, user_id) == "owner"
