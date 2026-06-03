import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { useLang } from "@/contexts/LanguageContext";
import { usePermissions } from "@/lib/usePermissions";
import { PageHeader, Section, Empty, Loading, Field, Input, Select, Modal, PrimaryButton, GhostButton, Badge, Stat } from "@/components/kit";
import ExportMenu from "@/components/ExportMenu";
import { Plus, Building2, Contact, Target, Kanban, Sparkles, TrendingUp, Search } from "lucide-react";
import { toast } from "sonner";

const LEAD_STAGES = ["new", "contacted", "qualified", "proposal", "negotiation", "won", "lost"];
const OPP_STAGES = ["prospecting", "qualification", "proposal", "negotiation", "won", "lost"];

export default function CRM() {
  const { t, lang } = useLang();
  const { has } = usePermissions();
  const [tab, setTab] = useState("pipeline");
  const locale = lang === "ar" ? "ar-EG" : "en-US";
  const money = (n) => new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(n || 0);

  const TABS = [
    { id: "pipeline", label: t("خط الأنابيب", "Pipeline"), icon: Kanban },
    { id: "opportunities", label: t("الفرص", "Opportunities"), icon: Target },
    { id: "leads", label: t("العملاء المحتملون", "Leads"), icon: TrendingUp },
    { id: "companies", label: t("الشركات", "Companies"), icon: Building2 },
    { id: "contacts", label: t("جهات الاتصال", "Contacts"), icon: Contact },
    { id: "intelligence", label: t("الذكاء", "Intelligence"), icon: Sparkles },
  ];

  return (
    <div className="p-6 lg:p-8 space-y-6" data-testid="crm-page">
      <PageHeader label={t("المبيعات", "Sales")} title={t("إدارة العملاء", "CRM")}
        subtitle={t("الشركات وجهات الاتصال والصفقات وخط الأنابيب.", "Companies, contacts, deals, and pipeline.")} />

      <div className="flex items-center gap-1 border-b border-border overflow-x-auto">
        {TABS.map((x) => (
          <button key={x.id} onClick={() => setTab(x.id)} data-testid={`crm-tab-${x.id}`}
            className={`px-4 py-2 text-sm border-b-2 -mb-px flex items-center gap-1.5 whitespace-nowrap ${tab === x.id ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"}`}>
            <x.icon size={13} /> {x.label}
          </button>
        ))}
      </div>

      {tab === "pipeline" && <Pipeline money={money} />}
      {tab === "opportunities" && <Opportunities has={has} money={money} locale={locale} />}
      {tab === "leads" && <Leads has={has} money={money} />}
      {tab === "companies" && <Companies has={has} />}
      {tab === "contacts" && <Contacts has={has} />}
      {tab === "intelligence" && <Intelligence money={money} />}
    </div>
  );
}

function useList(url, params) {
  const [rows, setRows] = useState(null);
  const load = useCallback(() => { api.get(url, { params }).then((r) => setRows(r.data)).catch(() => setRows([])); }, [url, JSON.stringify(params)]);
  useEffect(() => { load(); }, [load]);
  return [rows, load];
}

function Pipeline({ money }) {
  const { t } = useLang();
  const [board, setBoard] = useState(null);
  useEffect(() => { api.get("/crm/pipeline").then((r) => setBoard(r.data)).catch(() => setBoard({ stages: [], board: {} })); }, []);
  if (!board) return <Loading label={t("تحميل خط الأنابيب…", "Loading pipeline…")} />;
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3" data-testid="crm-pipeline">
      {(board.stages || []).map((stage) => {
        const col = board.board[stage] || { count: 0, value: 0, items: [] };
        return (
          <div key={stage} className="border border-border bg-card rounded-md">
            <div className="hairline px-3 py-2 flex items-center justify-between">
              <span className="text-sm font-medium capitalize">{stage}</span>
              <span className="label-mono">{col.count}</span>
            </div>
            <div className="px-3 py-1.5 text-xs text-muted-foreground border-b border-border">{money(col.value)}</div>
            <div className="p-2 space-y-1.5 min-h-12">
              {(col.items || []).map((o) => (
                <div key={o.id} className="border border-border rounded-md px-2 py-1.5">
                  <div className="text-xs font-medium truncate">{o.name}</div>
                  <div className="font-mono text-[10px] text-muted-foreground">{money(o.expected_revenue)} · {o.probability}%</div>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function Opportunities({ has, money, locale }) {
  const { t } = useLang();
  const [rows, load] = useList("/crm/opportunities", { limit: 200 });
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", expected_revenue: 0, probability: 0, stage: "prospecting" });
  const save = async () => {
    try { await api.post("/crm/opportunities", form); toast.success(t("تم", "Created")); setOpen(false); setForm({ name: "", expected_revenue: 0, probability: 0, stage: "prospecting" }); load(); }
    catch (e) { toast.error(e?.response?.data?.detail || t("فشل", "Failed")); }
  };
  const move = async (id, stage) => { try { await api.patch(`/crm/opportunities/${id}`, { stage }); load(); } catch { toast.error(t("فشل", "Failed")); } };
  if (rows === null) return <Loading label="…" />;
  return (
    <Section title={t("الفرص", "Opportunities")} actions={<>
      {has("export.data") && <ExportMenu entity="crm_opportunities" />}
      {has("crm.opportunity.create") && <PrimaryButton onClick={() => setOpen(true)} data-testid="opp-new"><Plus size={14} /> {t("فرصة", "Opportunity")}</PrimaryButton>}
    </>}>
      <div className="divide-y divide-border">
        {rows.length === 0 && <Empty>{t("لا فرص.", "No opportunities.")}</Empty>}
        {rows.map((o) => (
          <div key={o.id} className="px-5 py-3 flex items-center justify-between gap-3" data-testid="opp-row">
            <div className="min-w-0"><div className="text-sm font-medium truncate">{o.name}</div><div className="text-xs text-muted-foreground">{money(o.expected_revenue)} · {o.probability}%</div></div>
            <div className="flex items-center gap-2 shrink-0">
              <Badge tone={o.status === "won" ? "green" : o.status === "lost" ? "red" : "blue"}>{o.status}</Badge>
              {has("crm.opportunity.edit") ? (
                <Select value={o.stage} onChange={(e) => move(o.id, e.target.value)} className="w-36">
                  {OPP_STAGES.map((s) => <option key={s} value={s}>{s}</option>)}
                </Select>
              ) : <Badge>{o.stage}</Badge>}
            </div>
          </div>
        ))}
      </div>
      <Modal open={open} onClose={() => setOpen(false)} title={t("فرصة جديدة", "New opportunity")}
        footer={<><GhostButton onClick={() => setOpen(false)}>{t("إلغاء", "Cancel")}</GhostButton><PrimaryButton onClick={save} data-testid="opp-save">{t("حفظ", "Save")}</PrimaryButton></>}>
        <Field label={t("الاسم", "Name")}><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="opp-name" /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("الإيراد المتوقع", "Expected revenue")}><Input type="number" value={form.expected_revenue} onChange={(e) => setForm({ ...form, expected_revenue: Number(e.target.value) })} /></Field>
          <Field label={t("الاحتمالية %", "Probability %")}><Input type="number" value={form.probability} onChange={(e) => setForm({ ...form, probability: Number(e.target.value) })} /></Field>
        </div>
        <Field label={t("المرحلة", "Stage")}><Select value={form.stage} onChange={(e) => setForm({ ...form, stage: e.target.value })}>{OPP_STAGES.map((s) => <option key={s} value={s}>{s}</option>)}</Select></Field>
      </Modal>
    </Section>
  );
}

function Leads({ has, money }) {
  const { t } = useLang();
  const [rows, load] = useList("/crm/leads", { limit: 200 });
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ title: "", value: 0, probability: 0, stage: "new" });
  const save = async () => {
    try { await api.post("/crm/leads", form); toast.success(t("تم", "Created")); setOpen(false); setForm({ title: "", value: 0, probability: 0, stage: "new" }); load(); }
    catch (e) { toast.error(e?.response?.data?.detail || t("فشل", "Failed")); }
  };
  const convert = async (id) => { try { await api.post(`/crm/leads/${id}/convert`, {}); toast.success(t("تم التحويل لفرصة", "Converted to opportunity")); load(); } catch (e) { toast.error(e?.response?.data?.detail || t("فشل", "Failed")); } };
  const move = async (id, stage) => { try { await api.patch(`/crm/leads/${id}`, { stage }); load(); } catch { toast.error(t("فشل", "Failed")); } };
  if (rows === null) return <Loading label="…" />;
  return (
    <Section title={t("العملاء المحتملون", "Leads")} actions={has("crm.lead.create") && <PrimaryButton onClick={() => setOpen(true)} data-testid="lead-new"><Plus size={14} /> {t("عميل محتمل", "Lead")}</PrimaryButton>}>
      <div className="divide-y divide-border">
        {rows.length === 0 && <Empty>{t("لا عملاء محتملين.", "No leads.")}</Empty>}
        {rows.map((l) => (
          <div key={l.id} className="px-5 py-3 flex items-center justify-between gap-3" data-testid="lead-row">
            <div className="min-w-0"><div className="text-sm font-medium truncate">{l.title || "—"}</div><div className="text-xs text-muted-foreground">{money(l.value)} · {l.probability}%</div></div>
            <div className="flex items-center gap-2 shrink-0">
              {has("crm.lead.edit") ? <Select value={l.stage} onChange={(e) => move(l.id, e.target.value)} className="w-32">{LEAD_STAGES.map((s) => <option key={s} value={s}>{s}</option>)}</Select> : <Badge>{l.stage}</Badge>}
              {has("crm.lead.edit") && !l.converted_opportunity_id && <GhostButton onClick={() => convert(l.id)} data-testid="lead-convert">{t("تحويل", "Convert")}</GhostButton>}
            </div>
          </div>
        ))}
      </div>
      <Modal open={open} onClose={() => setOpen(false)} title={t("عميل محتمل جديد", "New lead")}
        footer={<><GhostButton onClick={() => setOpen(false)}>{t("إلغاء", "Cancel")}</GhostButton><PrimaryButton onClick={save} data-testid="lead-save">{t("حفظ", "Save")}</PrimaryButton></>}>
        <Field label={t("العنوان", "Title")}><Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} data-testid="lead-title" /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("القيمة", "Value")}><Input type="number" value={form.value} onChange={(e) => setForm({ ...form, value: Number(e.target.value) })} /></Field>
          <Field label={t("الاحتمالية %", "Probability %")}><Input type="number" value={form.probability} onChange={(e) => setForm({ ...form, probability: Number(e.target.value) })} /></Field>
        </div>
      </Modal>
    </Section>
  );
}

function Companies({ has }) {
  const { t } = useLang();
  const [q, setQ] = useState("");
  const [rows, load] = useList("/crm/companies", { limit: 200 });
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", industry: "", country: "" });
  const save = async () => { try { await api.post("/crm/companies", form); toast.success(t("تم", "Created")); setOpen(false); setForm({ name: "", industry: "", country: "" }); load(); } catch (e) { toast.error(e?.response?.data?.detail || t("فشل", "Failed")); } };
  if (rows === null) return <Loading label="…" />;
  const filtered = q ? rows.filter((c) => (c.name || "").toLowerCase().includes(q.toLowerCase())) : rows;
  return (
    <Section title={t("الشركات", "Companies")} actions={<>
      {has("export.data") && <ExportMenu entity="crm_companies" />}
      {has("crm.company.create") && <PrimaryButton onClick={() => setOpen(true)} data-testid="company-new"><Plus size={14} /> {t("شركة", "Company")}</PrimaryButton>}
    </>}>
      <div className="px-5 py-2 border-b border-border flex items-center gap-2"><Search size={13} className="text-muted-foreground" /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("بحث…", "Search…")} className="bg-transparent outline-none text-sm flex-1" data-testid="company-search" /></div>
      <div className="divide-y divide-border">
        {filtered.length === 0 && <Empty>{t("لا شركات.", "No companies.")}</Empty>}
        {filtered.map((c) => (
          <div key={c.id} className="px-5 py-3 flex items-center justify-between gap-3" data-testid="company-row">
            <div className="min-w-0"><div className="text-sm font-medium truncate">{c.name}</div><div className="text-xs text-muted-foreground">{[c.industry, c.country].filter(Boolean).join(" · ") || "—"}</div></div>
            <Badge tone={c.status === "active" ? "green" : "muted"}>{c.status}</Badge>
          </div>
        ))}
      </div>
      <Modal open={open} onClose={() => setOpen(false)} title={t("شركة جديدة", "New company")}
        footer={<><GhostButton onClick={() => setOpen(false)}>{t("إلغاء", "Cancel")}</GhostButton><PrimaryButton onClick={save} data-testid="company-save">{t("حفظ", "Save")}</PrimaryButton></>}>
        <Field label={t("الاسم", "Name")}><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="company-name" /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("القطاع", "Industry")}><Input value={form.industry} onChange={(e) => setForm({ ...form, industry: e.target.value })} /></Field>
          <Field label={t("الدولة", "Country")}><Input value={form.country} onChange={(e) => setForm({ ...form, country: e.target.value })} /></Field>
        </div>
      </Modal>
    </Section>
  );
}

function Contacts({ has }) {
  const { t } = useLang();
  const [rows, load] = useList("/crm/contacts", { limit: 200 });
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ full_name: "", email: "", position: "" });
  const save = async () => { try { await api.post("/crm/contacts", form); toast.success(t("تم", "Created")); setOpen(false); setForm({ full_name: "", email: "", position: "" }); load(); } catch (e) { toast.error(e?.response?.data?.detail || t("فشل", "Failed")); } };
  if (rows === null) return <Loading label="…" />;
  return (
    <Section title={t("جهات الاتصال", "Contacts")} actions={<>
      {has("export.data") && <ExportMenu entity="crm_contacts" />}
      {has("crm.contact.create") && <PrimaryButton onClick={() => setOpen(true)} data-testid="contact-new"><Plus size={14} /> {t("جهة اتصال", "Contact")}</PrimaryButton>}
    </>}>
      <div className="divide-y divide-border">
        {rows.length === 0 && <Empty>{t("لا جهات اتصال.", "No contacts.")}</Empty>}
        {rows.map((c) => (
          <div key={c.id} className="px-5 py-3 flex items-center justify-between gap-3" data-testid="contact-row">
            <div className="min-w-0"><div className="text-sm font-medium truncate">{c.full_name}</div><div className="text-xs text-muted-foreground">{[c.position, c.email].filter(Boolean).join(" · ") || "—"}</div></div>
          </div>
        ))}
      </div>
      <Modal open={open} onClose={() => setOpen(false)} title={t("جهة اتصال جديدة", "New contact")}
        footer={<><GhostButton onClick={() => setOpen(false)}>{t("إلغاء", "Cancel")}</GhostButton><PrimaryButton onClick={save} data-testid="contact-save">{t("حفظ", "Save")}</PrimaryButton></>}>
        <Field label={t("الاسم الكامل", "Full name")}><Input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} data-testid="contact-name" /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("البريد", "Email")}><Input value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
          <Field label={t("المنصب", "Position")}><Input value={form.position} onChange={(e) => setForm({ ...form, position: e.target.value })} /></Field>
        </div>
      </Modal>
    </Section>
  );
}

function Intelligence({ money }) {
  const { t } = useLang();
  const [data, setData] = useState(undefined);
  useEffect(() => { api.get("/crm/intelligence").then((r) => setData(r.data)).catch(() => setData(null)); }, []);
  if (data === undefined) return <Loading label={t("تحليل خط الأنابيب…", "Analyzing pipeline…")} />;
  if (data === null) return <Empty>{t("لا تملك صلاحية ذكاء CRM.", "No access to CRM intelligence.")}</Empty>;
  const f = data.forecast_insights || {};
  return (
    <div className="space-y-4" data-testid="crm-intelligence">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Stat label={t("خط مفتوح", "Open pipeline")} value={money(f.open_pipeline)} />
        <Stat label={t("متوقع مرجح", "Weighted forecast")} value={money(f.weighted_forecast)} />
        <Stat label={t("إيراد محقق", "Won revenue")} value={money(f.won_revenue)} />
        <Stat label={t("إيراد بخطر", "At-risk revenue")} value={money(f.at_risk_revenue)} color="text-amber-500" />
      </div>
      <Section title={t("سرد ذكي", "AI narrative")}><div className="p-5 text-sm text-muted-foreground">{data.narrative}</div></Section>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Section title={t("المخاطر", "Risks")}>
          <div className="divide-y divide-border">
            {(data.risks || []).length === 0 && <Empty>{t("لا مخاطر.", "No risks.")}</Empty>}
            {(data.risks || []).map((r, i) => (
              <div key={i} className="px-5 py-3 flex items-center justify-between"><span className="text-sm">{r.title}</span><Badge tone={r.level === "high" || r.level === "critical" ? "red" : "amber"}>{r.level}</Badge></div>
            ))}
          </div>
        </Section>
        <Section title={t("متابعات مقترحة", "Follow-ups")}>
          <div className="divide-y divide-border">
            {(data.follow_up_recommendations || []).length === 0 && <Empty>{t("لا متابعات.", "None.")}</Empty>}
            {(data.follow_up_recommendations || []).slice(0, 10).map((r, i) => (
              <div key={i} className="px-5 py-3"><div className="text-sm font-medium">{r.title}</div><div className="text-xs text-muted-foreground">{r.reason}</div></div>
            ))}
          </div>
        </Section>
      </div>
    </div>
  );
}
