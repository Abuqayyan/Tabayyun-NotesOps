# Data Consistency Report — Tabayyun NotesOps
_Phase 5.5 · cross-database references, FK integrity, orphan/cleanup analysis._

## Architecture recap (hybrid, by design)
- **PostgreSQL** = relational system of record: org, RBAC, daily updates, meetings/action items, approvals, reports, **CRM** (companies/contacts/leads/opportunities + stage history + `crm_links`), client-portal schema.
- **MongoDB** = content/high-write: tasks, notes, projects, activity feed, AI summaries, digests, knowledge articles, CRM activities (timeline), notifications, escalations, observability.
- **Cross-store rule:** references by **UUID only**, no cross-DB joins/transactions. Postgres `department_id`/`owner_id`/`user_id` are **soft** references to Mongo/other ids (intentionally not FKs) → no cross-store integrity hazard.

## Intra-Postgres foreign keys — audit of delete paths
Traced every delete handler against the declared `ForeignKey`s.

| Parent delete | FK children | Before | After |
|---|---|---|---|
| `crm_companies` | `crm_contacts.company_id`, `crm_leads.company_id`, `crm_opportunities.company_id` | contacts+opps detached, **leads NOT detached** → FK violation on Postgres | ✅ **Fixed** — all three detached |
| `crm_contacts` | `crm_leads.contact_id`, `crm_opportunities.contact_id` | **neither detached** → FK violation on Postgres | ✅ **Fixed** — both detached |
| `departments` | `departments.parent_department_id` (self), `employees.primary_department_id` | members + employee dept handled, **child-department parent NOT nulled** → FK violation | ✅ **Fixed** — children detached |
| `crm_leads` | history (CASCADE), `crm_links` (manual) | OK | ✅ OK |
| `crm_opportunities` | history (CASCADE), `crm_links` (manual) | OK | ✅ OK |
| `meetings` | attendees + action items (ondelete CASCADE) | no delete endpoint (cancel only) | ✅ OK |
| `approval_templates` | template steps (manual delete) | OK | ✅ OK |
| `approval_requests` | steps (ondelete CASCADE) | OK | ✅ OK |
| `employees` | `employees.manager_id` (self) | reports detached | ✅ OK |

### Proof
With SQLite FK enforcement enabled (matching PostgreSQL semantics), deleting a contact
referenced by a lead **raised `IntegrityError` before the fix** and **succeeds after the
fix** (lead/opp `contact_id` nulled). Same verified for company delete. Covered by
`test_validation.py::test_referential_integrity_on_delete`.

> Note: the standard test harness runs SQLite with FK enforcement **off** (aiosqlite default),
> which is why these latent Postgres-only bugs were invisible until traced explicitly. This is
> itself a finding (see deployment report — enable FK PRAGMA or run a Postgres CI lane).

## Soft-reference dangling values (acceptable, documented)
After a parent delete, these soft (non-FK) references may remain and are tolerated by design
(reads null-guard them): `crm_opportunities.source_lead_id`, `crm_leads.converted_opportunity_id`,
`crm_links.target_id` → a cancelled/removed Mongo task, `activity_feed`/`crm_activities` historical
rows. The owning delete paths purge `crm_links` and `crm_activities` for the deleted entity.

## UUID link integrity (verified in workflows)
- Meeting **action item → Mongo task** two-way link (`action_item.task_id` ⇄ `task.source_meeting_id`) — consistent; completion syncs both sides.
- **CRM links** (opportunity ⇄ meeting/task) appear correctly in the unified timeline and are deleted with the entity.
- Approval **step instances** snapshot the template and resolve approvers from the live reporting chain — consistent.

## Verdict
**3 referential-integrity bugs found and fixed** (2 Critical for Postgres: CRM company/contact delete; 1 Medium: department parent). No remaining Postgres FK-violation paths. Hybrid soft-references are intentional and null-safe. **Data layer is consistent and production-safe.**
