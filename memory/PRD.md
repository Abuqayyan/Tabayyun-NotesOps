# OpsCore — AI-native Productivity Operating System

## Original Problem Statement
Build a highly advanced AI-powered productivity OS for multi-project founders that feels like a smart AI executive assistant (COO + PM + Coach), not a static task manager. Should combine the feel of Linear + Notion + ClickUp + Motion + Superhuman.

## User Choices (locked in)
- **Language**: Arabic UI by default, English available via toggle in AppShell header / Login / Register / Brief pages. Choice persisted in localStorage.
- **AI Model**: Claude Sonnet 4.5 (claude-sonnet-4-5-20250929) via Emergent Universal LLM key. Users can override with their own Anthropic key in Settings (Fernet-encrypted in DB).
- **Auth**: JWT email/password (HS256, 30-day expiry).
- **Email invites**: Resend (key empty by default — graceful fallback returns invite URL).
- **Theme**: Both light + dark with toggle (premium high-contrast dark with vermilion accents).
- **Scope**: All 14 modules at MVP level + execution intelligence layer.

## Architecture
- **Backend**: FastAPI + Motor (MongoDB async) + emergentintegrations.LlmChat (Claude 4.5). All routes under `/api`. Single file `/app/backend/server.py` (~2050 lines).
- **Frontend**: React 19 + React Router 7 + Tailwind 3.4 (logical CSS properties for RTL/LTR) + shadcn/ui + Framer Motion + Recharts.
- **Storage**: MongoDB for all data + on-disk uploads under `UPLOAD_DIR` (default `/app/backend/uploads`, mounted as `/data/uploads` volume in Docker).
- **Localization pattern**: `useLang().t("النص العربي", "English text")` inline helper. axios injects `X-Lang` header from `localStorage.opscore_lang` on every API call. Backend extracts via `get_lang` dependency and appends a strict `OUTPUT LANGUAGE OVERRIDE` directive to every Claude system prompt via `lang_directive()`.

### 2026-05-17 — Phase 4 (Professional Reminder System)
- **Multi-recipient reminders**: `recipient_ids` per reminder. Tasks default to `[assignee_id || owner_id]`; notes default to `[owner_id]`. Reminders show in BOTH creator's AND recipient's `/api/reminders` feed.
- **Offset-based scheduling**: New `offset_minutes` field on reminders auto-computes `fire_at = parent.due_date - offset`. Validates entity has an anchor date.
- **Quick-fire endpoint**: `POST /api/reminders/send-now` either fires an existing reminder by id OR creates an ephemeral one-shot. Only flips `sent=true` when at least one recipient succeeded (retries on transient SMTP failures, max 5 attempts).
- **Daily overdue digest**: Workspace-level setting `overdue_digest_enabled` + `overdue_digest_time` (HH:MM UTC) + `digest_lookahead_hours`. Scheduler emails each non-opted-out user a styled list of their overdue + soon-due tasks once per day.
- **Default offsets curation**: Admin chooses which quick-pick chips appear on each reminder bell — `default_offsets_minutes`.
- **Personal prefs**: `digest_opted_out` + `quiet_hours_start/end` (HH:MM validated).
- **ReminderBell UI**: recipients chip selector + quick offsets + custom datetime + per-row "Send now" / delete.
- **Settings → Reminders tab**: workspace digest config (admin-only) + offset presets + personal preferences.
- **Admin seed migration**: idempotent startup task promotes founder to `is_admin=true` when no admin exists.
- **Backend tests**: `/app/backend/tests/test_phase4_reminders.py` — 16/16 + regression 29/29 phase3 = 45/45 PASS.

 `recipient_ids` per reminder. Tasks default to `[assignee_id || owner_id]`; notes default to `[owner_id]`. Reminders show in BOTH creator's AND recipient's `/api/reminders` feed.
- **Offset-based scheduling**: New `offset_minutes` field on reminders auto-computes `fire_at = parent.due_date - offset`. Validates entity has an anchor date.
- **Quick-fire endpoint**: `POST /api/reminders/send-now` either fires an existing reminder by id OR creates an ephemeral one-shot. Only flips `sent=true` when at least one recipient succeeded (retries on transient SMTP failures, max 5 attempts).
- **Daily overdue digest**: Workspace-level setting `overdue_digest_enabled` + `overdue_digest_time` (HH:MM UTC) + `digest_lookahead_hours`. Scheduler emails each non-opted-out user a styled list of their overdue + soon-due tasks once per day.
- **Default offsets curation**: Admin chooses which quick-pick chips appear on each reminder bell — `default_offsets_minutes` (e.g., `[0, 15, 60, 1440]`).
- **Personal prefs**: `digest_opted_out` + `quiet_hours_start/end` (HH:MM validated; runtime enforcement pending).
- **ReminderBell UI**: recipients chip selector (multi-select teammates) + quick-pick chips (Now/15m/1h/1d) + custom datetime + per-row "Send now" / Delete.
- **Settings → Reminders tab**: workspace digest config (admin-only) + offset presets + personal preferences.
- **Admin seed migration**: idempotent startup task promotes `founder@opscore.app` (or the oldest user) to `is_admin=true` when no admin exists — fixes legacy seeded accounts.
- **Backend tests**: `/app/backend/tests/test_phase4_reminders.py` — 16/16 passing. Regression 29/29 phase3 PASS. Total 45/45.


- **Auth**: 2-step OTP login via email (6-digit code, 10-min TTL, max 5 attempts). Sessions reduced to 6 hours after OTP. Public registration disabled (`ALLOW_REGISTRATION=false`).
- **Invite-only onboarding**: Owner adds email → temp password emailed → first login forces password change. Accept-invite page reads `?invite=&email=` query params.
- **SMTP infrastructure**: Custom SMTP host/port/user/pass/from + STARTTLS/SSL. Password encrypted with Fernet. Settings → SMTP tab + test send endpoint. Replaces Resend.
- **Email templates editor**: Customizable HTML + subject (AR/EN) for 4 system events: OTP, invite, task_assigned, task_reminder. Per-template reset to default. Live iframe preview.
- **Project sharing & RBAC**: Per-project `roles` map `{user_id: owner|editor|viewer}`. Tasks/notes inherit project permissions. Sharing UI inside ProjectDetail (owner-only). Endpoints: POST/PATCH/DELETE `/api/projects/{pid}/share|members/{uid}`.
- **Task assignment**: `assignee_id` field on tasks. Auto-emails the assignee via task_assigned template on create/update. Detail modal has Assignee dropdown sourced from `/team/members`.
- **Reminders system**: Per-task & per-note reminders with `fire_at`. Background asyncio loop polls every 60s and sends via SMTP using task_reminder template. ReminderBell popover component embedded in Task cards + Notes.
- **Internal Calendar** (`/calendar`): Month grid + click-day to create event. Synthetic task events auto-injected from any task with `scheduled_for` or `due_date`. End must be ≥ start.
- **Graph / Canvas** (`/graph`): Obsidian-style node-edge editor via `@xyflow/react`. Drag/drop nodes, connect edges, double-click to rename, link canvas to a project, import all project tasks as nodes. Auto-save debounced 1.2s.
- **Security hardening**: SecurityHeadersMiddleware (X-Frame-Options=DENY, X-Content-Type-Options=nosniff, Referrer-Policy, Permissions-Policy, X-XSS-Protection). Rate-limited OTP requests (5/10min). Change-password endpoint with bcrypt verify.
- **DB**: `db.otps`, `db.smtp_settings`, `db.email_templates`, `db.reminders`, `db.calendar_events`, `db.canvases`. Projects now carry `roles: {user_id: role}`.
- **Backend tests**: `/app/backend/tests/test_phase3.py` — 29/29 passing.

## What's Been Implemented (cumulative)

### 2026-02-10 — MVP
- 14-module shell (Dashboard, Projects, ProjectDetail, Tasks, Focus, Notes, Team, Analytics, Notifications, Assistant, Memory, WeeklyReview, Settings, Brief)
- JWT auth, Projects/Tasks/Notes CRUD, Team invites, Notifications, Focus sessions, Analytics, AI chat/rewrite/breakdown/summarize/prioritize
- User-supplied Anthropic key (encrypted), model picker, usage tracking, connection test
- Daily Execution Brief, Weekly Review, Memory & Bottlenecks
- WebSocket real-time task sync (`/api/ws`)
- HTML5 drag-and-drop Kanban
- Start/End date+time pickers + Projects Timeline / Roadmap view with AI scheduling
- Public shareable AI briefings (`/brief/{token}`)
- Time-based dashboard greeting

### 2026-05-12 — Localization
- `LanguageContext` with inline `t(ar, en)` helper; auto-sets `document.documentElement.dir` and `lang`.
- Logical CSS (`border-e`, `ms-2`, `ps-3`, etc.) so sidebar lives on the right in Arabic and left in English without manual flips.
- Lang toggle button (Languages icon + AR/EN) on AppShell header, Login, Register, public Brief page.
- Backend `lang_directive()` appended to every AI system prompt; `get_lang` FastAPI dependency reads `X-Lang` header on all AI endpoints (chat, daily-brief, weekly-review, prioritize, schedule-suggest, summarize-project, rewrite, breakdown, memory/extract, share/brief).
- Static endpoints localized server-side: greeting (5 periods × 2 langs), notifications, timeline insights.

### 2026-05-14 — Focus & Filtering (multi-project clarity)
- **Project filter dropdown** on Tasks page header — "All projects" or a specific one.
- **"Today" view** — shows tasks pinned for today (`scheduled_for == today`) + overdue + in-progress. Timezone-correct (client passes local `today` to the server).
- **"This week" view** — pinned tasks for the next 7 days + overdue carry-over + in-progress.
- **Pin-to-Today** — 📌 icon on every task card + detail modal. One click pins a task to today's plan or removes it.
- **Project chip on every task card** — colored dot + truncated project name so you instantly see ownership.
- **Free-text search** — debounced (250ms) `q=` filter on title/description; runs server-side with case-insensitive regex.
- **Stats strip** — live counts that respect the current filter: total / in-progress / overdue / pinned-today.
- **Race-condition fix** — `loadVersion` ref ensures only the latest tasks request applies (older in-flight responses are discarded).
- New schema field: `tasks.scheduled_for` (`YYYY-MM-DD` string or null). Backwards compatible — existing tasks default to null.

### 2026-05-13 — Workflow upgrades
- **Task Progress Updates** — new `task_updates` collection. Endpoints: `POST/GET/DELETE /api/tasks/{tid}/updates`. UI: log section inside the task detail modal with input + chronological list + per-item delete. Lets the founder write "did X today" even while the task is still in progress.
- **Project File Uploads** — new `project_files` collection + on-disk storage under `UPLOAD_DIR/{project_id}/`. Endpoints: `POST/GET/DELETE /api/projects/{pid}/files` + `GET /api/projects/{pid}/files/{fid}/download`. 25 MB per file (configurable via `MAX_UPLOAD_BYTES`). UI in ProjectDetail: upload button + drag-and-drop area + file list with download/delete + size & timestamp.
- **Notes Done state** — added `done` + `done_at` fields. `GET /api/notes` hides done notes by default; `?include_done=true` shows all. UI: per-note ✓ button to toggle done; "Show done / Hide done" header toggle; done notes render dimmed + struck-through with green check.
- **Docker** — full stack (`mongo` + `backend` + `frontend`) via `docker-compose.yml`. Backend: python:3.11-slim + uvicorn, healthcheck on `/api/`, persistent `uploads` volume, `MONGO_URL=mongodb://mongo:27017` injected. Frontend: multi-stage build → `node:20-bookworm-slim` build → `nginx:1.27-alpine` serve with SPA fallback. `.env.example` template + `DOCKER.md` quickstart guide.

## Key DB schema additions
- `task_updates`: `{id, task_id, owner_id, content, created_at}`
- `project_files`: `{id, project_id, owner_id, filename, content_type, size, storage_path, uploaded_at}`
- `notes` now: `+ done: bool, done_at: iso|null`
- `share_briefs_cache` keyed by `{user_id, lang}` (each language cached independently)

## Key environment variables
- `MONGO_URL`, `DB_NAME` (required)
- `JWT_SECRET`, `ENCRYPTION_KEY` (required for production)
- `EMERGENT_LLM_KEY` (fallback Claude key)
- `RESEND_API_KEY`, `RESEND_FROM_EMAIL` (optional, for invite emails)
- `UPLOAD_DIR` (default `./uploads`; Docker mounts `/data/uploads`)
- `MAX_UPLOAD_BYTES` (default 25 MB)
- `CORS_ORIGINS` (comma-separated; default `*`)
- `REACT_APP_BACKEND_URL` (frontend build-time; baked into bundle)

## Roadmap
### P1 — next
- Deep Work time-blocking inside Timeline (drag a task onto a calendar slot)
- AI-driven update suggestions ("Looks like you haven't logged progress on X in 3 days — what shipped?")
- Threaded comments on project files (annotate the strategy doc itself)
- Drag tasks directly on the internal Calendar to reschedule (currently month grid is read-only for synthetic events)
- In-app reminder feed (currently only email channel; backend supports `channel=inapp` already)

### P2 — backlog
- Strategic Risk Layer — subtle visualization of slipping projects on the timeline
- Google Calendar / Outlook sync (current calendar is internal-only)
- Mobile-responsive Kanban + Calendar + Graph (desktop-first today)
- Server-side i18n for outbound emails (invites)
- Refactor `server.py` into routers (~3100 lines; growth per phase increasing)
- WebSocket: accept() before close(4001) handshake

## Files of reference
- `/app/backend/server.py` — monolithic backend (FastAPI + Motor + AI + WS + uploads)
- `/app/frontend/src/contexts/LanguageContext.jsx` — `useLang()` with `t(ar, en)`
- `/app/frontend/src/components/layout/AppShell.jsx` — sidebar (uses `border-e` logical) + lang toggle
- `/app/frontend/src/lib/api.js` — axios with `X-Lang` interceptor
- `/app/docker-compose.yml` + `/app/backend/Dockerfile` + `/app/frontend/Dockerfile`
- `/app/DOCKER.md` — quickstart for Docker builds
- `/app/memory/test_credentials.md` — founder@opscore.app / test123
