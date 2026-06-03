# Pilot User Journeys — Tabayyun NotesOps
_Phase 6 · Module 14. Each journey lists the screens used, permissions required, and the
expected workflow. All screens call REAL APIs (no mocks)._

> Setup once (admin): create departments + employees with reporting lines, then assign
> system roles (`executive`, `department_manager` scoped to a department, `employee`) via
> **Organization → Roles & RBAC**.

## 1) CEO / Executive
**Screens:** Executive Dashboard · CRM (Intelligence/Pipeline) · Operations Center · Notification bell.
**Permissions:** `company.dashboard.view`, `intelligence.view`, `report.view_company`, `crm.*.view`, `ops.view`, `audit.view` (all via the `executive` role).
**Workflow:** Open **Executive** → see company health score, department health, operational risks, escalations, pending approvals, CRM pipeline & weighted forecast, and executive recommendations. Drill into **CRM → Intelligence** for revenue insights. Check **Operations** for system/scheduler/error health. The bell surfaces escalations and approvals needing attention.

## 2) Department Manager
**Screens:** Daily Updates · Meetings (+MOM + action items) · Approvals · CRM · Organization (read) · Notification bell.
**Permissions:** `department_manager` **scoped to their department** — `daily_update.view_team/department`, `meeting.create/edit/cancel/mom.*`, `approval.approve/view`, `crm.*` (full in-scope), `report.view_department`, `department.dashboard.view`, `kb.view/create/edit`.
**Workflow:** Review the team's **Daily Updates**; run a **Meeting**, record **MOM**, add **action items** (each auto-creates an owned task); decide **Approvals** routed to them by the reporting chain; manage **CRM** companies/leads/opportunities for their department; export lists to CSV/XLSX.

## 3) Employee
**Screens:** Dashboard · Tasks · Daily Updates · Meetings (view + own action items) · Knowledge Base · CRM (in scope) · Approvals (raise) · Notification bell.
**Permissions:** `employee` (global) — `task.manage`, `daily_update.submit`, `meeting.view/mom.view`, `approval.create/view`, `kb.view`, `crm.*.view/create/edit`.
**Workflow:** Submit the **Daily Update** (today/tomorrow/blockers, edit same-day); work **Tasks** (incl. tasks spawned from meeting action items); read **Knowledge Base**; raise an **Approval** request; get in-app notifications when tasks/approvals are assigned or escalated.

## 4) CRM User (Sales)
**Screens:** CRM (Companies · Contacts · Leads · Pipeline · Opportunities · Intelligence).
**Permissions:** `crm.company/contact/lead/opportunity.view+create+edit` (employee role or a CRM-scoped role).
**Workflow:** Create a **Company** and **Contact** → create a **Lead** → move it through stages → **Convert** to an **Opportunity** → manage it on the **Pipeline** board (stage changes) → watch the **Forecast** and **Intelligence** (stalled deals, follow-ups, at-risk revenue).

## Cross-cutting
- **Global search:** ⌘K / Ctrl-K opens the command palette; typing searches across tasks, projects, employees, departments, meetings, approvals, CRM, knowledge, and reports — **permission-filtered**; recent searches persist.
- **Notification Center:** the header bell shows unread count + a dropdown; the `/inbox` page filters by status (unread/read/archived) and category, with mark-read / archive / mark-all.
- **Exports:** CSV/XLSX buttons on Approvals, Meetings, CRM (companies/contacts/opportunities), and Knowledge — audited server-side.

## Verification note
Screens were built to the existing design system and the verified backend API contracts
(113/113 backend tests green). A full interactive smoke requires `npm install && npm start`
against a running backend — see the Phase 6 report's "Verification & limits".
