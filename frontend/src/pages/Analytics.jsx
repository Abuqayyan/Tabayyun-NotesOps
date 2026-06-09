import { useEffect, useState, Fragment } from "react";
import { api } from "@/lib/api";
import { useLang } from "@/contexts/LanguageContext";
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
  BarChart, Bar, CartesianGrid
} from "recharts";
import { Clock, Zap, Activity, TrendingUp, AlertTriangle } from "lucide-react";

export default function Analytics() {
  const { t } = useLang();
  const [data, setData] = useState(null);
  const [intel, setIntel] = useState(null);
  useEffect(() => {
    api.get("/analytics/overview").then(r => setData(r.data));
    api.get("/analytics/intelligence").then(r => setIntel(r.data));
  }, []);

  if (!data) return <div className="p-8 label-mono">{t("جارٍ التحميل…", "Loading…")}</div>;

  const PRIORITY_LABEL = { low: t("منخفض", "Low"), medium: t("متوسط", "Medium"), high: t("عالٍ", "High"), critical: t("حرج", "Critical") };
  const TENDS_LABEL = { underestimate: t("تقدّر أقل من اللازم", "Tends to underestimate"), overestimate: t("تقدّر أكثر من اللازم", "Tends to overestimate"), unknown: "—" };
  const DAYS = t("إثن,ثل,أرب,خم,جم,سب,أح", "Mon,Tue,Wed,Thu,Fri,Sat,Sun").split(",");

  const maxHeat = Math.max(1, ...data.heatmap.flat());

  return (
    <div className="p-6 lg:p-8 space-y-6" data-testid="analytics-page">
      <div>
        <div className="label-mono">{t("ذكاء", "Intelligence")}</div>
        <h1 className="text-3xl sm:text-4xl tracking-tight font-medium mt-1">{t("التحليلات", "Analytics")}</h1>
        <p className="text-sm text-muted-foreground mt-1">{t("آخر ١٤ يومًا من التركيز والتنفيذ وتحليل الأنماط.", "Last 14 days of focus, execution, and pattern analysis.")}</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="border border-border bg-card rounded-md p-5">
          <div className="label-mono mb-4">{t("دقائق التركيز / اليوم", "Focus minutes / day")}</div>
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={data.daily}>
              <defs>
                <linearGradient id="g1" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="hsl(var(--primary))" stopOpacity={0.5} />
                  <stop offset="100%" stopColor="hsl(var(--primary))" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis dataKey="label" stroke="hsl(var(--muted-foreground))" fontSize={10} />
              <YAxis stroke="hsl(var(--muted-foreground))" fontSize={10} />
              <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 6, fontSize: 12 }} />
              <Area type="monotone" dataKey="focus_minutes" stroke="hsl(var(--primary))" fill="url(#g1)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div className="border border-border bg-card rounded-md p-5">
          <div className="label-mono mb-4">{t("المهام المكتملة / اليوم", "Tasks completed / day")}</div>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={data.daily}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis dataKey="label" stroke="hsl(var(--muted-foreground))" fontSize={10} />
              <YAxis stroke="hsl(var(--muted-foreground))" fontSize={10} />
              <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 6, fontSize: 12 }} />
              <Bar dataKey="completed" fill="hsl(var(--primary))" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 border border-border bg-card rounded-md p-5">
          <div className="label-mono mb-4">{t("خريطة الحرارة · يوم × ساعة", "Heatmap · day × hour")}</div>
          <div className="overflow-x-auto">
            <div className="inline-grid gap-0.5" style={{ gridTemplateColumns: "auto repeat(24, 1fr)", direction: "ltr" }}>
              <div></div>
              {Array.from({ length: 24 }).map((_, h) => (
                <div key={h} className="label-mono text-[8px] text-center">{h}</div>
              ))}
              {DAYS.map((d, di) => (
                <Fragment key={d}>
                  <div className="label-mono text-[9px] pe-2 self-center">{d}</div>
                  {Array.from({ length: 24 }).map((_, h) => {
                    const v = data.heatmap[di][h];
                    const opacity = v / maxHeat;
                    return (
                      <div key={h} className="w-5 h-5 rounded-sm" title={`${d} ${h}:00 — ${v}m`}
                        style={{ backgroundColor: opacity > 0 ? `hsl(16 100% 50% / ${0.15 + opacity * 0.85})` : "hsl(var(--secondary))" }} />
                    );
                  })}
                </Fragment>
              ))}
            </div>
          </div>
        </div>

        <div className="border border-border bg-card rounded-md p-5">
          <div className="label-mono mb-3">{t("توزيع الأولويات", "Priority distribution")}</div>
          <div className="space-y-3">
            {Object.entries(data.priority_distribution).map(([k, v]) => {
              const total = Object.values(data.priority_distribution).reduce((a, b) => a + b, 0) || 1;
              return (
                <div key={k}>
                  <div className="flex justify-between text-xs mb-1"><span>{PRIORITY_LABEL[k] || k}</span><span className="font-mono">{v}</span></div>
                  <div className="h-1.5 bg-secondary rounded-full overflow-hidden">
                    <div className="h-full bg-primary" style={{ width: `${(v / total) * 100}%` }} />
                  </div>
                </div>
              );
            })}
          </div>
          <div className="mt-6 pt-4 border-t border-border">
            <div className="label-mono">{t("دقة التقدير", "Estimate accuracy")}</div>
            <div className="data-number text-3xl mt-1">{data.estimate_accuracy}%</div>
            <div className="text-xs text-muted-foreground mt-1">{t("المتوسط بين المقدّر والفعلي", "Avg between estimated and actual")}</div>
          </div>
        </div>
      </div>

      {intel && (
        <div className="space-y-4">
          <div className="flex items-end justify-between">
            <div>
              <div className="label-mono">{t("الدماغ التشغيلي", "Operational brain")}</div>
              <h2 className="text-xl sm:text-2xl tracking-tight font-medium mt-1">{t("ذكاء الإنتاجية", "Productivity intelligence")}</h2>
            </div>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="p-5 border border-border bg-card rounded-md">
              <div className="label-mono flex items-center gap-1.5"><Clock size={11} /> {t("أفضل ساعاتك", "Your best hours")}</div>
              <div className="mt-3 space-y-1">
                {intel.best_hours.length ? intel.best_hours.map(h => (
                  <div key={h.hour} className="flex items-center justify-between text-sm">
                    <span className="font-mono">{String(h.hour).padStart(2, "0")}:00</span>
                    <span className="label-mono text-[10px]">{h.minutes} {t("د", "min")}</span>
                  </div>
                )) : <div className="text-xs text-muted-foreground">{t("لا توجد بيانات", "No data")}</div>}
              </div>
            </div>

            <div className="p-5 border border-border bg-card rounded-md">
              <div className="label-mono flex items-center gap-1.5"><Activity size={11} /> {t("الانتظام", "Consistency")}</div>
              <div className="data-number text-3xl mt-3">{intel.consistency_pct}%</div>
              <div className="text-xs text-muted-foreground mt-1">{intel.active_days_14}/14 {t("أيام نشطة", "active days")}</div>
            </div>

            <div className="p-5 border border-border bg-card rounded-md">
              <div className="label-mono flex items-center gap-1.5"><Zap size={11} className="text-primary" /> {t("سلسلة التركيز", "Focus streak")}</div>
              <div className="data-number text-3xl mt-3">{intel.focus_streak_days}<span className="text-lg text-muted-foreground"> {t("ي", "d")}</span></div>
              <div className="text-xs text-muted-foreground mt-1">{intel.total_focus_sessions} {t("جلسة", "sessions")}</div>
            </div>

            <div className="p-5 border border-border bg-card rounded-md">
              <div className="label-mono flex items-center gap-1.5"><TrendingUp size={11} /> {t("تميل إلى", "You tend to")}</div>
              <div className="data-number text-lg mt-3">{TENDS_LABEL[intel.tends_to]}</div>
              <div className="text-xs text-muted-foreground mt-1">{t("في تقدير الوقت", "in time estimation")}</div>
            </div>
          </div>

          {intel.procrastinated.length > 0 && (
            <div className="border border-amber-500/30 bg-card rounded-md">
              <div className="hairline px-5 py-3 flex items-center gap-2"><AlertTriangle size={13} className="text-amber-500" /><div className="label-mono">{t("مهام مؤجَّلة", "Procrastinated tasks")}</div></div>
              <div className="divide-y divide-border">
                {intel.procrastinated.map(tk => (
                  <div key={tk.id} className="px-5 py-3 flex items-center justify-between">
                    <span className="text-sm">{tk.title}</span>
                    <span className="label-mono text-[10px] text-amber-500">{t("متأخرة", "overdue")} {tk.days_overdue} {t("ي", "d")}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
