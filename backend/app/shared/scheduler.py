"""Background reminder scheduler + daily overdue digest + admin seed.

NOTE (scale): this runs in-process via asyncio. Correct for the single-instance,
<50-user deployment. Running multiple backend replicas later requires a distributed
lock / leader election to avoid double-sends (documented in the roadmap).
"""
import asyncio
import logging
from datetime import timedelta

from app.core.config import APP_NAME, PUBLIC_APP_URL
from app.core.db_mongo import db
from app.core.utils import now_iso
from app.shared.email import get_smtp_config, send_email
from app.modules.reminders.service import get_workspace_reminder_settings, fire_reminder_payload
from security_utils import now_utc

log = logging.getLogger("opscore.scheduler")


async def _run_overdue_digest(ws: dict):
    """Email each user a digest of their overdue + soon-due tasks."""
    smtp_cfg = await get_smtp_config()
    if not smtp_cfg or not smtp_cfg.get("host"):
        log.info("Digest skipped — SMTP unconfigured")
        return
    lookahead_hours = int(ws.get("digest_lookahead_hours", 24))
    now = now_utc()
    soon_cutoff = now + timedelta(hours=lookahead_hours)

    from datetime import datetime
    users = await db.users.find({}, {"_id": 0, "password_hash": 0}).to_list(1000)
    sent_count = 0
    for u in users:
        prefs = await db.user_settings.find_one({"user_id": u["id"]}, {"_id": 0}) or {}
        if prefs.get("digest_opted_out"):
            continue
        tasks = await db.tasks.find(
            {"$or": [{"owner_id": u["id"]}, {"assignee_id": u["id"]}], "status": {"$ne": "done"}},
            {"_id": 0, "id": 1, "title": 1, "due_date": 1, "priority": 1},
        ).to_list(500)
        overdue, soon = [], []
        for t in tasks:
            d = t.get("due_date")
            if not d:
                continue
            try:
                dd = datetime.fromisoformat(d.replace("Z", "+00:00"))
            except Exception:
                continue
            if dd < now:
                overdue.append((t, dd))
            elif dd <= soon_cutoff:
                soon.append((t, dd))
        if not overdue and not soon:
            continue

        rows = ""
        for label, group, color in [("Overdue", overdue, "#EF4444"), (f"Due in next {lookahead_hours}h", soon, "#FF4500")]:
            if not group:
                continue
            rows += f'<div style="margin-top:16px;font-size:11px;letter-spacing:0.12em;color:{color};text-transform:uppercase;font-weight:600">{label}</div>'
            for t, dd in sorted(group, key=lambda x: x[1])[:10]:
                rows += f'<div style="padding:8px 0;border-bottom:1px solid #262626;font-size:13px;color:#fafafa">{t["title"]} <span style="color:#737373;font-size:11px;font-family:monospace">· {dd.strftime("%b %d %H:%M")}</span></div>'

        app_url = PUBLIC_APP_URL or ""
        html = f"""<!doctype html><html><body style="margin:0;background:#0a0a0a;font-family:'IBM Plex Sans Arabic',system-ui,sans-serif;color:#e5e5e5">
<div style="max-width:560px;margin:32px auto;background:#141414;border:1px solid #262626;border-radius:8px;overflow:hidden">
  <div style="padding:20px 24px;border-bottom:1px solid #262626"><strong style="font-size:14px">{APP_NAME}</strong></div>
  <div style="padding:32px 24px">
    <div style="font-size:11px;letter-spacing:0.12em;color:#737373;text-transform:uppercase;margin-bottom:8px">Daily digest</div>
    <h2 style="margin:0 0 8px;font-size:22px;font-weight:500;color:#fafafa">Good morning, {u.get('name','').split(' ')[0]}</h2>
    <p style="margin:0 0 16px;font-size:13px;color:#a3a3a3">{len(overdue)} overdue · {len(soon)} due soon</p>
    {rows}
    <a href="{app_url}/tasks" style="display:inline-block;background:#FF4500;color:white;text-decoration:none;padding:12px 24px;border-radius:6px;font-weight:500;font-size:14px;margin-top:24px">Open OpsCore</a>
  </div>
</div></body></html>"""
        ok, _ = await send_email(smtp_cfg, u["email"], f"{APP_NAME} — Daily digest ({len(overdue)} overdue)", html, from_name=APP_NAME)
        if ok:
            sent_count += 1
    log.info(f"Daily digest sent to {sent_count} user(s)")


async def reminder_loop():
    """Polls db.reminders every 60s, sends due reminders, runs escalations + daily digest."""
    from app.shared.escalation import run_escalations
    await asyncio.sleep(5)  # let app start up
    last_digest_minute = None
    tick = 0
    while True:
        try:
            now = now_utc()
            now_str = now.isoformat()
            tick += 1
            # Heartbeat for the Operations Center (proves the scheduler is alive).
            try:
                await db.ops_heartbeat.update_one(
                    {"id": "scheduler"},
                    {"$set": {"last_run_at": now_str}, "$inc": {"loop_count": 1},
                     "$setOnInsert": {"id": "scheduler", "started_at": now_str}},
                    upsert=True,
                )
            except Exception:  # noqa: BLE001
                pass

            due = await db.reminders.find({
                "enabled": True,
                "sent": {"$ne": True},
                "fire_at": {"$lte": now_str},
            }, {"_id": 0}).to_list(50)
            for r in due:
                try:
                    recipients = r.get("recipient_ids") or [r["user_id"]]
                    actor = "OpsCore"
                    if r.get("user_id"):
                        u = await db.users.find_one({"id": r["user_id"]}, {"_id": 0, "name": 1})
                        actor = (u or {}).get("name") or actor
                    ok, fail = await fire_reminder_payload(r["entity_type"], r["entity_id"], recipients, r.get("message"), actor)
                    if ok > 0:
                        await db.reminders.update_one(
                            {"id": r["id"]},
                            {"$set": {"sent": True, "sent_at": now_str, "send_ok_count": ok, "send_fail_count": fail}},
                        )
                    else:
                        attempts = (r.get("attempts") or 0) + 1
                        terminal = attempts >= 5
                        await db.reminders.update_one(
                            {"id": r["id"]},
                            {"$set": {
                                "attempts": attempts,
                                "last_attempt_at": now_str,
                                "send_fail_count": fail,
                                **({"sent": True, "sent_at": now_str, "error": "max_retries"} if terminal else {}),
                            }},
                        )
                except Exception as e:  # noqa: BLE001
                    log.error(f"Reminder processing error for {r.get('id')}: {e}")
                    await db.reminders.update_one({"id": r["id"]}, {"$set": {"sent": True, "sent_at": now_str, "error": str(e)[:200]}})

            # Escalations: every ~10 minutes. The per-entity level record dedups, and the
            # enqueued reminders are delivered by the same loop on the next pass.
            if tick % 10 == 1:
                try:
                    result = await run_escalations(now)
                    if result.get("tasks") or result.get("approvals"):
                        log.info(f"Escalations: {result}")
                    await db.ops_heartbeat.update_one({"id": "scheduler"}, {"$set": {"last_escalation_at": now_str}})
                except Exception as e:  # noqa: BLE001
                    log.error(f"Escalation run failed: {e}")

            ws = await get_workspace_reminder_settings()
            if ws.get("overdue_digest_enabled"):
                hhmm = ws.get("overdue_digest_time", "09:00")
                current_hm = now.strftime("%H:%M")
                if current_hm == hhmm and last_digest_minute != f"{now.date().isoformat()}-{hhmm}":
                    last_digest_minute = f"{now.date().isoformat()}-{hhmm}"
                    await _run_overdue_digest(ws)
        except Exception as e:  # noqa: BLE001
            log.error(f"Reminder loop error: {e}")
        await asyncio.sleep(60)


async def seed_admin():
    """Idempotent: ensure at least one admin exists (founder, else oldest user)."""
    try:
        admin_count = await db.users.count_documents({"is_admin": True})
        if admin_count == 0:
            founder = await db.users.find_one({"email": "founder@opscore.app"})
            if founder:
                await db.users.update_one({"id": founder["id"]}, {"$set": {"is_admin": True}})
                log.info("Promoted founder@opscore.app to admin")
            else:
                first = await db.users.find({}, {"_id": 0, "id": 1}).sort("created_at", 1).limit(1).to_list(1)
                if first:
                    await db.users.update_one({"id": first[0]["id"]}, {"$set": {"is_admin": True}})
                    log.info(f"Promoted first user ({first[0]['id']}) to admin")
    except Exception as e:  # noqa: BLE001
        log.warning(f"Admin seed skipped: {e}")
