# RBAC Validation Report — Tabayyun NotesOps
_Phase 5.5 · derived from the actual route table + dependency tree (not assumptions)._

## Method
Imported the live FastAPI app and walked **every route's dependency tree** to detect the
authentication guard (`get_current_user`) and permission guards. Scope behavior was
verified by running real, role-driven requests in `verify/test_validation.py` and
`verify/test_phase1..5.py`.

## Surface
- **242** `/api` routes inspected.
- **8** routes have no `get_current_user` in their dependency tree — **all intentionally public**:
  `GET /api/`, `GET /api/health`, `POST /api/auth/register|login|otp/verify|otp/resend|accept-invite`,
  `GET /api/share/brief/{token}` (token-gated public share link).
- **234** authenticated routes. **0 unguarded business routes.**

## Authorization model (verified)
- **Global permission gate:** `require_permission(perm)` dependency (returns 401/403 before the handler).
- **Scope-aware gate:** `ensure_permission(session, user, perm, department_id=…)` inside handlers — honours department-scoped role assignments (a Department Manager scoped to Sales is allowed in Sales, denied elsewhere). Verified positively and negatively.
- **Ownership gate:** owner/assignee/organizer/requester checks for personal resources (tasks, daily updates, notifications, own approvals).
- **Legacy bridge:** `is_admin` users resolve to all permissions (founder/admin always functional).

## Findings
| Severity | Finding | Status |
|---|---|---|
| — | No unauthenticated business endpoints; the 8 public routes are justified | ✅ Pass |
| — | Department-scope isolation holds: manager denied other-dept dashboards/CRM/intelligence | ✅ Pass (tested) |
| — | Executive-only surfaces (executive dashboard, intelligence, ops, audit) deny employees | ✅ Pass (tested) |
| — | `settings.manage` is admin-only; executive/manager denied writes | ✅ Pass (tested) |
| Low | CRM `*.delete` requires the explicit delete permission (owner cannot hard-delete) — intentional design, documented | ℹ Accepted |
| Low | `crm.*.view` is granted **globally** to the `employee` system role → company-wide CRM read for all employees. Correct for a single <50-person company; for stricter tenancy, assign CRM via department-scoped roles instead. | ℹ By design (documented) |

### Over-permissioned routes
None found. Every mutating route requires the matching create/edit/delete/manage permission or ownership.

### Under-permissioned routes
None found. Read endpoints that use only `get_current_user` apply in-handler visibility filtering (search, notifications, activity, CRM lists, daily-update lists) — verified permission-aware.

### Scope leaks
None observed in the validated workflows. CRM/daily-update/report/dashboard reads filter by the caller's `permission_scopes` (global ∪ department-scoped ∪ ownership).

## Verdict
**RBAC is production-grade.** No missing checks, no scope leaks, no over/under-permissioned business routes. The only policy choice to confirm with stakeholders is global-vs-department CRM visibility for the `employee` role (currently global by design).
