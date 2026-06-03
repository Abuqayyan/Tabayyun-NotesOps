import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { useLang } from "@/contexts/LanguageContext";
import { usePermissions } from "@/lib/usePermissions";
import { PageHeader, Section, Empty, Loading, Field, Input, Select, Modal, PrimaryButton, GhostButton, Badge } from "@/components/kit";
import { Building2, Users, ShieldCheck, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

export default function Organization() {
  const { t } = useLang();
  const { has } = usePermissions();
  const [tab, setTab] = useState("departments");
  const TABS = [
    { id: "departments", label: t("الأقسام", "Departments"), icon: Building2, show: has("department.view") },
    { id: "employees", label: t("الموظفون", "Employees"), icon: Users, show: has("employee.view") },
    { id: "roles", label: t("الأدوار والصلاحيات", "Roles & RBAC"), icon: ShieldCheck, show: has("role.view") || has("role.manage") },
  ].filter((x) => x.show !== false);

  return (
    <div className="p-6 lg:p-8 space-y-6" data-testid="organization-page">
      <PageHeader label={t("الإدارة", "Administration")} title={t("التنظيم", "Organization")}
        subtitle={t("الأقسام والموظفون والأدوار والصلاحيات.", "Departments, employees, roles, and permissions.")} />
      <div className="flex items-center gap-1 border-b border-border overflow-x-auto">
        {TABS.map((x) => (
          <button key={x.id} onClick={() => setTab(x.id)} data-testid={`org-tab-${x.id}`}
            className={`px-4 py-2 text-sm border-b-2 -mb-px flex items-center gap-1.5 whitespace-nowrap ${tab === x.id ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"}`}>
            <x.icon size={13} /> {x.label}
          </button>
        ))}
      </div>
      {tab === "departments" && <Departments has={has} />}
      {tab === "employees" && <Employees has={has} />}
      {tab === "roles" && <Roles has={has} />}
    </div>
  );
}

function Departments({ has }) {
  const { t } = useLang();
  const [rows, setRows] = useState(null);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", description: "" });
  const load = useCallback(() => api.get("/departments").then((r) => setRows(r.data)).catch(() => setRows([])), []);
  useEffect(() => { load(); }, [load]);
  const save = async () => { try { await api.post("/departments", form); toast.success(t("تم", "Created")); setOpen(false); setForm({ name: "", description: "" }); load(); } catch (e) { toast.error(e?.response?.data?.detail || t("فشل", "Failed")); } };
  if (rows === null) return <Loading label="…" />;
  return (
    <Section title={t("الأقسام", "Departments")} actions={has("department.manage") && <PrimaryButton onClick={() => setOpen(true)} data-testid="dept-new"><Plus size={14} /> {t("قسم", "Department")}</PrimaryButton>}>
      <div className="divide-y divide-border">
        {rows.length === 0 && <Empty>{t("لا أقسام.", "No departments.")}</Empty>}
        {rows.map((d) => (
          <div key={d.id} className="px-5 py-3 flex items-center justify-between" data-testid="dept-row">
            <div><div className="text-sm font-medium">{d.name}</div><div className="text-xs text-muted-foreground">{d.description || "—"}</div></div>
            <Badge tone={d.is_active ? "green" : "muted"}>{d.is_active ? t("نشط", "active") : t("معطل", "inactive")}</Badge>
          </div>
        ))}
      </div>
      <Modal open={open} onClose={() => setOpen(false)} title={t("قسم جديد", "New department")}
        footer={<><GhostButton onClick={() => setOpen(false)}>{t("إلغاء", "Cancel")}</GhostButton><PrimaryButton onClick={save} data-testid="dept-save">{t("حفظ", "Save")}</PrimaryButton></>}>
        <Field label={t("الاسم", "Name")}><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="dept-name" /></Field>
        <Field label={t("الوصف", "Description")}><Input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field>
      </Modal>
    </Section>
  );
}

function Employees({ has }) {
  const { t } = useLang();
  const [rows, setRows] = useState(null);
  const [users, setUsers] = useState([]);
  const [depts, setDepts] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ user_id: "", position: "", primary_department_id: "" });
  const load = useCallback(() => api.get("/employees").then((r) => setRows(r.data)).catch(() => setRows([])), []);
  useEffect(() => {
    load();
    api.get("/users").then((r) => setUsers(r.data || [])).catch(() => {});
    api.get("/departments").then((r) => setDepts(r.data || [])).catch(() => {});
  }, [load]);
  const save = async () => { try { await api.post("/employees", form); toast.success(t("تم", "Created")); setOpen(false); setForm({ user_id: "", position: "", primary_department_id: "" }); load(); } catch (e) { toast.error(e?.response?.data?.detail || t("فشل", "Failed")); } };
  if (rows === null) return <Loading label="…" />;
  return (
    <Section title={t("الموظفون", "Employees")} actions={has("employee.manage") && <PrimaryButton onClick={() => setOpen(true)} data-testid="emp-new"><Plus size={14} /> {t("موظف", "Employee")}</PrimaryButton>}>
      <div className="divide-y divide-border">
        {rows.length === 0 && <Empty>{t("لا موظفين.", "No employees.")}</Empty>}
        {rows.map((e) => (
          <div key={e.id} className="px-5 py-3 flex items-center justify-between" data-testid="emp-row">
            <div><div className="text-sm font-medium">{e.user_name || e.user_id}</div><div className="text-xs text-muted-foreground">{[e.position, e.user_email].filter(Boolean).join(" · ") || "—"}</div></div>
            <Badge tone={e.employment_status === "active" ? "green" : "muted"}>{e.employment_status}</Badge>
          </div>
        ))}
      </div>
      <Modal open={open} onClose={() => setOpen(false)} title={t("موظف جديد", "New employee")}
        footer={<><GhostButton onClick={() => setOpen(false)}>{t("إلغاء", "Cancel")}</GhostButton><PrimaryButton onClick={save} data-testid="emp-save">{t("حفظ", "Save")}</PrimaryButton></>}>
        <Field label={t("المستخدم", "User")}><Select value={form.user_id} onChange={(e) => setForm({ ...form, user_id: e.target.value })} data-testid="emp-user"><option value="">{t("اختر…", "Select…")}</option>{users.map((u) => <option key={u.id} value={u.id}>{u.name} ({u.email})</option>)}</Select></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("المنصب", "Position")}><Input value={form.position} onChange={(e) => setForm({ ...form, position: e.target.value })} /></Field>
          <Field label={t("القسم", "Department")}><Select value={form.primary_department_id} onChange={(e) => setForm({ ...form, primary_department_id: e.target.value })}><option value="">{t("بدون", "None")}</option>{depts.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</Select></Field>
        </div>
      </Modal>
    </Section>
  );
}

function Roles({ has }) {
  const { t } = useLang();
  const [roles, setRoles] = useState(null);
  const [assignments, setAssignments] = useState([]);
  const [users, setUsers] = useState([]);
  const [depts, setDepts] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ user_id: "", role_id: "", scope_type: "global", scope_id: "" });
  const load = useCallback(() => {
    api.get("/rbac/roles").then((r) => setRoles(r.data)).catch(() => setRoles([]));
    api.get("/rbac/assignments").then((r) => setAssignments(r.data || [])).catch(() => {});
  }, []);
  useEffect(() => {
    load();
    api.get("/users").then((r) => setUsers(r.data || [])).catch(() => {});
    api.get("/departments").then((r) => setDepts(r.data || [])).catch(() => {});
  }, [load]);
  const assign = async () => {
    try {
      const body = { user_id: form.user_id, role_id: form.role_id, scope_type: form.scope_type };
      if (form.scope_type !== "global" && form.scope_id) body.scope_id = form.scope_id;
      await api.post("/rbac/assignments", body); toast.success(t("تم التعيين", "Assigned")); setOpen(false); load();
    } catch (e) { toast.error(e?.response?.data?.detail || t("فشل", "Failed")); }
  };
  const unassign = async (id) => { try { await api.delete(`/rbac/assignments/${id}`); load(); } catch { toast.error(t("فشل", "Failed")); } };
  if (roles === null) return <Loading label="…" />;
  const roleName = (id) => roles.find((r) => r.id === id)?.name || id;
  const userName = (id) => users.find((u) => u.id === id)?.name || id;
  return (
    <div className="space-y-4">
      <Section title={t("الأدوار", "Roles")}>
        <div className="divide-y divide-border">
          {roles.map((r) => (
            <div key={r.id} className="px-5 py-3 flex items-center justify-between" data-testid="role-row">
              <div><div className="text-sm font-medium">{r.name}</div><div className="text-xs text-muted-foreground">{(r.permissions || []).length} {t("صلاحية", "permissions")}</div></div>
              {r.is_system && <Badge tone="primary">{t("نظام", "system")}</Badge>}
            </div>
          ))}
        </div>
      </Section>
      <Section title={t("التعيينات", "Assignments")} actions={has("role.manage") && <PrimaryButton onClick={() => setOpen(true)} data-testid="assign-new"><Plus size={14} /> {t("تعيين", "Assign")}</PrimaryButton>}>
        <div className="divide-y divide-border">
          {assignments.length === 0 && <Empty>{t("لا تعيينات.", "No assignments.")}</Empty>}
          {assignments.map((a) => (
            <div key={a.id} className="px-5 py-3 flex items-center justify-between" data-testid="assignment-row">
              <div className="text-sm"><span className="font-medium">{userName(a.user_id)}</span> · {roleName(a.role_id)} <Badge>{a.scope_type}</Badge></div>
              {has("role.manage") && <button onClick={() => unassign(a.id)} className="text-muted-foreground hover:text-red-500" title={t("إزالة", "Remove")}><Trash2 size={14} /></button>}
            </div>
          ))}
        </div>
      </Section>
      <Modal open={open} onClose={() => setOpen(false)} title={t("تعيين دور", "Assign role")}
        footer={<><GhostButton onClick={() => setOpen(false)}>{t("إلغاء", "Cancel")}</GhostButton><PrimaryButton onClick={assign} data-testid="assign-save">{t("تعيين", "Assign")}</PrimaryButton></>}>
        <Field label={t("المستخدم", "User")}><Select value={form.user_id} onChange={(e) => setForm({ ...form, user_id: e.target.value })} data-testid="assign-user"><option value="">{t("اختر…", "Select…")}</option>{users.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}</Select></Field>
        <Field label={t("الدور", "Role")}><Select value={form.role_id} onChange={(e) => setForm({ ...form, role_id: e.target.value })} data-testid="assign-role"><option value="">{t("اختر…", "Select…")}</option>{roles.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}</Select></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("النطاق", "Scope")}><Select value={form.scope_type} onChange={(e) => setForm({ ...form, scope_type: e.target.value })}><option value="global">global</option><option value="department">department</option></Select></Field>
          {form.scope_type === "department" && <Field label={t("القسم", "Department")}><Select value={form.scope_id} onChange={(e) => setForm({ ...form, scope_id: e.target.value })}><option value="">{t("اختر…", "Select…")}</option>{depts.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</Select></Field>}
        </div>
      </Modal>
    </div>
  );
}
