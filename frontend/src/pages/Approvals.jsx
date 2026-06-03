import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { useLang } from "@/contexts/LanguageContext";
import { usePermissions } from "@/lib/usePermissions";
import { PageHeader, Section, Empty, Loading, Field, Input, Select, Modal, PrimaryButton, GhostButton, Badge } from "@/components/kit";
import ExportMenu from "@/components/ExportMenu";
import { Stamp, Check, X, Plus } from "lucide-react";
import { toast } from "sonner";

const STATUS_TONE = { pending: "amber", approved: "green", rejected: "red", cancelled: "muted" };

export default function Approvals() {
  const { t, lang } = useLang();
  const { has } = usePermissions();
  const [tab, setTab] = useState("to_approve");
  const [rows, setRows] = useState(null);
  const [templates, setTemplates] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ template_id: "", title: "" });
  const locale = lang === "ar" ? "ar-EG" : "en-US";

  const load = useCallback(() => {
    const params = tab === "all" ? {} : { mine: tab };
    api.get("/approvals/requests", { params }).then((r) => setRows(r.data)).catch(() => setRows([]));
  }, [tab]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { api.get("/approvals/templates").then((r) => setTemplates(r.data || [])).catch(() => {}); }, []);

  const decide = async (id, decision) => {
    try {
      await api.post(`/approvals/requests/${id}/decision`, { decision });
      toast.success(decision === "approve" ? t("تمت الموافقة", "Approved") : t("تم الرفض", "Rejected"));
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || t("فشل", "Failed")); }
  };

  const submit = async () => {
    if (!form.template_id) return toast.error(t("اختر نموذجًا", "Pick a template"));
    try {
      await api.post("/approvals/requests", form);
      toast.success(t("تم إرسال الطلب", "Request submitted"));
      setOpen(false); setForm({ template_id: "", title: "" }); setTab("requested"); load();
    } catch (e) { toast.error(e?.response?.data?.detail || t("فشل الإرسال", "Submit failed")); }
  };

  const TABS = [
    { id: "to_approve", label: t("بانتظار قراري", "To approve") },
    { id: "requested", label: t("طلباتي", "My requests") },
    ...(has("approval.view") ? [{ id: "all", label: t("الكل", "All") }] : []),
  ];

  return (
    <div className="p-6 lg:p-8 space-y-6" data-testid="approvals-page">
      <PageHeader label={t("العمليات", "Operations")} title={t("الموافقات", "Approvals")}
        subtitle={t("اطلب الموافقات وقرّر فيها عبر سلسلة الإدارة.", "Raise and decide requests along the management chain.")}
        actions={<>
          {has("export.data") && <ExportMenu entity="approvals" />}
          {has("approval.create") && <PrimaryButton data-testid="approval-new-btn" onClick={() => setOpen(true)}><Plus size={14} /> {t("طلب جديد", "New request")}</PrimaryButton>}
        </>} />

      <div className="flex items-center gap-1 border-b border-border">
        {TABS.map((x) => (
          <button key={x.id} onClick={() => setTab(x.id)} data-testid={`approval-tab-${x.id}`}
            className={`px-4 py-2 text-sm border-b-2 -mb-px ${tab === x.id ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"}`}>
            {x.label}
          </button>
        ))}
      </div>

      {rows === null ? <Loading label={t("تحميل…", "Loading…")} /> : (
        <Section>
          <div className="divide-y divide-border">
            {rows.length === 0 && <Empty>{t("لا طلبات في هذا العرض.", "Nothing here.")}</Empty>}
            {rows.map((r) => (
              <div key={r.id} className="px-5 py-3 flex items-center justify-between gap-3" data-testid="approval-row">
                <div className="min-w-0">
                  <div className="text-sm font-medium truncate">{r.title}</div>
                  <div className="text-xs text-muted-foreground">{t("خطوة", "Step")} {r.current_step} · {new Date(r.created_at).toLocaleDateString(locale)}</div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <Badge tone={STATUS_TONE[r.status]}>{r.status}</Badge>
                  {r.status === "pending" && r.can_decide && (
                    <>
                      <button data-testid="approve-btn" onClick={() => decide(r.id, "approve")} title={t("موافقة", "Approve")} className="w-8 h-8 flex items-center justify-center rounded-md border border-border hover:bg-emerald-500/10 text-emerald-500"><Check size={15} /></button>
                      <button data-testid="reject-btn" onClick={() => decide(r.id, "reject")} title={t("رفض", "Reject")} className="w-8 h-8 flex items-center justify-center rounded-md border border-border hover:bg-red-500/10 text-red-500"><X size={15} /></button>
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        </Section>
      )}

      <Modal open={open} onClose={() => setOpen(false)} title={t("طلب موافقة جديد", "New approval request")}
        footer={<><GhostButton onClick={() => setOpen(false)}>{t("إلغاء", "Cancel")}</GhostButton><PrimaryButton data-testid="approval-submit" onClick={submit}><Stamp size={14} /> {t("إرسال", "Submit")}</PrimaryButton></>}>
        <Field label={t("النموذج", "Template")}>
          <Select data-testid="approval-template" value={form.template_id} onChange={(e) => setForm({ ...form, template_id: e.target.value })}>
            <option value="">{t("اختر…", "Select…")}</option>
            {templates.map((tp) => <option key={tp.id} value={tp.id}>{tp.name}</option>)}
          </Select>
        </Field>
        <Field label={t("العنوان", "Title")}>
          <Input data-testid="approval-title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder={t("مثال: خصم ١٠٪", "e.g. 10% discount")} />
        </Field>
      </Modal>
    </div>
  );
}
