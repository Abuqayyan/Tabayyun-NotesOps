import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useLang } from "@/contexts/LanguageContext";
import { useAuth } from "@/contexts/AuthContext";
import { useSearchParams } from "react-router-dom";
import {
  Key, Cpu, Zap, CheckCircle2, AlertCircle, Loader2, Eye, EyeOff,
  Mail, Server, FileText, Lock, RefreshCw, Bell, Clock, Shield,
} from "lucide-react";
import { toast } from "sonner";

const TABS = [
  { key: "ai", icon: Cpu, ar: "الذكاء", en: "AI" },
  { key: "smtp", icon: Server, ar: "البريد (SMTP)", en: "Email (SMTP)" },
  { key: "templates", icon: FileText, ar: "قوالب البريد", en: "Email templates" },
  { key: "reminders", icon: Bell, ar: "التذكيرات", en: "Reminders" },
  { key: "security", icon: Lock, ar: "الأمان", en: "Security" },
];

export default function Settings() {
  const { lang, t } = useLang();
  const { user } = useAuth();
  const [params] = useSearchParams();
  const [tab, setTab] = useState(params.get("force") === "password" ? "security" : "ai");

  return (
    <div className="p-6 lg:p-8 space-y-6 max-w-5xl" data-testid="settings-page">
      <div>
        <div className="label-mono">{t("الإعدادات", "Settings")}</div>
        <h1 className="text-3xl sm:text-4xl tracking-tight font-medium mt-1">{t("الإعدادات", "Settings")}</h1>
        <p className="text-sm text-muted-foreground mt-1">{t("الذكاء، البريد، القوالب، والأمان.", "AI, email, templates, and security.")}</p>
      </div>

      <div className="flex gap-1 border-b border-border overflow-x-auto">
        {TABS.map(tg => (
          <button
            key={tg.key}
            data-testid={`tab-${tg.key}`}
            onClick={() => setTab(tg.key)}
            className={`px-4 py-2.5 text-sm flex items-center gap-2 border-b-2 transition-colors ${
              tab === tg.key ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            <tg.icon size={13} /> {t(tg.ar, tg.en)}
          </button>
        ))}
      </div>

      {tab === "ai" && <AISection />}
      {tab === "smtp" && <SmtpSection />}
      {tab === "templates" && <TemplatesSection />}
      {tab === "reminders" && <RemindersSection />}
      {tab === "security" && <SecuritySection user={user} forcePassword={params.get("force") === "password"} />}
    </div>
  );
}

// ============ AI ============
function AISection() {
  const { lang, t } = useLang();
  const [settings, setSettings] = useState(null);
  const [apiKey, setApiKey] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);

  const MODEL_LABELS = {
    "claude-sonnet-4-5-20250929": t("سونيت ٤٫٥ — سريع ومتوازن", "Sonnet 4.5 — fast & balanced"),
    "claude-opus-4-5-20251101": t("أوبس ٤٫٥ — أعمق تفكير", "Opus 4.5 — deepest reasoning"),
    "claude-haiku-4-5-20251001": t("هايكو ٤٫٥ — فوري", "Haiku 4.5 — instant"),
    "claude-sonnet-4-6": t("سونيت ٤٫٦ — الأحدث", "Sonnet 4.6 — newest"),
    "claude-opus-4-6": t("أوبس ٤٫٦ — الرائد", "Opus 4.6 — flagship"),
  };

  const load = () => api.get("/settings/ai").then(r => setSettings(r.data));
  useEffect(() => { load(); }, []);

  const save = async (patch) => {
    setBusy(true);
    try { const r = await api.put("/settings/ai", patch); setSettings(r.data); toast.success(t("تم الحفظ", "Saved")); }
    catch { toast.error(t("فشل", "Failed")); } finally { setBusy(false); }
  };
  const saveKey = async () => { if (!apiKey.trim()) return; await save({ api_key: apiKey.trim(), use_own_key: true }); setApiKey(""); };
  const removeKey = async () => { if (!window.confirm(t("حذف مفتاحك؟", "Remove your key?"))) return; await save({ api_key: "", use_own_key: false }); };
  const test = async () => {
    setTesting(true); setTestResult(null);
    try { const r = await api.post("/settings/ai/test"); setTestResult(r.data); if (r.data.ok) toast.success(`${t("متصل", "Connected")} — ${r.data.latency_ms}ms`); else toast.error(t("فشل الاتصال", "Connection failed")); }
    finally { setTesting(false); }
  };

  if (!settings) return <div className="p-8 label-mono">{t("جارٍ التحميل…", "Loading…")}</div>;
  const fmt = (n) => n?.toLocaleString(lang === "ar" ? "ar-EG" : "en-US") || "0";

  return (
    <div className="space-y-6">
      <div className="border border-border bg-card rounded-md">
        <div className="hairline px-5 py-3 flex items-center gap-2"><Key size={13} className="text-primary" /><div className="label-mono">{t("مفتاح Anthropic", "Anthropic key")}</div></div>
        <div className="p-5 space-y-4">
          <div className="flex items-center gap-3">
            <div className={`w-2 h-2 rounded-full ${settings.has_custom_key ? "bg-emerald-500" : "bg-muted-foreground"}`} />
            <div className="text-sm">{settings.has_custom_key ? t("مفتاحك الخاص مُفعّل", "Your custom key is active") : t("المفتاح الافتراضي للمنصة", "Platform default key")}</div>
          </div>
          {!settings.has_custom_key ? (
            <div className="flex gap-2">
              <div className="flex-1 relative">
                <input data-testid="ai-key-input" value={apiKey} onChange={e => setApiKey(e.target.value)} type={show ? "text" : "password"} placeholder="sk-ant-..." dir="ltr"
                  className="w-full px-3 py-2 ps-10 bg-background border border-border rounded-md text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary text-left" />
                <button type="button" onClick={() => setShow(!show)} className="absolute start-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">{show ? <EyeOff size={14} /> : <Eye size={14} />}</button>
              </div>
              <button data-testid="save-ai-key" onClick={saveKey} disabled={busy || !apiKey.trim()} className="px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:opacity-90 disabled:opacity-50">{t("احفظ", "Save")}</button>
            </div>
          ) : (
            <div className="flex gap-2">
              <div className="flex-1 px-3 py-2 bg-secondary border border-border rounded-md text-sm font-mono" dir="ltr">sk-ant-••••••••••••••••</div>
              <button onClick={removeKey} className="px-4 py-2 border border-border rounded-md text-sm hover:bg-secondary">{t("إزالة", "Remove")}</button>
            </div>
          )}
        </div>
      </div>

      <div className="border border-border bg-card rounded-md">
        <div className="hairline px-5 py-3 flex items-center gap-2"><Cpu size={13} className="text-primary" /><div className="label-mono">{t("النموذج", "Model")}</div></div>
        <div className="p-5 space-y-2">
          {settings.supported_models.map(m => (
            <button key={m} onClick={() => save({ model: m })} data-testid={`model-${m}`}
              className={`w-full text-start px-4 py-3 rounded-md border flex items-center justify-between ${settings.model === m ? "border-primary bg-primary/5" : "border-border hover:bg-secondary"}`}>
              <div>
                <div className="text-sm font-medium" dir="ltr">{m}</div>
                <div className="text-xs text-muted-foreground mt-0.5">{MODEL_LABELS[m]}</div>
              </div>
              {settings.model === m && <CheckCircle2 size={15} className="text-primary" />}
            </button>
          ))}
        </div>
      </div>

      <div className="border border-border bg-card rounded-md">
        <div className="hairline px-5 py-3 flex items-center gap-2"><Zap size={13} className="text-primary" /><div className="label-mono">{t("اختبار الاتصال", "Connection test")}</div></div>
        <div className="p-5 space-y-3">
          <button data-testid="test-ai-btn" onClick={test} disabled={testing} className="px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:opacity-90 disabled:opacity-50 flex items-center gap-2">
            {testing ? <Loader2 size={13} className="animate-spin" /> : <Zap size={13} />} {t("شغّل الاختبار", "Run test")}
          </button>
          {testResult && (
            <div className={`p-3 rounded-md border flex items-start gap-2 ${testResult.ok ? "border-emerald-500/40 bg-emerald-500/5" : "border-destructive/40 bg-destructive/5"}`}>
              {testResult.ok ? <CheckCircle2 size={14} className="text-emerald-500 shrink-0 mt-0.5" /> : <AlertCircle size={14} className="text-destructive shrink-0 mt-0.5" />}
              <div className="text-sm flex-1">
                <div className="font-medium">{testResult.ok ? t("متصل", "Connected") : t("فشل", "Failed")}</div>
                <div className="text-xs text-muted-foreground mt-0.5">{testResult.latency_ms}ms · {testResult.model} · {testResult.source === "user" ? t("مفتاحك", "Your key") : t("افتراضي", "Default")}</div>
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="border border-border bg-card rounded-md">
        <div className="hairline px-5 py-3 flex items-center gap-2"><div className="label-mono">{t("استهلاك التوكنز", "Token usage")}</div></div>
        <div className="p-5 grid grid-cols-3 gap-px bg-border">
          <div className="bg-card p-4"><div className="label-mono">{t("الاستدعاءات", "Calls")}</div><div className="data-number text-3xl mt-1">{fmt(settings.usage?.calls)}</div></div>
          <div className="bg-card p-4"><div className="label-mono">{t("توكنز داخلة", "Tokens in")}</div><div className="data-number text-3xl mt-1">{fmt(settings.usage?.tokens_in)}</div></div>
          <div className="bg-card p-4"><div className="label-mono">{t("توكنز خارجة", "Tokens out")}</div><div className="data-number text-3xl mt-1">{fmt(settings.usage?.tokens_out)}</div></div>
        </div>
      </div>
    </div>
  );
}

// ============ SMTP ============
function SmtpSection() {
  const { t } = useLang();
  const [s, setS] = useState(null);
  const [pwd, setPwd] = useState("");
  const [showPwd, setShowPwd] = useState(false);
  const [testTo, setTestTo] = useState("");
  const [busy, setBusy] = useState(false);
  const [testing, setTesting] = useState(false);

  const load = () => api.get("/settings/smtp").then(r => setS(r.data));
  useEffect(() => { load(); }, []);

  const save = async () => {
    setBusy(true);
    try {
      const body = { ...s };
      delete body.has_password; delete body.updated_at;
      if (pwd) body.password = pwd;
      const r = await api.put("/settings/smtp", body);
      setS(r.data); setPwd("");
      toast.success(t("تم الحفظ", "Saved"));
    } catch (err) { toast.error(err?.response?.data?.detail || t("فشل", "Failed")); }
    finally { setBusy(false); }
  };

  const sendTest = async () => {
    if (!testTo) return;
    setTesting(true);
    try {
      const r = await api.post("/settings/smtp/test", { to: testTo });
      if (r.data.ok) toast.success(t("تم الإرسال", "Test sent"));
      else toast.error(r.data.detail || t("فشل الإرسال", "Send failed"));
    } catch (err) { toast.error(err?.response?.data?.detail || t("فشل", "Failed")); }
    finally { setTesting(false); }
  };

  if (!s) return <div className="p-8 label-mono">{t("جارٍ التحميل…", "Loading…")}</div>;

  return (
    <div className="space-y-6">
      <div className="border border-border bg-card rounded-md">
        <div className="hairline px-5 py-3 flex items-center gap-2"><Server size={13} className="text-primary" /><div className="label-mono">{t("إعداد خادم SMTP", "SMTP server config")}</div></div>
        <div className="p-5 space-y-4">
          <p className="text-xs text-muted-foreground">{t("هذا يفعّل: رموز الدخول (OTP)، دعوات الفريق، تنبيهات المهام، والتذكيرات.", "Powers: sign-in OTP, team invites, task notifications, and reminders.")}</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Field label={t("الخادم (Host)", "Host")} value={s.host} onChange={v => setS({ ...s, host: v })} placeholder="smtp.gmail.com" testid="smtp-host" />
            <Field label={t("المنفذ (Port)", "Port")} value={s.port} type="number" onChange={v => setS({ ...s, port: Number(v) })} placeholder="587" testid="smtp-port" />
            <Field label={t("اسم المستخدم", "Username")} value={s.username} onChange={v => setS({ ...s, username: v })} placeholder="you@gmail.com" testid="smtp-username" />
            <div>
              <label className="label-mono mb-1 block">{t("كلمة المرور / App Password", "Password / App Password")}</label>
              <div className="relative">
                <input data-testid="smtp-password" value={pwd} onChange={e => setPwd(e.target.value)} type={showPwd ? "text" : "password"} dir="ltr"
                  placeholder={s.has_password ? "••••••••" : t("اتركه فارغًا للإبقاء", "Leave empty to keep")}
                  className="w-full px-3 py-2 pe-9 bg-background border border-border rounded-md text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary text-left" />
                <button type="button" onClick={() => setShowPwd(!showPwd)} className="absolute end-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">{showPwd ? <EyeOff size={13} /> : <Eye size={13} />}</button>
              </div>
            </div>
            <Field label={t("From Email", "From email")} value={s.from_email} onChange={v => setS({ ...s, from_email: v })} placeholder="noreply@yourapp.com" testid="smtp-from" />
            <div className="flex flex-col gap-2 justify-end">
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" data-testid="smtp-starttls" checked={!!s.start_tls} onChange={e => setS({ ...s, start_tls: e.target.checked, use_tls: e.target.checked ? false : s.use_tls })} />
                STARTTLS (587)
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" data-testid="smtp-tls" checked={!!s.use_tls} onChange={e => setS({ ...s, use_tls: e.target.checked, start_tls: e.target.checked ? false : s.start_tls })} />
                SSL/TLS (465)
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" data-testid="smtp-enabled" checked={!!s.enabled} onChange={e => setS({ ...s, enabled: e.target.checked })} />
                {t("مفعّل", "Enabled")}
              </label>
            </div>
          </div>
          <div className="flex gap-2">
            <button data-testid="smtp-save" onClick={save} disabled={busy} className="px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:opacity-90 disabled:opacity-50">{t("احفظ", "Save")}</button>
          </div>
        </div>
      </div>

      <div className="border border-border bg-card rounded-md">
        <div className="hairline px-5 py-3 flex items-center gap-2"><Mail size={13} className="text-primary" /><div className="label-mono">{t("اختبر الإرسال", "Send test email")}</div></div>
        <div className="p-5 flex gap-2">
          <input data-testid="smtp-test-to" value={testTo} onChange={e => setTestTo(e.target.value)} type="email" placeholder="me@example.com" dir="ltr"
            className="flex-1 px-3 py-2 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary text-left" />
          <button data-testid="smtp-test-send" onClick={sendTest} disabled={testing || !testTo} className="px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:opacity-90 disabled:opacity-50 flex items-center gap-2">
            {testing ? <Loader2 size={13} className="animate-spin" /> : <Zap size={13} />} {t("أرسل", "Send")}
          </button>
        </div>
      </div>

      <div className="text-xs text-muted-foreground space-y-1 px-1">
        <div>{t("Gmail: استخدم App Password (ليس كلمة سرك). فعّل التحقق بخطوتين أولاً.", "Gmail: use an App Password (not your real password). Enable 2FA first.")}</div>
        <div>{t("AWS SES / Mailgun / Postmark / Sendgrid SMTP: ادخل المعلومات كما هي من لوحة التحكم.", "AWS SES / Mailgun / Postmark / Sendgrid SMTP: paste values from their console.")}</div>
      </div>
    </div>
  );
}

function Field({ label, value, onChange, placeholder, type = "text", testid }) {
  return (
    <div>
      <label className="label-mono mb-1 block">{label}</label>
      <input data-testid={testid} value={value || ""} onChange={e => onChange(e.target.value)} type={type} placeholder={placeholder} dir="ltr"
        className="w-full px-3 py-2 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary text-left" />
    </div>
  );
}

// ============ TEMPLATES ============
function TemplatesSection() {
  const { t } = useLang();
  const [templates, setTemplates] = useState(null);
  const [active, setActive] = useState("otp");
  const [edit, setEdit] = useState({});
  const [busy, setBusy] = useState(false);

  const load = () => api.get("/settings/email-templates").then(r => { setTemplates(r.data); setEdit(r.data[active]); });
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);
  useEffect(() => { if (templates) setEdit(templates[active]); }, [active, templates]);

  const save = async () => {
    setBusy(true);
    try {
      await api.put("/settings/email-templates", { key: active, subject_ar: edit.subject_ar, subject_en: edit.subject_en, html: edit.html });
      toast.success(t("تم الحفظ", "Saved"));
      load();
    } catch { toast.error(t("فشل", "Failed")); } finally { setBusy(false); }
  };

  const reset = async () => {
    if (!window.confirm(t("إعادة القالب للإعدادات الافتراضية؟", "Reset to default template?"))) return;
    await api.post(`/settings/email-templates/${active}/reset`);
    load();
  };

  if (!templates) return <div className="p-8 label-mono">{t("جارٍ التحميل…", "Loading…")}</div>;

  const labels = {
    otp: t("رمز الدخول (OTP)", "Sign-in code (OTP)"),
    invite: t("دعوة فريق", "Team invite"),
    task_assigned: t("تعيين مهمة", "Task assignment"),
    task_reminder: t("تذكير", "Reminder"),
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[200px_1fr] gap-4">
      <div className="border border-border bg-card rounded-md p-2 space-y-0.5 h-fit">
        {Object.keys(templates).map(k => (
          <button key={k} data-testid={`tpl-${k}`} onClick={() => setActive(k)}
            className={`w-full text-start px-3 py-2 rounded-md text-sm transition-colors ${active === k ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground hover:bg-secondary/60"}`}>
            {labels[k] || k}
          </button>
        ))}
      </div>
      <div className="space-y-4">
        <div className="border border-border bg-card rounded-md p-5 space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <div className="label-mono">{t("القالب", "Template")}</div>
              <h3 className="text-lg font-medium mt-0.5">{labels[active]}</h3>
            </div>
            <button data-testid="tpl-reset" onClick={reset} className="px-3 h-9 border border-border rounded-md text-xs hover:bg-secondary flex items-center gap-1">
              <RefreshCw size={12} /> {t("إعادة افتراضي", "Reset default")}
            </button>
          </div>
          <Field label={t("العنوان (عربي)", "Subject (AR)")} value={edit.subject_ar} onChange={v => setEdit({ ...edit, subject_ar: v })} testid="tpl-subject-ar" />
          <Field label={t("العنوان (إنجليزي)", "Subject (EN)")} value={edit.subject_en} onChange={v => setEdit({ ...edit, subject_en: v })} testid="tpl-subject-en" />
          <div>
            <label className="label-mono mb-1 block">{t("HTML — استخدم المتغيرات بين أقواس مجعدة", "HTML body — use {placeholders}")}</label>
            <textarea data-testid="tpl-html" value={edit.html || ""} onChange={e => setEdit({ ...edit, html: e.target.value })} rows={14}
              className="w-full px-3 py-2 bg-background border border-border rounded-md text-xs font-mono focus:outline-none focus:ring-2 focus:ring-primary" dir="ltr" />
            <div className="label-mono text-[10px] mt-2 text-muted-foreground">
              {t("المتغيرات المتاحة:", "Available variables:")} {"{app_name} {name} {email} {otp} {actor} {title} {description} {due_date} {url} {temp_password} {invite_url}"}
            </div>
          </div>
          <button data-testid="tpl-save" onClick={save} disabled={busy} className="px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:opacity-90 disabled:opacity-50">{t("احفظ القالب", "Save template")}</button>
        </div>
        <div className="border border-border bg-card rounded-md p-5">
          <div className="label-mono mb-2">{t("معاينة", "Preview")}</div>
          <div className="border border-border rounded-md overflow-hidden">
            <iframe data-testid="tpl-preview" title="preview" srcDoc={edit.html || ""} className="w-full h-[420px] bg-white" sandbox="" />
          </div>
        </div>
      </div>
    </div>
  );
}

// ============ REMINDERS SECTION ============
function RemindersSection() {
  const { t } = useLang();
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = () => api.get("/settings/reminders").then(r => setData(r.data));
  useEffect(() => { load(); }, []);

  const saveWorkspace = async (patch) => {
    setBusy(true);
    try {
      const r = await api.put("/settings/reminders/workspace", patch);
      setData(d => ({ ...d, workspace: r.data }));
      toast.success(t("تم الحفظ", "Saved"));
    } catch (err) {
      toast.error(err?.response?.data?.detail || t("فشل", "Failed"));
    } finally { setBusy(false); }
  };

  const savePersonal = async (patch) => {
    setBusy(true);
    try {
      const r = await api.put("/settings/reminders/personal", patch);
      setData(r.data);
      toast.success(t("تم الحفظ", "Saved"));
    } catch (err) {
      toast.error(err?.response?.data?.detail || t("فشل", "Failed"));
    } finally { setBusy(false); }
  };

  if (!data) return <div className="p-8 label-mono">{t("جارٍ التحميل…", "Loading…")}</div>;

  const ws = data.workspace;
  const me = data.personal;

  // Editable presets handler
  const togglePreset = (val) => {
    const set = new Set(ws.default_offsets_minutes || []);
    if (set.has(val)) set.delete(val); else set.add(val);
    saveWorkspace({ default_offsets_minutes: [...set].sort((a, b) => a - b) });
  };
  const PRESETS = [
    { v: 0, l: t("الآن", "Now") },
    { v: 15, l: t("١٥د", "15m") },
    { v: 30, l: t("٣٠د", "30m") },
    { v: 60, l: t("ساعة", "1h") },
    { v: 240, l: t("٤ ساعات", "4h") },
    { v: 1440, l: t("يوم", "1d") },
    { v: 4320, l: t("٣ أيام", "3d") },
    { v: 10080, l: t("أسبوع", "1w") },
  ];

  return (
    <div className="space-y-6">
      {/* Workspace digest */}
      <div className="border border-border bg-card rounded-md">
        <div className="hairline px-5 py-3 flex items-center gap-2">
          <Shield size={13} className="text-primary" />
          <div className="label-mono">{t("إعدادات المكان (المشرف)", "Workspace settings (admin)")}</div>
          {!data.is_admin && <span className="ms-auto label-mono text-[9px] text-muted-foreground">{t("للقراءة فقط", "Read-only")}</span>}
        </div>
        <div className="p-5 space-y-5">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1">
              <div className="text-sm font-medium">{t("ملخص يومي للمتأخرات", "Daily overdue digest")}</div>
              <p className="text-xs text-muted-foreground mt-1">{t("يُرسل لكل عضو بريد يومي بمهامه المتأخرة والمستحقة قريبًا.", "Emails every member a daily summary of their overdue and soon-due tasks.")}</p>
            </div>
            <label className="inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                data-testid="digest-enabled"
                disabled={!data.is_admin || busy}
                checked={!!ws.overdue_digest_enabled}
                onChange={e => saveWorkspace({ overdue_digest_enabled: e.target.checked })}
                className="sr-only peer"
              />
              <span className="w-10 h-5 bg-secondary peer-checked:bg-primary rounded-full relative transition-colors after:absolute after:top-0.5 after:start-0.5 after:bg-background after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:after:translate-x-5 rtl:peer-checked:after:-translate-x-5" />
            </label>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label-mono mb-1.5 block flex items-center gap-1"><Clock size={11} /> {t("وقت الإرسال اليومي (UTC)", "Daily send time (UTC)")}</label>
              <input
                type="time" disabled={!data.is_admin || busy}
                data-testid="digest-time"
                value={ws.overdue_digest_time || "09:00"}
                onChange={e => saveWorkspace({ overdue_digest_time: e.target.value })}
                className="w-full px-3 py-2 bg-background border border-border rounded-md text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
            <div>
              <label className="label-mono mb-1.5 block">{t("نطاق التنبيه المسبق (ساعات)", "Lookahead window (hours)")}</label>
              <input
                type="number" min={1} max={168} disabled={!data.is_admin || busy}
                data-testid="digest-lookahead"
                value={ws.digest_lookahead_hours || 24}
                onChange={e => saveWorkspace({ digest_lookahead_hours: Number(e.target.value) })}
                className="w-full px-3 py-2 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
          </div>

          <div>
            <div className="label-mono mb-2">{t("إعدادات التذكير السريعة الافتراضية", "Default quick reminder offsets")}</div>
            <p className="text-xs text-muted-foreground mb-2">{t("الأزرار التي تظهر في كل مهمة عند إضافة تذكير.", "The buttons shown on each task when adding a reminder.")}</p>
            <div className="flex flex-wrap gap-1.5">
              {PRESETS.map(p => {
                const active = (ws.default_offsets_minutes || []).includes(p.v);
                return (
                  <button
                    key={p.v}
                    type="button"
                    disabled={!data.is_admin || busy}
                    data-testid={`preset-${p.v}`}
                    onClick={() => togglePreset(p.v)}
                    className={`px-3 py-1.5 text-xs rounded-md border transition-colors disabled:opacity-50 ${active ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground hover:text-foreground"}`}
                  >
                    {p.l}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* Personal preferences */}
      <div className="border border-border bg-card rounded-md">
        <div className="hairline px-5 py-3 flex items-center gap-2">
          <Bell size={13} className="text-primary" />
          <div className="label-mono">{t("تفضيلاتك الشخصية", "Your preferences")}</div>
        </div>
        <div className="p-5 space-y-5">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1">
              <div className="text-sm font-medium">{t("استثناء من الملخص اليومي", "Opt out of daily digest")}</div>
              <p className="text-xs text-muted-foreground mt-1">{t("لن تستلم بريد الملخص اليومي. التذكيرات المباشرة على المهام ستبقى تعمل.", "You won't receive the daily digest email. Direct per-task reminders still work.")}</p>
            </div>
            <label className="inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                data-testid="optout"
                disabled={busy}
                checked={!!me.digest_opted_out}
                onChange={e => savePersonal({ digest_opted_out: e.target.checked })}
                className="sr-only peer"
              />
              <span className="w-10 h-5 bg-secondary peer-checked:bg-primary rounded-full relative transition-colors after:absolute after:top-0.5 after:start-0.5 after:bg-background after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:after:translate-x-5 rtl:peer-checked:after:-translate-x-5" />
            </label>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label-mono mb-1.5 block">{t("بداية ساعات الهدوء", "Quiet hours start")}</label>
              <input
                type="time" disabled={busy}
                data-testid="quiet-start"
                value={me.quiet_hours_start || ""}
                onChange={e => savePersonal({ quiet_hours_start: e.target.value || null })}
                className="w-full px-3 py-2 bg-background border border-border rounded-md text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
            <div>
              <label className="label-mono mb-1.5 block">{t("نهاية ساعات الهدوء", "Quiet hours end")}</label>
              <input
                type="time" disabled={busy}
                data-testid="quiet-end"
                value={me.quiet_hours_end || ""}
                onChange={e => savePersonal({ quiet_hours_end: e.target.value || null })}
                className="w-full px-3 py-2 bg-background border border-border rounded-md text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
          </div>
          <p className="text-[10px] text-muted-foreground">{t("ملاحظة: ساعات الهدوء توثّقت كتفضيل — التطبيق العملي قادم.", "Note: quiet hours are recorded as preference — runtime enforcement coming next.")}</p>
        </div>
      </div>
    </div>
  );
}

// ============ SECURITY ============
function SecuritySection({ user, forcePassword }) {
  const { t } = useLang();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (next !== confirm) { toast.error(t("كلمتا المرور غير متطابقتين", "Passwords don't match")); return; }
    setBusy(true);
    try {
      await api.post("/auth/change-password", { current_password: current, new_password: next });
      toast.success(t("تم تغيير كلمة المرور", "Password updated"));
      setCurrent(""); setNext(""); setConfirm("");
    } catch (err) { toast.error(err?.response?.data?.detail || t("فشل", "Failed")); }
    finally { setBusy(false); }
  };

  return (
    <div className="space-y-6">
      {forcePassword && (
        <div className="border border-amber-500/40 bg-amber-500/5 rounded-md p-4 text-sm">
          {t("يجب تغيير كلمة المرور المؤقتة قبل المتابعة.", "You must change your temporary password before continuing.")}
        </div>
      )}
      <div className="border border-border bg-card rounded-md">
        <div className="hairline px-5 py-3 flex items-center gap-2"><Lock size={13} className="text-primary" /><div className="label-mono">{t("تغيير كلمة المرور", "Change password")}</div></div>
        <form onSubmit={submit} className="p-5 space-y-3 max-w-md" data-testid="change-password-form">
          <Field label={t("كلمة المرور الحالية", "Current password")} value={current} onChange={setCurrent} type="password" testid="pw-current" />
          <Field label={t("كلمة المرور الجديدة (٨ أحرف على الأقل)", "New password (min 8)")} value={next} onChange={setNext} type="password" testid="pw-new" />
          <Field label={t("تأكيد كلمة المرور الجديدة", "Confirm new password")} value={confirm} onChange={setConfirm} type="password" testid="pw-confirm" />
          <button data-testid="pw-submit" type="submit" disabled={busy || !current || !next || next.length < 8} className="px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:opacity-90 disabled:opacity-50">{t("تحديث", "Update")}</button>
        </form>
      </div>
      <div className="border border-border bg-card rounded-md p-5 space-y-2">
        <div className="label-mono">{t("جلسة الدخول", "Session")}</div>
        <p className="text-sm text-muted-foreground">{t("الجلسة تنتهي تلقائيًا بعد ٦ ساعات. الدخول يتطلب رمز OTP يُرسل عبر البريد (عند تفعيل SMTP).", "Sessions auto-expire after 6 hours. Sign-in requires an OTP code sent via email (when SMTP is enabled).")}</p>
        <p className="text-sm text-muted-foreground" dir="ltr">{user?.email}</p>
      </div>
    </div>
  );
}
