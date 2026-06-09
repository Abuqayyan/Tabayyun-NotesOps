import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { useLang } from "@/contexts/LanguageContext";
import { Link } from "react-router-dom";
import { CalendarDays, Layers, Loader2, ArrowRight } from "lucide-react";
import { toast } from "sonner";
import { motion } from "framer-motion";

// Day mapping — start the visual week on SATURDAY for Arabic founders (matches typical work week).
// Each entry: { key (0..6 ISO Sunday=0), labelAr, labelEn, shortAr, shortEn }
const DAYS = [
  { key: 6, ar: "السبت", en: "Saturday", shortAr: "سبت", shortEn: "Sat" },
  { key: 0, ar: "الأحد", en: "Sunday", shortAr: "أحد", shortEn: "Sun" },
  { key: 1, ar: "الإثنين", en: "Monday", shortAr: "إثن", shortEn: "Mon" },
  { key: 2, ar: "الثلاثاء", en: "Tuesday", shortAr: "ثل", shortEn: "Tue" },
  { key: 3, ar: "الأربعاء", en: "Wednesday", shortAr: "أرب", shortEn: "Wed" },
  { key: 4, ar: "الخميس", en: "Thursday", shortAr: "خم", shortEn: "Thu" },
  { key: 5, ar: "الجمعة", en: "Friday", shortAr: "جمعة", shortEn: "Fri" },
];

export default function Schedule() {
  const { lang, t } = useLang();
  const [data, setData] = useState(null);
  const [projects, setProjects] = useState([]);
  const [busy, setBusy] = useState(null); // project id currently being mutated

  const load = async () => {
    const [s, p] = await Promise.all([
      api.get("/schedule"),
      api.get("/projects"),
    ]);
    setData(s.data);
    setProjects(p.data);
  };

  useEffect(() => { load(); }, []);

  // local lookup of weekly_days per project (rebuilt on data change)
  const projectDays = useMemo(() => {
    const m = {};
    if (!data) return m;
    Object.entries(data.by_day).forEach(([d, list]) => {
      list.forEach(p => {
        m[p.id] = m[p.id] || new Set();
        m[p.id].add(parseInt(d));
      });
    });
    data.unscheduled.forEach(p => { if (!m[p.id]) m[p.id] = new Set(); });
    return m;
  }, [data]);

  const toggleDay = async (projectId, dayKey) => {
    const current = new Set(projectDays[projectId] || []);
    if (current.has(dayKey)) current.delete(dayKey);
    else current.add(dayKey);
    const arr = Array.from(current).sort((a, b) => a - b);
    setBusy(projectId);
    try {
      await api.patch(`/projects/${projectId}`, { weekly_days: arr });
      // optimistic local update so the UI feels instant
      await load();
    } catch {
      toast.error(t("فشل التحديث", "Update failed"));
    } finally { setBusy(null); }
  };

  const todayKey = (() => new Date().getDay())(); // 0=Sun .. 6=Sat
  const isToday = (k) => k === todayKey;

  if (!data) return <div className="p-8 label-mono">{t("جارٍ التحميل…", "Loading…")}</div>;

  return (
    <div className="p-6 lg:p-8 space-y-6" data-testid="schedule-page">
      <div className="flex items-end justify-between flex-wrap gap-4">
        <div>
          <div className="label-mono">{t("التخطيط", "Planning")}</div>
          <h1 className="text-3xl sm:text-4xl tracking-tight font-medium mt-1">{t("الجدول الأسبوعي", "Weekly schedule")}</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {t(
              "حدّد أيّ مشروع تشتغل عليه في أيّ يوم من الأسبوع. ثمّ افلتر مهامك بحسب اليوم.",
              "Pin each project to specific days of the week. Then filter tasks by the day you're working.",
            )}
          </p>
        </div>
        <Link to="/tasks" className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1.5">
          <ArrowRight size={12} className="rtl:rotate-180" /> {t("اذهب إلى المهام", "Go to tasks")}
        </Link>
      </div>

      {/* 7-day grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-7 gap-3" data-testid="schedule-grid">
        {DAYS.map(d => {
          const items = data.by_day[d.key] || [];
          return (
            <div key={d.key}
              className={`border bg-card rounded-md min-h-[200px] ${isToday(d.key) ? "border-primary ring-1 ring-primary/30" : "border-border"}`}
              data-testid={`day-${d.key}`}
            >
              <div className="hairline px-3 py-2.5 flex items-center justify-between">
                <div>
                  <div className="text-sm font-medium tracking-tight">{lang === "ar" ? d.ar : d.en}</div>
                  {isToday(d.key) && <div className="label-mono text-[9px] text-primary mt-0.5">{t("اليوم", "Today")}</div>}
                </div>
                <span className="font-mono text-xs text-muted-foreground">{items.length}</span>
              </div>
              <div className="p-2 space-y-1.5">
                {items.length === 0 ? (
                  <div className="px-2 py-6 text-center text-xs text-muted-foreground">{t("لا شيء", "Nothing")}</div>
                ) : items.map((p, i) => (
                  <motion.div key={p.id} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }}
                    className="px-2.5 py-2 border border-border bg-background rounded-md group">
                    <div className="flex items-center gap-2 min-w-0">
                      <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: p.color }} />
                      <Link to={`/projects/${p.id}`} className="text-sm flex-1 truncate hover:text-primary">{p.name}</Link>
                      <button
                        onClick={() => toggleDay(p.id, d.key)}
                        disabled={busy === p.id}
                        title={t("إزالة من هذا اليوم", "Remove from this day")}
                        className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive text-xs"
                      >×</button>
                    </div>
                    {p.open_tasks > 0 && (
                      <div className="label-mono text-[9px] mt-1">{p.open_tasks} {t("مهمة مفتوحة", "open tasks")}</div>
                    )}
                  </motion.div>
                ))}
              </div>
            </div>
          );
        })}
      </div>

      {/* Project rows — toggle each day per project */}
      <div className="border border-border bg-card rounded-md" data-testid="projects-day-toggles">
        <div className="hairline px-5 py-3 flex items-center gap-2">
          <Layers size={13} className="text-primary" />
          <div className="label-mono">{t("ضبط أيّ مشروع لأيّ يوم", "Configure projects per day")}</div>
          <span className="label-mono text-[10px] ms-auto text-muted-foreground">{projects.length} {t("مشروع", "projects")}</span>
        </div>
        {projects.length === 0 ? (
          <div className="p-8 text-center text-sm text-muted-foreground">{t("لا توجد مشاريع. أنشئ مشروعًا أولاً.", "No projects. Create one first.")}</div>
        ) : (
          <div className="divide-y divide-border">
            {projects.filter(p => p.status !== "archived").map(p => {
              const selected = projectDays[p.id] || new Set();
              return (
                <div key={p.id} className="px-5 py-3 flex items-center gap-3 flex-wrap" data-testid={`project-row-${p.id}`}>
                  <div className="flex items-center gap-2 min-w-0 flex-1">
                    <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: p.color || "#FF4500" }} />
                    <div className="min-w-0">
                      <div className="text-sm font-medium truncate">{p.name}</div>
                      <div className="label-mono text-[9px]">
                        {selected.size === 0 ? t("غير مجدول", "Unscheduled") : (selected.size === 7 ? t("كل أيام الأسبوع", "Every day") : `${selected.size} ${t("أيام/أسبوع", "days/week")}`)}
                      </div>
                    </div>
                  </div>
                  <div className="flex gap-1 shrink-0">
                    {DAYS.map(d => {
                      const on = selected.has(d.key);
                      return (
                        <button
                          key={d.key}
                          onClick={() => toggleDay(p.id, d.key)}
                          disabled={busy === p.id}
                          data-testid={`toggle-${p.id}-${d.key}`}
                          className={`w-10 h-9 rounded-md text-xs font-mono transition-colors flex items-center justify-center ${
                            on
                              ? "bg-primary text-primary-foreground"
                              : "border border-border text-muted-foreground hover:text-foreground hover:bg-secondary"
                          } ${isToday(d.key) && !on ? "ring-1 ring-primary/30" : ""}`}
                          title={lang === "ar" ? d.ar : d.en}
                        >
                          {busy === p.id ? <Loader2 size={11} className="animate-spin" /> : (lang === "ar" ? d.shortAr : d.shortEn)}
                        </button>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="border border-amber-500/30 bg-amber-500/5 rounded-md px-4 py-3 flex items-center gap-2 text-sm">
        <CalendarDays size={14} className="text-amber-500 shrink-0" />
        <span>
          {t("نصيحة:", "Tip:")}{" "}
          {t(
            "بعد ضبط الأيام، اذهب لصفحة المهام واستخدم فلتر «يوم الأسبوع» لتركّز على مهام اليوم فقط.",
            "After setting days, go to Tasks and use the day-of-week filter to focus on today's work only.",
          )}
        </span>
      </div>
    </div>
  );
}
