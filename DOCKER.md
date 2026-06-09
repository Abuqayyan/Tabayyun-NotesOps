# OpsCore — Docker

Spin up the whole stack (MongoDB + PostgreSQL + FastAPI backend + React frontend) locally with Docker.

## Prerequisites
- Docker Desktop / Engine 24+
- Docker Compose v2

## Quick start

1. Copy the env template and fill it in (see `.env.example` for the full list):
   ```bash
   cp .env.example .env
   ```
   **Required** (the backend fails fast on startup if any are missing/weak):
   - `JWT_SECRET` — strong random string, ≥ 32 chars:
     ```bash
     python3 -c "import secrets; print(secrets.token_urlsafe(48))"
     ```
   - `ENCRYPTION_KEY` — a Fernet key (generate ONCE and keep stable):
     ```bash
     python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
     ```
   - `MONGO_PASSWORD` — MongoDB root password
   - `POSTGRES_PASSWORD` — PostgreSQL password
   - `CORS_ORIGINS` — your frontend origin(s), comma-separated (no wildcard)

   *Optional:* `EMERGENT_LLM_KEY`, `RESEND_*`, `PUBLIC_APP_URL`.

   > Upgrading an existing install that predates MongoDB auth? Follow the
   > "MongoDB auth migration" steps in [BACKUP_RESTORE.md](BACKUP_RESTORE.md) first.

2. Build and start:
   ```bash
   docker compose up --build
   ```

3. Open:
   - Frontend → http://localhost:3000
   - Backend  → http://localhost:8001/api/

## Volumes (persistent state)
- `mongo_data` — MongoDB database files
- `pg_data`    — PostgreSQL data files
- `uploads`    — Project file attachments (`/data/uploads` inside the backend container)

See [BACKUP_RESTORE.md](BACKUP_RESTORE.md) for backup/restore commands.

## Frontend backend URL
`REACT_APP_BACKEND_URL` is **baked into the React build**. For local Docker it defaults to `http://localhost:8001`. For production, set it before building:
```bash
REACT_APP_BACKEND_URL=https://api.yourdomain.com docker compose up --build frontend
```

## Common commands
```bash
# Logs
docker compose logs -f backend
docker compose logs -f frontend

# Rebuild a single service
docker compose up --build backend

# Stop & remove (keep volumes)
docker compose down

# Stop & wipe everything (DELETES data)
docker compose down -v
```

## Ports exposed on host
| Service  | Host port | Notes |
|----------|-----------|-------|
| frontend | 3000      | Put Cloudflare in front in production |
| backend  | 8001      | Put Cloudflare in front in production |
| mongo    | —         | **Internal network only** (no longer published) |
| postgres | —         | **Internal network only** (no longer published) |

In production, only expose what Cloudflare needs to reach; keep the databases off the public internet.
