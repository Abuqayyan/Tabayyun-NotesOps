"""Seeded permission catalog + system role templates.

Permissions are GRANULAR and NAMESPACED. Code checks PERMISSIONS (keys), never role
names — roles are fully configurable data. System roles are seeded but editable; they
are only protected from deletion (is_system). Future-phase permission keys (approvals,
finance, CRM, meetings, KB) are seeded now so roles can be configured ahead of those
modules; their endpoints arrive in later phases.
"""

# key, category, description
PERMISSIONS = [
    # Dashboards / reporting
    ("company.dashboard.view", "dashboard", "View the company-wide executive dashboard"),
    ("department.dashboard.view", "dashboard", "View a department dashboard"),
    ("report.view_company", "reporting", "View company-wide reports"),
    ("report.view_department", "reporting", "View department reports"),
    # Org
    ("department.view", "org", "View departments"),
    ("department.manage", "org", "Create/edit/delete departments"),
    ("employee.view", "org", "View employee profiles"),
    ("employee.manage", "org", "Create/edit employee profiles & reporting lines"),
    # RBAC
    ("role.view", "rbac", "View roles & permissions"),
    ("role.manage", "rbac", "Create/edit roles, assign permissions, assign users"),
    # Activity / audit
    ("activity.view_all", "activity", "View the company-wide activity feed"),
    ("activity.view_department", "activity", "View department activity"),
    ("audit.view", "audit", "View the audit log"),
    # Work
    ("project.create", "work", "Create projects"),
    ("project.manage", "work", "Manage any project"),
    ("task.manage", "work", "Manage any task"),
    # Daily updates (Phase 2)
    ("daily_update.submit", "daily_updates", "Submit a personal daily update"),
    ("daily_update.view_team", "daily_updates", "View direct reports' daily updates"),
    ("daily_update.view_department", "daily_updates", "View a department's daily updates"),
    ("daily_update.view_all", "daily_updates", "View all daily updates company-wide"),
    # Meetings (Phase 2)
    ("meeting.create", "meetings", "Create meetings"),
    ("meeting.edit", "meetings", "Edit meetings, attendees, action items"),
    ("meeting.cancel", "meetings", "Cancel meetings"),
    ("meeting.view", "meetings", "View meetings"),
    ("meeting.mom.edit", "meetings", "Edit minutes of meeting (notes/decisions/discussion)"),
    ("meeting.mom.view", "meetings", "View minutes of meeting"),
    # Approvals (Phase 2)
    ("approval.create", "approvals", "Submit approval requests"),
    ("approval.approve", "approvals", "Decide on approval steps assigned by role"),
    ("approval.view", "approvals", "View approval requests beyond your own"),
    ("approval.manage", "approvals", "Manage approval templates & override decisions"),
    # Knowledge base (Phase 3)
    ("kb.view", "knowledge", "View knowledge base articles (in scope)"),
    ("kb.create", "knowledge", "Create knowledge base articles"),
    ("kb.edit", "knowledge", "Edit knowledge base articles"),
    ("kb.delete", "knowledge", "Delete knowledge base articles"),
    # Intelligence layer (Phase 3)
    ("intelligence.view", "intelligence", "View executive intelligence: risks, recommendations, trends"),
    ("executive.digest.view", "intelligence", "View executive digests (daily/weekly/monthly)"),
    # Platform / operations (Phase 5)
    ("ops.view", "platform", "View the Admin Operations Center (system monitoring)"),
    ("settings.manage", "platform", "Manage company/notification/security/CRM settings"),
    ("export.data", "platform", "Export data (CSV/XLSX) within your access scope"),
    # CRM (Phase 4)
    ("crm.company.view", "crm", "View CRM companies (in scope)"),
    ("crm.company.create", "crm", "Create CRM companies"),
    ("crm.company.edit", "crm", "Edit CRM companies"),
    ("crm.company.delete", "crm", "Delete CRM companies"),
    ("crm.contact.view", "crm", "View CRM contacts (in scope)"),
    ("crm.contact.create", "crm", "Create CRM contacts"),
    ("crm.contact.edit", "crm", "Edit CRM contacts"),
    ("crm.contact.delete", "crm", "Delete CRM contacts"),
    ("crm.lead.view", "crm", "View CRM leads (in scope)"),
    ("crm.lead.create", "crm", "Create CRM leads"),
    ("crm.lead.edit", "crm", "Edit CRM leads & move stages"),
    ("crm.lead.delete", "crm", "Delete CRM leads"),
    ("crm.opportunity.view", "crm", "View CRM opportunities (in scope)"),
    ("crm.opportunity.create", "crm", "Create CRM opportunities"),
    ("crm.opportunity.edit", "crm", "Edit CRM opportunities & move stages"),
    ("crm.opportunity.delete", "crm", "Delete CRM opportunities"),
    # Future phases (seeded ahead of their modules)
    ("request.approve", "approvals", "Approve requests in an approval chain"),
    ("finance.view", "finance", "View financial data"),
    ("crm.manage", "crm", "Manage all CRM records (all scopes, hard delete)"),
    ("kb.manage", "knowledge", "Manage the knowledge base (all scopes, hard delete)"),
    ("meeting.manage", "meetings", "Manage meetings"),
]

# Convenience groupings used by system-role seeding.
_CRM_VIEW = ["crm.company.view", "crm.contact.view", "crm.lead.view", "crm.opportunity.view"]
_CRM_WRITE = _CRM_VIEW + [
    "crm.company.create", "crm.company.edit", "crm.contact.create", "crm.contact.edit",
    "crm.lead.create", "crm.lead.edit", "crm.opportunity.create", "crm.opportunity.edit",
]
_CRM_FULL = _CRM_WRITE + ["crm.company.delete", "crm.contact.delete", "crm.lead.delete", "crm.opportunity.delete"]

ALL_PERMISSION_KEYS = [p[0] for p in PERMISSIONS]

# System roles: key -> {name, description, permissions ('*' = all)}
SYSTEM_ROLES = {
    "administrator": {
        "name": "Administrator",
        "description": "Full access to the entire platform.",
        "permissions": "*",
    },
    "executive": {
        "name": "Executive",
        "description": "Company-wide visibility (dashboards, reports, activity, audit).",
        "permissions": [
            "company.dashboard.view", "report.view_company", "report.view_department",
            "activity.view_all", "audit.view", "department.view", "employee.view", "role.view",
            "daily_update.view_all", "meeting.view", "meeting.mom.view",
            "approval.view", "approval.approve",
            "intelligence.view", "executive.digest.view", "kb.view",
            "ops.view", "export.data",
        ] + _CRM_VIEW,
    },
    "department_manager": {
        "name": "Department Manager",
        "description": "Manage and monitor a single department (assign with department scope).",
        "permissions": [
            "department.dashboard.view", "report.view_department", "activity.view_department",
            "department.view", "employee.view", "project.create", "task.manage",
            "daily_update.submit", "daily_update.view_team", "daily_update.view_department",
            "meeting.create", "meeting.edit", "meeting.cancel", "meeting.view",
            "meeting.mom.edit", "meeting.mom.view",
            "approval.create", "approval.approve", "approval.view",
            "kb.view", "kb.create", "kb.edit", "export.data",
        ] + _CRM_FULL,
    },
    "employee": {
        "name": "Employee",
        "description": "Standard employee access.",
        "permissions": [
            "project.create", "task.manage", "department.view",
            "daily_update.submit", "meeting.view", "meeting.mom.view",
            "approval.create", "approval.view", "kb.view",
        ] + _CRM_WRITE,
    },
}
