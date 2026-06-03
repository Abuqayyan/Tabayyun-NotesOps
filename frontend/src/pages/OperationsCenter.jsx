import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { useLang } from "@/contexts/LanguageContext";
import { PageHeader, Section, Stat, Empty, Loading, Forbidden, Badge } from "@/components/kit";
import { Activity, Database, Clock, Bell, ShieldAlert, Gauge, AlertOctagon, RefreshCw } from "lucide-react";

export default function OperationsCenter() {
  const { t, lang } = useLang();
  const [ov, setOv] = useState(undefined);
  const [errors, setErrors] = useState([]);
  const locale = lang === "ar" ? "ar-EG" : "en-US";

  const load = useCallback(() => {
    api.get("/ops/overview").then((r) => setOv(r.data)).catch((e) => setOv(e?.response?.status === 403 ? null : {}));
    api.get("/ops/errors", { params: { limit: 20 } }).then((r) => setErrors(r.data.errors || [])).catch(() => {});
  }, []);
  useEffect(() => { load(); const id = setInterval(load, 30000); return () => clearInterval(id); }, [load]);

  if (ov === undefined) return <Loading label={t("فحص النظام…", "Checking system…")} />;
  if (ov === null) return <Forbidden label={t("مركز العمليات للمسؤولين فقط.", "Operations Center is admin-only.")} />;

  const sched = ov.scheduler || {};
  const rem = ov.reminders || {};
  const esc = ov.escalations || {};
  const metrics = ov.metrics || {};

  return (
    <div className="p-6 lg:p-8 space-y-6" data-testid="operations-center-page">
      <PageHeader label={t("الإدارة", "Administration")} title={t("مركز العمليات", "Operations Center")}
        subtitle={t("صحة النظام والمهام الخلفية والمقاييس.", "System health, background jobs, and metrics.")}
        actions={<button onClick={load} className="px-3 py-2 border border-border rounded-md text-sm hover:bg-secondary flex items-center gap-2"><RefreshCw size={13} /> {t("تحديث", "Refresh")}</button>} />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Stat label={t("مونغو", "MongoDB")} value={ov.health?.mongo ? t("متصل", "Up") : t("معطل", "Down")} icon={Database} color={ov.health?.mongo ? "text-emerald-500" : "text-red-500"} />
        <Stat label={t("بوستجرس", "PostgreSQL")} value={ov.health?.postgres?.ok ? t("متصل", "Up") : t("معطل", "Down")} icon={Database} color={ov.health?.postgres?.ok ? "text-emerald-500" : "text-red-500"} />
        <Stat label={t("المجدول", "Scheduler")} value={sched.alive ? t("يعمل", "Alive") : t("متوقف", "Stopped")} icon={Clock} color={sched.alive ? "text-emerald-500" : "text-amber-500"} sub={sched.last_run_at ? new Date(sched.last_run_at).toLocaleTimeString(locale) : "—"} />
        <Stat label={t("المستخدمون", "Users")} value={ov.users ?? "—"} icon={Activity} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Section title={t("التذكيرات", "Reminders")} actions={<Bell size={14} className="text-muted-foreground" />}>
          <div className="p-5 grid grid-cols-3 gap-3 text-center">
            <div><div className="data-number text-2xl">{rem.pending ?? 0}</div><div className="label-mono text-[9px]">{t("معلّق", "Pending")}</div></div>
            <div><div className="data-number text-2xl">{rem.sent ?? 0}</div><div className="label-mono text-[9px]">{t("مرسل", "Sent")}</div></div>
            <div><div className="data-number text-2xl text-red-500">{rem.failed ?? 0}</div><div className="label-mono text-[9px]">{t("فاشل", "Failed")}</div></div>
          </div>
        </Section>
        <Section title={t("التصعيدات", "Escalations")} actions={<ShieldAlert size={14} className="text-muted-foreground" />}>
          <div className="p-5">
            <div className="data-number text-2xl">{esc.total ?? 0}</div>
            <div className="flex gap-2 mt-2">{Object.entries(esc.by_level || {}).map(([lvl, n]) => <Badge key={lvl} tone="amber">L{lvl}: {n}</Badge>)}</div>
          </div>
        </Section>
      </div>

      <Section title={t("مقاييس الطلبات", "Request metrics")} actions={<Gauge size={14} className="text-muted-foreground" />}>
        <div className="p-5 grid grid-cols-2 md:grid-cols-4 gap-3 text-center">
          <div><div className="data-number text-2xl">{metrics.total_requests ?? 0}</div><div className="label-mono text-[9px]">{t("طلبات", "Requests")}</div></div>
          <div><div className="data-number text-2xl text-red-500">{metrics.total_errors ?? 0}</div><div className="label-mono text-[9px]">{t("أخطاء", "Errors")}</div></div>
          <div><div className="data-number text-2xl">{metrics.error_rate ?? 0}%</div><div className="label-mono text-[9px]">{t("نسبة الخطأ", "Error rate")}</div></div>
          <div><div className="data-number text-2xl text-amber-500">{metrics.total_denials ?? 0}</div><div className="label-mono text-[9px]">{t("رفض صلاحية", "Denials")}</div></div>
        </div>
        {(metrics.slowest_routes || []).length > 0 && (
          <div className="px-5 pb-4">
            <div className="label-mono mb-2">{t("أبطأ المسارات", "Slowest routes")}</div>
            <div className="space-y-1">{metrics.slowest_routes.slice(0, 5).map((r) => <div key={r.route} className="flex items-center justify-between text-xs"><span className="font-mono truncate">{r.route}</span><span className="font-mono text-muted-foreground">{r.max_ms}ms</span></div>)}</div>
          </div>
        )}
      </Section>

      <Section title={t("أخطاء حديثة", "Recent errors")} actions={<AlertOctagon size={14} className="text-muted-foreground" />}>
        <div className="divide-y divide-border">
          {errors.length === 0 && <Empty>{t("لا أخطاء — كل شيء سليم.", "No errors — all clear.")}</Empty>}
          {errors.map((e) => (
            <div key={e.id} className="px-5 py-2.5 flex items-center justify-between text-xs">
              <span className="font-mono truncate">{e.method} {e.route}</span>
              <span className="flex items-center gap-2"><Badge tone="red">{e.status}</Badge><span className="text-muted-foreground">{e.created_at ? new Date(e.created_at).toLocaleTimeString(locale) : ""}</span></span>
            </div>
          ))}
        </div>
      </Section>
    </div>
  );
}
