"""OpsCore backend — compatibility entry point.

The monolithic implementation was split (Phase 0) into the `app` package:
  app/core      — config, security, db clients, deps, errors
  app/shared    — email, files, websocket, scheduler, activity, permissions, rate limiting
  app/modules   — one router per feature (auth, users, projects, tasks, notes, ...)

This shim preserves `server:app` so existing run commands and tooling keep working.
Prefer `app.main:app` for new tooling.
"""
from app.main import app  # noqa: F401

__all__ = ["app"]
