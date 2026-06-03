"""Central configuration with fail-fast validation.

Phase 0 hardening:
  - JWT_SECRET is REQUIRED (no insecure fallback) and quality-checked.
  - ENCRYPTION_KEY is REQUIRED and must be a valid Fernet key (no auto-generation,
    which previously caused all encrypted values to become undecryptable on restart).
  - MONGO_URL / DB_NAME remain required.

Importing this module triggers validation. A misconfigured deployment will fail to
start with a clear error rather than booting in an insecure or data-losing state.
"""
import os
from pathlib import Path
from dotenv import load_dotenv
from cryptography.fernet import Fernet

# backend/  (this file lives at backend/app/core/config.py)
ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")


class ConfigError(RuntimeError):
    """Raised at import time when required configuration is missing or insecure."""


def _require(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise ConfigError(
            f"Required environment variable '{name}' is missing. "
            f"Set it in your environment or .env file. See .env.example."
        )
    return val


# ---- Weak/placeholder values we must never accept for secrets ----
_WEAK_SECRETS = {
    "", "dev-secret", "change-me", "change-me-in-prod", "changeme",
    "secret", "password", "test", "jwt-secret",
}


def _validate_jwt_secret(value: str) -> str:
    if value.strip().lower() in _WEAK_SECRETS:
        raise ConfigError(
            "JWT_SECRET is set to a weak/placeholder value. "
            "Generate a strong random secret, e.g.: "
            "python -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )
    if len(value) < 32:
        raise ConfigError(
            f"JWT_SECRET is too short ({len(value)} chars). Use at least 32 characters. "
            "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )
    return value


def _validate_fernet_key(value: str) -> bytes:
    key = value.encode()
    try:
        Fernet(key)  # validates length + base64 shape
    except Exception as exc:  # noqa: BLE001 - surface a clear, actionable message
        raise ConfigError(
            "ENCRYPTION_KEY is not a valid Fernet key. Generate one with: "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        ) from exc
    return key


# ---- Database ----
MONGO_URL = _require("MONGO_URL")
DB_NAME = _require("DB_NAME")
# Relational store (Phase 0: infrastructure only, no business data yet). Optional at boot
# so the app still starts if Postgres is briefly unavailable; reported via /api/health.
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

# ---- Auth / crypto (fail-fast) ----
JWT_SECRET = _validate_jwt_secret(_require("JWT_SECRET"))
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_DAYS = int(os.environ.get("JWT_EXPIRE_DAYS", "30"))
SESSION_HOURS = int(os.environ.get("SESSION_HOURS", "6"))  # OTP-issued session lifetime
OTP_TTL_MINUTES = int(os.environ.get("OTP_TTL_MINUTES", "10"))
OTP_MAX_ATTEMPTS = int(os.environ.get("OTP_MAX_ATTEMPTS", "5"))

ENCRYPTION_KEY = _validate_fernet_key(_require("ENCRYPTION_KEY"))
FERNET = Fernet(ENCRYPTION_KEY)

# ---- App behavior ----
ALLOW_REGISTRATION = os.environ.get("ALLOW_REGISTRATION", "false").lower() == "true"
PUBLIC_APP_URL = os.environ.get("PUBLIC_APP_URL", "").rstrip("/")
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
RESEND_FROM_EMAIL = os.environ.get("RESEND_FROM_EMAIL", "onboarding@resend.dev")
APP_NAME = os.environ.get("APP_NAME", "OpsCore")

# ---- CORS (explicit origins only; no wildcard with credentials) ----
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]

# ---- Uploads ----
UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", str(ROOT_DIR / "uploads")))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))  # 25 MB

# ---- AI models ----
DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-5-20250929"
SUPPORTED_MODELS = [
    "claude-sonnet-4-5-20250929",
    "claude-opus-4-5-20251101",
    "claude-haiku-4-5-20251001",
    "claude-sonnet-4-6",
    "claude-opus-4-6",
]
