"""MongoDB client + startup index creation.

Phase 0 adds indexes for every collection touched by hot query paths. All index
creation is wrapped so a single failure (e.g. a pre-existing duplicate on a unique
index over dirty data) logs a warning instead of crashing startup.
"""
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING

from app.core.config import MONGO_URL, DB_NAME

log = logging.getLogger("opscore.db")

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]


# (collection, keys, options) — keys is a list of (field, direction) tuples.
_INDEX_SPECS = [
    # users — id + email are the primary lookups; email enforced unique.
    ("users", [("id", ASCENDING)], {"unique": True, "name": "ux_users_id"}),
    ("users", [("email", ASCENDING)], {"unique": True, "name": "ux_users_email"}),
    ("users", [("invited_by", ASCENDING)], {"name": "ix_users_invited_by"}),
    # projects
    ("projects", [("id", ASCENDING)], {"unique": True, "name": "ux_projects_id"}),
    ("projects", [("owner_id", ASCENDING)], {"name": "ix_projects_owner"}),
    ("projects", [("members", ASCENDING)], {"name": "ix_projects_members"}),
    # tasks
    ("tasks", [("id", ASCENDING)], {"unique": True, "name": "ux_tasks_id"}),
    ("tasks", [("project_id", ASCENDING)], {"name": "ix_tasks_project"}),
    ("tasks", [("owner_id", ASCENDING)], {"name": "ix_tasks_owner"}),
    ("tasks", [("assignee_id", ASCENDING)], {"name": "ix_tasks_assignee"}),
    ("tasks", [("due_date", ASCENDING)], {"name": "ix_tasks_due"}),
    ("tasks", [("scheduled_for", ASCENDING)], {"name": "ix_tasks_scheduled"}),
    ("tasks", [("owner_id", ASCENDING), ("status", ASCENDING)], {"name": "ix_tasks_owner_status"}),
    # notes
    ("notes", [("id", ASCENDING)], {"unique": True, "name": "ux_notes_id"}),
    ("notes", [("project_id", ASCENDING)], {"name": "ix_notes_project"}),
    ("notes", [("owner_id", ASCENDING)], {"name": "ix_notes_owner"}),
    # task_updates
    ("task_updates", [("task_id", ASCENDING)], {"name": "ix_taskupdates_task"}),
    ("task_updates", [("owner_id", ASCENDING)], {"name": "ix_taskupdates_owner"}),
    # project_files
    ("project_files", [("project_id", ASCENDING)], {"name": "ix_files_project"}),
    ("project_files", [("id", ASCENDING)], {"unique": True, "name": "ux_files_id"}),
    # reminders — scheduler scans (enabled, sent, fire_at)
    ("reminders", [("fire_at", ASCENDING)], {"name": "ix_reminders_fire"}),
    ("reminders", [("enabled", ASCENDING), ("sent", ASCENDING), ("fire_at", ASCENDING)], {"name": "ix_reminders_scan"}),
    ("reminders", [("user_id", ASCENDING)], {"name": "ix_reminders_user"}),
    ("reminders", [("recipient_ids", ASCENDING)], {"name": "ix_reminders_recipients"}),
    ("reminders", [("entity_type", ASCENDING), ("entity_id", ASCENDING)], {"name": "ix_reminders_entity"}),
    # otps
    ("otps", [("id", ASCENDING)], {"unique": True, "name": "ux_otps_id"}),
    ("otps", [("user_id", ASCENDING)], {"name": "ix_otps_user"}),
    # TTL index: expire OTP docs ~1 day after their expiry timestamp would be ideal, but
    # expires_at is stored as an ISO string, so we index it for range scans only.
    ("otps", [("expires_at", ASCENDING)], {"name": "ix_otps_expires"}),
    # calendar_events
    ("calendar_events", [("user_id", ASCENDING)], {"name": "ix_events_user"}),
    ("calendar_events", [("project_id", ASCENDING)], {"name": "ix_events_project"}),
    ("calendar_events", [("start", ASCENDING)], {"name": "ix_events_start"}),
    # focus_sessions
    ("focus_sessions", [("user_id", ASCENDING)], {"name": "ix_focus_user"}),
    # ai_conversations
    ("ai_conversations", [("user_id", ASCENDING), ("session_id", ASCENDING)], {"name": "ix_aiconvo_user_session"}),
    # ai_memory
    ("ai_memory", [("user_id", ASCENDING)], {"name": "ix_aimemory_user"}),
    # canvases
    ("canvases", [("user_id", ASCENDING)], {"name": "ix_canvases_user"}),
    # timeblocks
    ("timeblocks", [("user_id", ASCENDING)], {"name": "ix_timeblocks_user"}),
    # invites
    ("invites", [("invite_token", ASCENDING)], {"name": "ix_invites_token"}),
    ("invites", [("invited_by", ASCENDING)], {"name": "ix_invites_invitedby"}),
    # user_settings
    ("user_settings", [("user_id", ASCENDING)], {"unique": True, "name": "ux_usersettings_user"}),
    # share_briefs
    ("share_briefs", [("token", ASCENDING)], {"unique": True, "name": "ux_briefs_token"}),
    ("share_briefs", [("user_id", ASCENDING)], {"name": "ix_briefs_user"}),
    # activity_feed (Phase 1) — newest-first reads, plus department/actor filters
    ("activity_feed", [("created_at", DESCENDING)], {"name": "ix_activity_created"}),
    ("activity_feed", [("department_id", ASCENDING), ("created_at", DESCENDING)], {"name": "ix_activity_dept_created"}),
    ("activity_feed", [("actor_id", ASCENDING)], {"name": "ix_activity_actor"}),
    ("activity_feed", [("object_type", ASCENDING), ("object_id", ASCENDING)], {"name": "ix_activity_object"}),
    ("activity_feed", [("actor_id", ASCENDING), ("created_at", DESCENDING)], {"name": "ix_activity_actor_created"}),
    # escalations (Phase 2) — one record per (entity_type, entity_id) tracking the level reached
    ("escalations", [("entity_type", ASCENDING), ("entity_id", ASCENDING)], {"unique": True, "name": "ux_escalations_entity"}),
    # Phase 3 — knowledge base
    ("knowledge_articles", [("id", ASCENDING)], {"unique": True, "name": "ux_kb_id"}),
    ("knowledge_articles", [("department_id", ASCENDING), ("status", ASCENDING)], {"name": "ix_kb_dept_status"}),
    ("knowledge_articles", [("owner_id", ASCENDING)], {"name": "ix_kb_owner"}),
    ("knowledge_articles", [("article_type", ASCENDING)], {"name": "ix_kb_type"}),
    ("knowledge_articles", [("tags", ASCENDING)], {"name": "ix_kb_tags"}),
    ("knowledge_versions", [("article_id", ASCENDING), ("version", DESCENDING)], {"name": "ix_kbver_article"}),
    # Phase 3 — AI summaries + digests
    ("ai_summaries", [("summary_type", ASCENDING), ("subject_type", ASCENDING), ("subject_id", ASCENDING)], {"name": "ix_aisum_subject"}),
    ("ai_summaries", [("created_at", DESCENDING)], {"name": "ix_aisum_created"}),
    ("executive_digests", [("period_type", ASCENDING), ("period_start", DESCENDING)], {"name": "ix_digest_period"}),
    ("executive_digests", [("id", ASCENDING)], {"unique": True, "name": "ux_digest_id"}),
    # Phase 4 — CRM client activities (per-entity timeline)
    ("crm_activities", [("crm_entity_type", ASCENDING), ("crm_entity_id", ASCENDING), ("created_at", DESCENDING)], {"name": "ix_crmact_entity"}),
    ("crm_activities", [("actor_id", ASCENDING)], {"name": "ix_crmact_actor"}),
    ("crm_activities", [("id", ASCENDING)], {"unique": True, "name": "ux_crmact_id"}),
    # Phase 5 — notification center
    ("notifications", [("user_id", ASCENDING), ("read", ASCENDING), ("archived", ASCENDING), ("created_at", DESCENDING)], {"name": "ix_notif_user"}),
    ("notifications", [("user_id", ASCENDING), ("category", ASCENDING)], {"name": "ix_notif_user_cat"}),
    ("notifications", [("id", ASCENDING)], {"unique": True, "name": "ux_notif_id"}),
    # Phase 5 — global search history
    ("search_history", [("user_id", ASCENDING), ("at", DESCENDING)], {"name": "ix_searchhist_user"}),
    ("search_history", [("user_id", ASCENDING), ("q", ASCENDING)], {"unique": True, "name": "ux_searchhist_user_q"}),
    # Phase 5 — observability
    ("api_metrics", [("id", ASCENDING)], {"unique": True, "name": "ux_apimetrics_id"}),
    ("api_errors", [("created_at", DESCENDING)], {"name": "ix_apierrors_created"}),
]


async def create_indexes() -> int:
    """Create all indexes idempotently. Returns the count created/ensured."""
    ok = 0
    for coll, keys, opts in _INDEX_SPECS:
        try:
            await db[coll].create_index(keys, **opts)
            ok += 1
        except Exception as exc:  # noqa: BLE001 - never let one bad index stop startup
            log.warning(f"Index ensure failed on {coll} {opts.get('name')}: {exc}")
    log.info(f"Mongo indexes ensured: {ok}/{len(_INDEX_SPECS)}")
    return ok


async def mongo_healthcheck() -> bool:
    try:
        await db.command("ping")
        return True
    except Exception:  # noqa: BLE001
        return False
