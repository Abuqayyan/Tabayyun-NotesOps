# OpsCore — Backup & Restore Runbook (Phase 0)

Simple, dependable commands for the single-VPS deployment. All commands assume you
run them from the project root where `docker-compose.yml` lives, with a populated
`.env` (so `${MONGO_USERNAME}` etc. resolve).

There are **three** things to back up:
1. **MongoDB** — all business data (users, projects, tasks, notes, reminders, AI...).
2. **PostgreSQL** — relational store (empty in Phase 0, but back it up so the habit/scripts exist).
3. **Uploads** — project file attachments (Docker volume `uploads`).

> ⚠️ Never run `docker compose down -v` in production — the `-v` flag deletes the data volumes.

---

## 1. MongoDB

### Backup
```bash
# Dump into a timestamped archive on the host
docker compose exec -T mongo sh -c \
  'mongodump --username "$MONGO_INITDB_ROOT_USERNAME" --password "$MONGO_INITDB_ROOT_PASSWORD" \
   --authenticationDatabase admin --archive --gzip' \
  > backup-mongo-$(date +%F).archive.gz
```

### Restore
```bash
cat backup-mongo-YYYY-MM-DD.archive.gz | docker compose exec -T mongo sh -c \
  'mongorestore --username "$MONGO_INITDB_ROOT_USERNAME" --password "$MONGO_INITDB_ROOT_PASSWORD" \
   --authenticationDatabase admin --archive --gzip --drop'
```
(`--drop` replaces existing collections; omit it to merge.)

---

## 2. PostgreSQL

### Backup
```bash
docker compose exec -T postgres sh -c \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  > backup-pg-$(date +%F).dump
```

### Restore
```bash
cat backup-pg-YYYY-MM-DD.dump | docker compose exec -T postgres sh -c \
  'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists'
```

---

## 3. Uploads volume

### Backup
```bash
docker run --rm -v opscore_uploads:/data -v "$PWD":/backup alpine \
  tar czf /backup/backup-uploads-$(date +%F).tar.gz -C /data .
```

### Restore
```bash
docker run --rm -v opscore_uploads:/data -v "$PWD":/backup alpine \
  sh -c 'rm -rf /data/* && tar xzf /backup/backup-uploads-YYYY-MM-DD.tar.gz -C /data'
```
> The volume name is `<project>_uploads` (Compose prefixes the directory name). Confirm with `docker volume ls`.

---

## Suggested cron (daily at 02:30, keep 14 days)
```cron
30 2 * * * cd /opt/opscore && \
  docker compose exec -T mongo sh -c 'mongodump -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --archive --gzip' > /opt/backups/mongo-$(date +\%F).archive.gz && \
  docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > /opt/backups/pg-$(date +\%F).dump && \
  find /opt/backups -type f -mtime +14 -delete
```
Copy `/opt/backups` offsite (e.g. `rclone`/`rsync` to object storage). Cloudflare does
not back up your origin data — backups are your responsibility.

---

## MongoDB auth migration (existing data volume)

Phase 0 enables MongoDB authentication. The official image only auto-creates the root
user on a **fresh** data dir. If you already have a `mongo_data` volume from before auth
was enabled, do this **once** before bringing the new stack up with auth:

```bash
# 1. Start ONLY mongo temporarily WITHOUT auth, pointed at the existing volume:
docker run --rm -d --name mongo-migrate -v opscore_mongo_data:/data/db mongo:7

# 2. Create the root user (use the same values you'll put in .env):
docker exec -it mongo-migrate mongosh admin --eval \
  'db.createUser({user:"opscore", pwd:"YOUR_STRONG_PASSWORD", roles:[{role:"root",db:"admin"}]})'

# 3. Stop the temp container, then start the real stack (auth now enabled):
docker stop mongo-migrate
docker compose up -d
```
For a brand-new install there is nothing to migrate — `MONGO_INITDB_ROOT_*` handles it.
