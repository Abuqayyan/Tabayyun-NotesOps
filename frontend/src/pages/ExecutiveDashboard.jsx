import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useLang } from "@/contexts/LanguageContext";
import { PageHeader, Section, Stat, Empty, Loading, Forbidden, Badge } from "@/components/kit";
import {
  HeartPulse, AlertTriangle, Stamp, CalendarClock,
  Briefcase, Lightbulb, ArrowUp, ArrowDown, Minus, ShieldAlert
} from "lucide-react";

const RISK_TONE = { low: "muted", medium: "amber", high: "red", critical: "red" };
const GRADE_TONE = { excellent: "green", good: "blue", fair: "amber", poor: "red" };
// Full literal classes (Tailwind JIT can't see interpolated names).
const GRADE_COLOR = { excellent: "text-emerald-500", good: "text-blue-500", fair: "text-amber-500", poor: "text-red-500" };
const LEVEL_COLOR = { critical: "text-red-500", high: "text-red-500", medium: "text-amber-500", low: "text-muted-foreground" };

function Trend({ d }) {
  if (!d) return null;
  const Icon = d.direction === "up" ? ArrowUp : d.direction === "down" ? ArrowDown : Minus;
  const color = d.direction === "up" ? "text-emerald-500" : d.direction === "down" ? "text-red-500" : "text-muted-foreground";
  return <span className={`inline-flex items-center gap-0.5 font-mono text-xs ${color}`}><Icon size={11} />{d.change > 0 ? `+${d.change}` : d.change}</span>;
}

export default function ExecutiveDashboard() {
  const { t, lang } = useLang();
  const [intel, setIntel] = useState(null);
  const [crm, setCrm] = useState(null);
  const [exec, setExec] = useState(null);
  const [loading, setLoading] = useState(true);
  const [forbidden, setForbidden] = useState(false);
  const locale = lang === "ar" ? "ar-EG" : "en-US";
  const money = (n) => new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(n || 0);

  useEffect(() => {
    let ok = false;
    Promise.allSettled([
      api.get("/intelligence/dashboard").then((r) => { setIntel(r.data); ok = true; }),
      api.get("/crm/dashboards/executive").then((r) => { setCrm(r.data); ok = true; }),
      api.get("/executive/dashboard").then((r) => { setExec(r.data); ok = true; }),
    ]).then(() => { setForbidden(!ok); setLoading(false); });
  }, []);

  if (loading) return <Loading label={t("جارٍ تجميع ذكاء الشركة…", "Assembling company intelligence…")} />;
  if (forbidden) return <Forbidden label={t("لا تملك صلاحية لوحة التنفيذيين.", "You don't have access to the executive dashboard.")} />;

  const health = intel?.company_health;
  const deptHealth = intel?.department_health || [];
  const risks = intel?.operational_risks || [];
  const recs = intel?.recommendations || [];
  const wk = intel?.weekly_comparison;

  return (
    <div className="p-6 lg:p-8 space-y-6" data-testid="executive-dashboard-page">
      <PageHeader label={t("القيادة", "Leadership")} title={t("لوحة التنفيذيين", "Executive Dashboard")}
        subtitle={t("صحة الشركة والمخاطر والتوصيات في صفحة واحدة.", "Company health, risks, and recommendations at a glance.")} />

      {/* Top KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Stat tid="exec-health" label={t("صحة الشركة", "Company health")} icon={HeartPulse}
          value={intel ? `${intel.company_health_score}` : "—"} sub={health ? t(`الدرجة: ${health.grade}`, `Grade: ${health.grade}`) : ""}
          color={health ? GRADE_COLOR[health.grade] : ""} />
        <Stat tid="exec-pipeline" label={t("خط الأنابيب", "Pipeline")} icon={Briefcase}
          value={crm ? money(crm.total_pipeline) : "—"} sub={crm ? t(`متوقع: ${money(crm.weighted_forecast)}`, `Weighted: ${money(crm.weighted_forecast)}`) : ""} />
        <Stat tid="exec-approvals" label={t("موافقات معلّقة", "Pending approvals")} icon={Stamp}
          value={intel?.pending_approvals?.count ?? "—"} />
        <Stat tid="exec-escalations" label={t("تصعيدات", "Escalations")} icon={ShieldAlert}
          value={intel?.escalations?.total ?? 0} color={intel?.escalations?.total ? "text-red-500" : ""} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Department health */}
        <Section className="lg:col-span-2" title={t("صحة الأقسام", "Department health")}>
          <div className="divide-y divide-border">
            {deptHealth.length === 0 && <Empty>{t("لا توجد أقسام.", "No departments yet.")}</Empty>}
            {deptHealth.map((d) => (
              <div key={d.id} className="px-5 py-3 flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-sm font-medium truncate">{d.name}</div>
                  <div className="text-xs text-muted-foreground">{d.open} {t("مفتوحة", "open")} · {d.delayed} {t("متأخرة", "delayed")} · {d.participation_rate}% {t("مشاركة", "participation")}</div>
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  <Badge tone={GRADE_TONE[d.health?.grade] || "muted"}>{d.health?.score}</Badge>
                </div>
              </div>
            ))}
          </div>
        </Section>

        {/* Risk indicators */}
        <Section title={t("مؤشرات المخاطر", "Risk indicators")}>
          <div className="p-5 space-y-3">
            <div className="grid grid-cols-4 gap-2 text-center">
              {["critical", "high", "medium", "low"].map((lvl) => (
                <div key={lvl} className="p-2 border border-border rounded-md">
                  <div className={`data-number text-xl ${LEVEL_COLOR[lvl]}`}>{intel?.risk_indicators?.[lvl] || 0}</div>
                  <div className="label-mono text-[9px]">{lvl}</div>
                </div>
              ))}
            </div>
            {wk && (
              <div className="pt-2 space-y-1.5 text-xs">
                <div className="label-mono">{t("الاتجاه الأسبوعي", "Weekly trend")}</div>
                <div className="flex items-center justify-between"><span className="text-muted-foreground">{t("مكتملة", "Completed")}</span><Trend d={wk.completed} /></div>
                <div className="flex items-center justify-between"><span className="text-muted-foreground">{t("متأخرة", "Delayed")}</span><Trend d={wk.delayed} /></div>
                <div className="flex items-center justify-between"><span className="text-muted-foreground">{t("اجتماعات", "Meetings")}</span><Trend d={wk.meetings} /></div>
              </div>
            )}
          </div>
        </Section>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Critical risks */}
        <Section title={t("المخاطر التشغيلية", "Operational risks")}>
          <div className="divide-y divide-border max-h-72 overflow-y-auto">
            {risks.length === 0 && <Empty>{t("لا مخاطر مرصودة.", "No risks detected.")}</Empty>}
            {risks.slice(0, 8).map((r, i) => (
              <div key={i} className="px-5 py-3 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 min-w-0">
                  <AlertTriangle size={13} className={r.level === "critical" || r.level === "high" ? "text-red-500" : "text-amber-500"} />
                  <span className="text-sm truncate">{r.title}</span>
                </div>
                <Badge tone={RISK_TONE[r.level]}>{r.level}</Badge>
              </div>
            ))}
          </div>
        </Section>

        {/* Recommendations */}
        <Section title={t("التوصيات التنفيذية", "Executive recommendations")}>
          <div className="divide-y divide-border max-h-72 overflow-y-auto">
            {recs.length === 0 && <Empty>{t("لا توصيات حالية.", "No recommendations right now.")}</Empty>}
            {recs.slice(0, 8).map((r, i) => (
              <div key={i} className="px-5 py-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium flex items-center gap-2"><Lightbulb size={13} className="text-primary" />{r.title}</span>
                  <Badge tone={RISK_TONE[r.priority]}>{r.priority}</Badge>
                </div>
                <div className="text-xs text-muted-foreground mt-1">{r.message}</div>
              </div>
            ))}
          </div>
        </Section>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* CRM pipeline */}
        <Section title={t("خط أنابيب المبيعات", "CRM pipeline")}
          actions={crm && <span className="font-mono text-xs text-muted-foreground">{t("فوز", "Won")}: {money(crm.won_revenue)}</span>}>
          <div className="p-5">
            {!crm && <Empty>{t("لا بيانات CRM.", "No CRM data.")}</Empty>}
            {crm && Object.entries(crm.pipeline_by_stage || {}).map(([stage, v]) => (
              <div key={stage} className="flex items-center justify-between py-1.5 border-b border-border last:border-0">
                <span className="text-sm capitalize">{stage}</span>
                <span className="font-mono text-xs text-muted-foreground">{v.count} · {money(v.value)}</span>
              </div>
            ))}
          </div>
        </Section>

        {/* Upcoming meetings + pending approvals */}
        <Section title={t("اجتماعات قادمة", "Upcoming meetings")} actions={<CalendarClock size={14} className="text-muted-foreground" />}>
          <div className="divide-y divide-border max-h-72 overflow-y-auto">
            {(exec?.upcoming_meetings || []).length === 0 && <Empty>{t("لا اجتماعات قادمة.", "No upcoming meetings.")}</Empty>}
            {(exec?.upcoming_meetings || []).slice(0, 8).map((m) => (
              <div key={m.id} className="px-5 py-3 flex items-center justify-between gap-3">
                <span className="text-sm truncate">{m.title}</span>
                <span className="font-mono text-xs text-muted-foreground shrink-0">{m.meeting_at ? new Date(m.meeting_at).toLocaleDateString(locale) : "—"}</span>
              </div>
            ))}
          </div>
        </Section>
      </div>
    </div>
  );
}
