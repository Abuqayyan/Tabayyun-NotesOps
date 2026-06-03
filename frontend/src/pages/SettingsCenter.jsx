import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useLang } from "@/contexts/LanguageContext";
import { usePermissions } from "@/lib/usePermissions";
import { PageHeader, Section, Loading, Field, Input, Select, PrimaryButton } from "@/components/kit";
import { Building2, BellRing, ShieldCheck, Briefcase, Save } from "lucide-react";
import { toast } from "sonner";

const SECTIONS = [
  { id: "company", label: ["الشركة", "Company"], icon: Building2,
    fields: [["name", "اسم الشركة", "Company name"], ["logo_url", "رابط الشعار", "Logo URL"], ["primary_color", "اللون الأساسي", "Primary color"], ["locale", "اللغة", "Locale"], ["timezone", "المنطقة الزمنية", "Timezone"]] },
  { id: "notifications", label: ["الإشعارات", "Notifications"], icon: BellRing,
    fields: [["email_enabled", "البريد", "Email enabled"], ["in_app_enabled", "داخل التطبيق", "In-app enabled"], ["digest_frequency", "تكرار الملخص", "Digest frequency"]] },
  { id: "security", label: ["الأمان", "Security"], icon: ShieldCheck,
    fields: [["session_hours", "ساعات الجلسة", "Session hours"], ["jwt_expire_days", "أيام انتهاء الرمز", "JWT expire days"], ["password_min_length", "أدنى طول لكلمة المرور", "Password min length"], ["otp_ttl_minutes", "مدة الرمز المؤقت", "OTP TTL minutes"]] },
  { id: "crm", label: ["CRM", "CRM"], icon: Briefcase,
    fields: [["default_lead_stage", "مرحلة العميل الافتراضية", "Default lead stage"], ["default_opportunity_stage", "مرحلة الفرصة الافتراضية", "Default opportunity stage"], ["currency", "العملة", "Currency"]] },
];

export default function SettingsCenter() {
  const { t } = useLang();
  const { has } = usePermissions();
  const [active, setActive] = useState("company");
  const [data, setData] = useState(null);
  const [draft, setDraft] = useState({});
  const canManage = has("settings.manage");

  useEffect(() => { api.get("/settings/center").then((r) => { setData(r.data); }).catch(() => setData({})); }, []);
  useEffect(() => { if (data) setDraft({ ...(data[active] || {}) }); }, [data, active]);

  const save = async () => {
    try {
      const r = await api.put(`/settings/center/${active}`, { values: draft });
      setData({ ...data, [active]: r.data });
      toast.success(t("تم الحفظ", "Saved"));
    } catch (e) { toast.error(e?.response?.data?.detail || t("فشل الحفظ", "Save failed")); }
  };

  if (!data) return <Loading label={t("تحميل الإعدادات…", "Loading settings…")} />;
  const section = SECTIONS.find((s) => s.id === active);

  return (
    <div className="p-6 lg:p-8 space-y-6" data-testid="settings-center-page">
      <PageHeader label={t("الإدارة", "Administration")} title={t("مركز التهيئة", "Configuration Center")}
        subtitle={t("إعدادات الشركة والإشعارات والأمان وCRM.", "Company, notification, security, and CRM settings.")} />

      <div className="flex flex-col lg:flex-row gap-4">
        <div className="lg:w-56 shrink-0 space-y-1">
          {SECTIONS.map((s) => (
            <button key={s.id} onClick={() => setActive(s.id)} data-testid={`settings-tab-${s.id}`}
              className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-md text-sm ${active === s.id ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground hover:bg-secondary/60"}`}>
              <s.icon size={14} /> {t(s.label[0], s.label[1])}
            </button>
          ))}
        </div>

        <Section className="flex-1" title={t(section.label[0], section.label[1])}
          actions={canManage && <PrimaryButton onClick={save} data-testid="settings-save"><Save size={14} /> {t("حفظ", "Save")}</PrimaryButton>}>
          <div className="p-5 space-y-4 max-w-xl">
            {!canManage && <div className="text-xs text-amber-500">{t("للعرض فقط — تحتاج صلاحية settings.manage للتعديل.", "Read-only — settings.manage is required to edit.")}</div>}
            {section.fields.map(([key, ar, en]) => {
              const val = draft[key];
              const isBool = typeof (data[active] || {})[key] === "boolean";
              return (
                <Field key={key} label={t(ar, en)}>
                  {isBool ? (
                    <Select value={String(val)} disabled={!canManage} onChange={(e) => setDraft({ ...draft, [key]: e.target.value === "true" })}>
                      <option value="true">{t("مفعّل", "Enabled")}</option>
                      <option value="false">{t("معطّل", "Disabled")}</option>
                    </Select>
                  ) : (
                    <Input value={val ?? ""} disabled={!canManage}
                      onChange={(e) => setDraft({ ...draft, [key]: typeof (data[active] || {})[key] === "number" ? Number(e.target.value) : e.target.value })}
                      data-testid={`settings-${key}`} />
                  )}
                </Field>
              );
            })}
          </div>
        </Section>
      </div>
    </div>
  );
}
