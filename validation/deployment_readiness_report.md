# Deployment Readiness Report — Tabayyun NotesOps
_Phase 5.5 · validated against the actual repo artifacts._

## Present & verified
| Area | Status | Evidence |
|---|---|---|
| Docker Compose | ✅ | `docker-compose.yml` — mongo + postgres internal-only (no host ports), backend non-root |
| Backend image | ✅ | `backend/Dockerfile` — non-root `appuser` (uid 10001) |
| Env template | ✅ | `.env.example`; fail-fast config validation in `app/core/config.py` (rejects weak/short `JWT_SECRET`, invalid Fernet key) |
| Secrets | ✅ | required via env (`${JWT_SECRET:?}` / `${ENCRYPTION_KEY:?}` in compose); Fernet-encrypted at rest |
| DB migrations | ✅ | Alembic configured (`alembic.ini`, `alembic/env.py`); ORM `create_all` idempotent on startup |
| Backups / restore | ✅ docs | `BACKUP_RESTORE.md` runbook (pg_dump + mongodump + uploads) |
| Health checks | ✅ | `GET /api/health` → mongo + postgres status; compose `pg_isready` |
| Logging | ✅ | structured logging; global exception handler (no stack traces leaked) |
| Metrics | ✅ | Phase 5 request-metrics middleware + `GET /api/ops/*` + `/api/observability/*` |
| Error tracking | 🟡 partial | in-app `api_errors` capture + ops center; **no external Sentry/APM** wired |
| Rate limiting | ✅ | slowapi on auth/OTP/search/export/AI; keyed on CF-Connecting-IP |
| CORS / headers | ✅ | explicit origins (no wildcard+credentials), security headers middleware, X-Request-ID |

## Gaps / actions before production cutover
| Severity | Item | Action |
|---|---|---|
| **High (env-blocked)** | Live Docker/Postgres smoke never run in this environment (no Docker daemon on the build host). All relational logic verified on SQLite. | Run `docker compose up` on the VPS; hit `/api/health` → expect `postgres.ok=true`; smoke the 4 workflows. |
| **High (env-blocked)** | Backup **restore drill** not executed. | Execute `BACKUP_RESTORE.md` into a scratch DB and confirm row counts. |
| Medium | CI runs SQLite with FK enforcement **off**, hiding Postgres-only FK bugs (3 found this phase by manual tracing). | Add a Postgres CI lane **or** enable `PRAGMA foreign_keys=ON` in the SQLite test engine. |
| Medium | No external error/uptime alerting. | Wire Sentry (or equivalent) + an uptime ping on `/api/health`. |
| Low | `@app.on_event` startup/shutdown is deprecated. | Migrate to lifespan handlers. |
| Low | `passlib` (unmaintained) pinned with `bcrypt==4.1.3` (W1). | Plan migration to argon2/bcrypt-direct. |
| Low | Single-instance scheduler/websocket (documented). | Keep 1 backend replica until a distributed lock is added. |

## Verdict
Infrastructure is **deployment-ready in configuration**. Two **operational prerequisites remain that can only be executed on the target VPS** (live compose smoke + restore drill). No code-level deployment blockers.
