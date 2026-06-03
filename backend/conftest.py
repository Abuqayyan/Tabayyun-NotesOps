"""Pytest bootstrap.

The existing suite is black-box (it makes HTTP calls to a running server), so it does
not import the app package. But to keep things robust — and to allow future tests that
DO import app modules — we set safe placeholder values for the fail-fast config vars
when they are not already provided by the environment. These placeholders are only ever
used in a test process; real deployments must set real secrets.
"""
import os
import secrets

os.environ.setdefault("JWT_SECRET", secrets.token_urlsafe(48))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "opscore_test")

# A valid Fernet key for import-time validation in app.core.config.
try:
    from cryptography.fernet import Fernet
    os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())
except Exception:  # cryptography not installed in this env — config import would skip anyway
    pass
