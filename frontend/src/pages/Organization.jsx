import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { useLang } from "@/contexts/LanguageContext";
import { usePermissions } from "@/lib/usePermissions";
import { PageHeader, Section, Empty, Loading, Field, Input, Select, Modal, PrimaryButton, GhostButton, Badge } from "@/components/kit";
import { Building2, Users, ShieldCheck, Plus, Trash2, UserPlus, Copy } from "lucide-react";
import { toast } from "sonner";

export default function Organization() {
  const { t } = useLang();
  const { has, isAdmin } = usePermissions();
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
      {tab === "employees" && <Employees has={has} isAdmin={isAdmin} />}
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

const EMPTY_EMP = { mode: "invite", email: "", name: "", user_id: "", position: "", primary_department_id: "", manager_id: "", role_id: "" };

function Employees({ has, isAdmin }) {
  const { t } = useLang();
  const [rows, setRows] = useState(null);
  const [users, setUsers] = useState([]);
  const [depts, setDepts] = useState([]);
  const [roles, setRoles] = useState([]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null); // {invite_url, temp_password, existing_user, emailed}
  const [form, setForm] = useState({ ...EMPTY_EMP, mode: isAdmin ? "invite" : "existing" });

  const load = useCallback(() => api.get("/employees").then((r) => setRows(r.data)).catch(() => setRows([])), []);
  useEffect(() => {
    load();
    api.get("/users").then((r) => setUsers(r.data || [])).catch(() => {});
    api.get("/departments").then((r) => setDepts(r.data || [])).catch(() => {});
    api.get("/rbac/roles").then((r) => setRoles(r.data || [])).catch(() => {});
  }, [load]);

  const reset = () => { setForm({ ...EMPTY_EMP, mode: isAdmin ? "invite" : "existing" }); setResult(null); };
  const close = () => { setOpen(false); reset(); };

  // user_ids that already have an employee profile (avoid duplicates in the picker)
  const taken = new Set((rows || []).map((e) => e.user_id));

  const save = async () => {
    setBusy(true);
    try {
      let userId = form.user_id;
      let invite = null;

      if (form.mode === "invite") {
        if (!form.email.trim()) { setBusy(false); return toast.error(t("أدخل البريد", "Enter an email")); }
        const inv = await api.post("/team/invite", { email: form.email.trim(), name: form.name.trim() || undefined });
        userId = inv.data.user_id;
        invite = inv.data;
      } else {
        if (!userId) { setBusy(false); return toast.error(t("اختر مستخدمًا", "Select a user")); }
      }

      // 1) employee profile
      await api.post("/employees", {
        user_id: userId,
        position: form.position || "",
        primary_department_id: form.primary_department_id || null,
        manager_id: form.manager_id || null,
      });

      // 2) optional role assignment (scope = chosen department, else global)
      if (form.role_id) {
        const body = { user_id: userId, role_id: form.role_id, scope_type: form.primary_department_id ? "department" : "global" };
        if (body.scope_type === "department") body.scope_id = form.primary_department_id;
        try { await api.post("/rbac/assignments", body); }
        catch (e) { toast.warning(t("أُضيف الموظف لكن تعذّر تعيين الدور: ", "Employee added but role not assigned: ") + (e?.response?.data?.detail || "")); }
      }

      toast.success(t("تمت إضافة الموظف", "Employee added"));
      load();
      api.get("/users").then((r) => setUsers(r.data || [])).catch(() => {});
      // Keep modal open to surface credentials for a brand-new invited account.
      if (invite && (invite.temp_password || (invite.invite_url && !invite.existing_user))) {
        setResult(invite);
      } else {
        close();
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || t("فشل", "Failed"));
    } finally { setBusy(false); }
  };

  const copy = (txt) => { try { navigator.clipboard?.writeText(txt); toast.success(t("تم النسخ", "Copied")); } catch { /* ignore */ } };

  if (rows === null) return <Loading label="…" />;
  const canManage = has("employee.manage");

  return (
    <Section title={t("الموظفون", "Employees")}
      actions={canManage && <PrimaryButton onClick={() => { reset(); setOpen(true); }} data-testid="emp-new"><UserPlus size={14} /> {t("إضافة موظف", "Add employee")}</PrimaryButton>}>
      <div className="divide-y divide-border">
        {rows.length === 0 && <Empty>{t("لا موظفين بعد. استخدم «إضافة موظف» لدعوة شخص وإنشاء ملفه.", "No employees yet. Use “Add employee” to invite someone and create their profile.")}</Empty>}
        {rows.map((e) => (
          <div key={e.id} className="px-5 py-3 flex items-center justify-between" data-testid="emp-row">
            <div><div className="text-sm font-medium">{e.user_name || e.user_id}</div><div className="text-xs text-muted-foreground">{[e.position, e.user_email].filter(Boolean).join(" · ") || "—"}</div></div>
            <Badge tone={e.employment_status === "active" ? "green" : "muted"}>{e.employment_status}</Badge>
          </div>
        ))}
      </div>

      <Modal open={open} onClose={close} title={t("إضافة موظف", "Add employee")}
        footer={result
          ? <PrimaryButton onClick={close} data-testid="emp-done">{t("تم", "Done")}</PrimaryButton>
          : <><GhostButton onClick={close}>{t("إلغاء", "Cancel")}</GhostButton><PrimaryButton onClick={save} disabled={busy} data-testid="emp-save">{busy ? t("جارٍ…", "Working…") : t("حفظ", "Save")}</PrimaryButton></>}>

        {result ? (
          <div className="space-y-3">
            <div className="text-sm text-green-600">{t("تمت إضافة الموظف بنجاح.", "Employee added successfully.")}</div>
            {result.existing_user
              ? <div className="text-sm text-muted-foreground">{t("هذا الحساب موجود مسبقًا — لم تتغيّر بياناته.", "This account already existed — its credentials were left unchanged.")}</div>
              : <>
                  <div className="text-xs text-muted-foreground">{result.emailed ? t("أُرسلت الدعوة بالبريد.", "Invite emailed.") : t("لم يُرسَل البريد — شارك البيانات يدويًا:", "Email not sent — share these manually:")}</div>
                  {result.temp_password && (
                    <div className="flex items-center justify-between border border-border rounded-md px-3 py-2">
                      <span className="text-sm">{t("كلمة مرور مؤقتة", "Temp password")}: <span className="font-mono">{result.temp_password}</span></span>
                      <button onClick={() => copy(result.temp_password)} className="text-muted-foreground hover:text-foreground" title={t("نسخ", "Copy")}><Copy size={14} /></button>
                    </div>
                  )}
                  {result.invite_url && (
                    <div className="flex items-center justify-between border border-border rounded-md px-3 py-2 gap-2">
                      <span className="text-xs truncate font-mono">{result.invite_url}</span>
                      <button onClick={() => copy(result.invite_url)} className="text-muted-foreground hover:text-foreground shrink-0" title={t("نسخ الرابط", "Copy link")}><Copy size={14} /></button>
                    </div>
                  )}
                </>}
          </div>
        ) : (
          <div className="space-y-3">
            {isAdmin && (
              <div className="flex gap-1 p-0.5 bg-secondary rounded-md text-sm">
                <button type="button" onClick={() => setForm({ ...form, mode: "invite" })} data-testid="emp-mode-invite"
                  className={`flex-1 py-1.5 rounded ${form.mode === "invite" ? "bg-card shadow-sm" : "text-muted-foreground"}`}>{t("دعوة شخص جديد", "Invite new")}</button>
                <button type="button" onClick={() => setForm({ ...form, mode: "existing" })} data-testid="emp-mode-existing"
                  className={`flex-1 py-1.5 rounded ${form.mode === "existing" ? "bg-card shadow-sm" : "text-muted-foreground"}`}>{t("مستخدم موجود", "Existing user")}</button>
              </div>
            )}

            {form.mode === "invite" ? (
              <div className="grid grid-cols-2 gap-3">
                <Field label={t("البريد الإلكتروني", "Email")}><Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} data-testid="emp-email" placeholder="name@company.com" /></Field>
                <Field label={t("الاسم", "Name")}><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="emp-name" /></Field>
              </div>
            ) : (
              <Field label={t("المستخدم", "User")}>
                <Select value={form.user_id} onChange={(e) => setForm({ ...form, user_id: e.target.value })} data-testid="emp-user">
                  <option value="">{t("اختر…", "Select…")}</option>
                  {users.filter((u) => !taken.has(u.id)).map((u) => <option key={u.id} value={u.id}>{u.name} ({u.email})</option>)}
                </Select>
              </Field>
            )}

            <div className="grid grid-cols-2 gap-3">
              <Field label={t("المنصب", "Position")}><Input value={form.position} onChange={(e) => setForm({ ...form, position: e.target.value })} data-testid="emp-position" /></Field>
              <Field label={t("القسم", "Department")}>
                <Select value={form.primary_department_id} onChange={(e) => setForm({ ...form, primary_department_id: e.target.value })} data-testid="emp-dept">
                  <option value="">{t("بدون", "None")}</option>{depts.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                </Select>
              </Field>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <Field label={t("المدير المباشر", "Manager")}>
                <Select value={form.manager_id} onChange={(e) => setForm({ ...form, manager_id: e.target.value })} data-testid="emp-manager">
                  <option value="">{t("بدون", "None")}</option>{rows.map((e) => <option key={e.id} value={e.id}>{e.user_name || e.user_id}</option>)}
                </Select>
              </Field>
              <Field label={t("الدور (اختياري)", "Role (optional)")}>
                <Select value={form.role_id} onChange={(e) => setForm({ ...form, role_id: e.target.value })} data-testid="emp-role">
                  <option value="">{t("بدون", "None")}</option>{roles.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
                </Select>
              </Field>
            </div>
            {form.role_id && <div className="text-xs text-muted-foreground">{form.primary_department_id ? t("سيُسنَد الدور بنطاق القسم المحدّد.", "Role will be scoped to the selected department.") : t("سيُسنَد الدور بنطاق عام (الشركة كلها).", "Role will be assigned globally (whole company).")}</div>}
          </div>
        )}
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
