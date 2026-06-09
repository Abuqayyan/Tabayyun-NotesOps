import { useEffect, useMemo, useState, useRef } from "react";
import { api } from "@/lib/api";
import { useLang } from "@/contexts/LanguageContext";
import { motion } from "framer-motion";
import { Link } from "react-router-dom";
import { ChevronLeft, ChevronRight, Sparkles, AlertTriangle, Loader2, Plus } from "lucide-react";
import { toast } from "sonner";

const SEVERITY = {
  high: { bg: "bg-red-500/10", text: "text-red-500", border: "border-red-500/30" },
  medium: { bg: "bg-amber-500/10", text: "text-amber-500", border: "border-amber-500/30" },
  low: { bg: "bg-muted text-muted-foreground", text: "text-muted-foreground", border: "border-border" },
};

function startOfDay(d) {
  const x = new Date(d); x.setHours(0, 0, 0, 0); return x;
}

function fmtAxisLabel(date, zoom) {
  const opts = zoom === "week"
    ? { weekday: "short", day: "numeric" }
    : zoom === "month"
      ? { day: "numeric", month: "short" }
      : { day: "numeric", month: "short" };
  return date.toLocaleDateString(undefined, opts);
}

export default function Timeline() {
  const { lang, t } = useLang();
  const ZOOM_LEVELS = {
    week: { days: 7, dayPx: 140, label: t("أسبوع", "Week"), tick: 1 },
    month: { days: 30, dayPx: 32, label: t("شهر", "Month"), tick: 5 },
    quarter: { days: 90, dayPx: 14, label: t("ربع", "Quarter"), tick: 10 },
  };
  const locale = lang === "ar" ? "ar-EG" : "en-US";
  const [projects, setProjects] = useState([]);
  const [insights, setInsights] = useState([]);
  const [zoom, setZoom] = useState("month");
  const [anchor, setAnchor] = useState(() => startOfDay(new Date()));
  const [insightsBusy, setInsightsBusy] = useState(false);
  const [hover, setHover] = useState(null); // {id, x, y}
  const scrollRef = useRef(null);

  const cfg = ZOOM_LEVELS[zoom];

  const load = () => {
    api.get("/projects").then(r => setProjects(r.data));
  };
  const loadInsights = async () => {
    setInsightsBusy(true);
    try {
      const r = await api.get("/timeline/insights");
      setInsights(r.data.insights || []);
    } finally { setInsightsBusy(false); }
  };

  useEffect(() => {
    load();
    loadInsights();
  }, []);

  // Build axis ticks
  const ticks = useMemo(() => {
    const arr = [];
    for (let i = 0; i < cfg.days; i++) {
      const d = new Date(anchor); d.setDate(d.getDate() + i);
      arr.push(d);
    }
    return arr;
  }, [anchor, cfg.days]);

  const totalWidth = cfg.days * cfg.dayPx;
  const today = startOfDay(new Date());
  const todayOffset = Math.round((today - anchor) / 86400000) * cfg.dayPx;

  const dated = projects.filter(p => p.start_date && p.end_date);
  const undated = projects.filter(p => !p.start_date || !p.end_date);

  // Group bars per row (one project per row, no overlap stacking — keep simple)
  const rows = dated.map(p => ({ project: p }));

  const computeBar = (p) => {
    const s = startOfDay(new Date(p.start_date));
    const e = startOfDay(new Date(p.end_date));
    const startOffset = Math.round((s - anchor) / 86400000) * cfg.dayPx;
    const widthDays = Math.max(1, Math.round((e - s) / 86400000) + 1);
    const width = widthDays * cfg.dayPx;
    return { startOffset, width, isOverdue: e < today && p.status !== "completed" };
  };

  const shift = (days) => {
    const x = new Date(anchor); x.setDate(x.getDate() + days); setAnchor(startOfDay(x));
  };

  const insightsByProject = useMemo(() => {
    const map = {};
    insights.forEach(i => (i.project_ids || []).forEach(pid => {
      map[pid] = map[pid] || []; map[pid].push(i);
    }));
    return map;
  }, [insights]);

  // Drag to reschedule
  const [dragging, setDragging] = useState(null); // {id, mode:'move'|'resize-end', startX, origStart, origEnd}
  const onPointerDown = (e, p, mode) => {
    e.stopPropagation();
    setDragging({
      id: p.id, mode, startX: e.clientX,
      origStart: new Date(p.start_date),
      origEnd: new Date(p.end_date),
    });
  };
  useEffect(() => {
    if (!dragging) return;
    const onMove = (e) => {
      const deltaDays = Math.round((e.clientX - dragging.startX) / cfg.dayPx);
      if (!deltaDays) return;
      setProjects(prev => prev.map(p => {
        if (p.id !== dragging.id) return p;
        const newStart = dragging.mode === "resize-end" ? p.start_date : new Date(dragging.origStart.getTime() + deltaDays * 86400000).toISOString();
        const newEnd = new Date(dragging.origEnd.getTime() + deltaDays * 86400000).toISOString();
        return { ...p, start_date: newStart, end_date: newEnd };
      }));
    };
    const onUp = async () => {
      const p = projects.find(x => x.id === dragging.id);
      const d = dragging; setDragging(null);
      if (p) {
        try {
          await api.patch(`/projects/${p.id}`, { start_date: p.start_date, end_date: p.end_date });
        } catch { load(); toast.error(t("لم نقدر نحفظ الجدولة", "Couldn't save the schedule")); return; }
        toast.success(t("تمت إعادة الجدولة", "Rescheduled"));
        loadInsights();
      }
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp, { once: true });
    return () => { window.removeEventListener("pointermove", onMove); window.removeEventListener("pointerup", onUp); };
  }, [dragging, cfg.dayPx, projects]);

  return (
    <div className="space-y-4" data-testid="timeline-view">
      {/* Toolbar */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-1">
          <button onClick={() => shift(-cfg.days)} className="w-8 h-8 rounded-md border border-border hover:bg-secondary flex items-center justify-center" title={t("للخلف", "Back")}><ChevronLeft size={14} className="rtl:rotate-180" /></button>
          <button onClick={() => setAnchor(startOfDay(new Date()))} className="px-3 h-8 rounded-md border border-border hover:bg-secondary text-xs font-mono">{t("اليوم", "Today")}</button>
          <button onClick={() => shift(cfg.days)} className="w-8 h-8 rounded-md border border-border hover:bg-secondary flex items-center justify-center" title={t("للأمام", "Forward")}><ChevronRight size={14} className="rtl:rotate-180" /></button>
          <div className="ms-2 label-mono">{ticks[0]?.toLocaleDateString(locale, { month: "short", day: "numeric", year: "numeric" })} → {ticks[ticks.length - 1]?.toLocaleDateString(locale, { month: "short", day: "numeric" })}</div>
        </div>
        <div className="flex items-center gap-1 p-0.5 border border-border rounded-md">
          {Object.entries(ZOOM_LEVELS).map(([k, v]) => (
            <button key={k} onClick={() => setZoom(k)} data-testid={`zoom-${k}`}
              className={`px-3 h-7 rounded-sm text-xs font-mono transition-colors ${zoom === k ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`}>
              {v.label}
            </button>
          ))}
        </div>
      </div>

      {/* AI Insights ribbon */}
      {insights.length > 0 && (
        <div className="border border-border bg-card rounded-md overflow-hidden">
          <div className="hairline px-4 py-2 flex items-center justify-between">
            <div className="flex items-center gap-2"><Sparkles size={12} className="text-primary" /><div className="label-mono">{t("رؤى الجدول الزمني", "Timeline insights")}</div></div>
            <button onClick={loadInsights} disabled={insightsBusy} className="label-mono text-[10px] text-muted-foreground hover:text-foreground">
              {insightsBusy ? <Loader2 size={10} className="animate-spin inline" /> : `↻ ${t("تحديث", "Refresh")}`}
            </button>
          </div>
          <div className="flex gap-2 overflow-x-auto p-3">
            {insights.map((ins, i) => {
              const s = SEVERITY[ins.severity] || SEVERITY.low;
              return (
                <motion.div key={i} initial={{ opacity: 0, x: 8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.04 }}
                  className={`shrink-0 px-3 py-2 rounded-md border ${s.border} ${s.bg} max-w-xs`}>
                  <div className="flex items-center gap-1.5 mb-1">
                    <AlertTriangle size={10} className={s.text} />
                    <span className={`label-mono text-[9px] ${s.text}`}>{ins.type}</span>
                  </div>
                  <div className="text-xs leading-relaxed">{ins.message}</div>
                </motion.div>
              );
            })}
          </div>
        </div>
      )}

      {/* Timeline */}
      <div className="border border-border bg-card rounded-md overflow-hidden">
        <div className="overflow-x-auto" ref={scrollRef}>
          <div style={{ width: totalWidth, minWidth: "100%" }} className="relative">
            {/* Axis */}
            <div className="sticky top-0 z-10 bg-card border-b border-border flex h-9">
              {ticks.map((d, i) => {
                const isToday = d.getTime() === today.getTime();
                const showLabel = i % cfg.tick === 0;
                const isWeekend = d.getDay() === 0 || d.getDay() === 6;
                return (
                  <div key={i} style={{ width: cfg.dayPx }}
                    className={`relative border-r border-border/40 flex items-center justify-start px-1 ${isWeekend ? "bg-secondary/20" : ""}`}>
                    {showLabel && <span className={`label-mono text-[9px] truncate ${isToday ? "text-primary" : ""}`}>{fmtAxisLabel(d, zoom)}</span>}
                  </div>
                );
              })}
            </div>

            {/* Today marker */}
            {todayOffset >= 0 && todayOffset <= totalWidth && (
              <div className="absolute top-9 bottom-0 w-px bg-primary z-20 pointer-events-none"
                style={{ left: todayOffset }}>
                <div className="absolute -top-1 -translate-x-1/2 w-2 h-2 rounded-full bg-primary" />
              </div>
            )}

            {/* Rows */}
            <div className="relative">
              {rows.length === 0 && (
                <div className="py-16 text-center text-sm text-muted-foreground">
                  {t("لا توجد مشاريع مجدولة. أضف تواريخ بداية ونهاية لرؤيتها على الجدول الزمني.", "No scheduled projects. Add start and end dates to see them on the timeline.")}
                </div>
              )}
              {rows.map((row, idx) => {
                const { project: p } = row;
                const { startOffset, width, isOverdue } = computeBar(p);
                const hasInsight = !!insightsByProject[p.id];
                return (
                  <div key={p.id} className="relative h-14 border-b border-border/40 hairline" style={{ minWidth: totalWidth }}>
                    {/* day grid */}
                    {ticks.map((d, i) => {
                      const isWeekend = d.getDay() === 0 || d.getDay() === 6;
                      return <div key={i} className={`absolute top-0 bottom-0 border-r border-border/30 ${isWeekend ? "bg-secondary/10" : ""}`}
                        style={{ left: i * cfg.dayPx, width: cfg.dayPx }} />;
                    })}
                    {/* bar */}
                    {width > 0 && startOffset + width > 0 && startOffset < totalWidth && (
                      <motion.div
                        initial={{ opacity: 0, scaleX: 0.95 }} animate={{ opacity: 1, scaleX: 1 }}
                        transition={{ duration: 0.18 }}
                        onPointerDown={(e) => onPointerDown(e, p, "move")}
                        onMouseEnter={(e) => setHover({ id: p.id, x: e.clientX, y: e.clientY })}
                        onMouseLeave={() => setHover(null)}
                        className={`absolute top-2 bottom-2 rounded-md cursor-grab active:cursor-grabbing select-none group ${dragging?.id === p.id ? "opacity-80 ring-2 ring-primary" : ""}`}
                        style={{
                          left: startOffset,
                          width: width,
                          backgroundColor: p.color || "#FF4500",
                          opacity: isOverdue ? 0.7 : 1,
                          border: isOverdue ? "1px dashed white" : `1px solid ${p.color}40`,
                        }}
                      >
                        <div className="h-full px-2 flex items-center gap-1.5 overflow-hidden text-white">
                          <span className="text-xs font-medium tracking-tight truncate">{p.name}</span>
                          {hasInsight && <AlertTriangle size={10} className="shrink-0 opacity-80" />}
                        </div>
                        {/* Progress fill */}
                        <div className="absolute left-0 bottom-0 h-0.5 bg-white/40" style={{ width: `${p.progress || 0}%` }} />
                        {/* Resize-end handle */}
                        <div
                          onPointerDown={(e) => onPointerDown(e, p, "resize-end")}
                          className="absolute right-0 top-0 bottom-0 w-1.5 cursor-ew-resize opacity-0 group-hover:opacity-100 bg-white/30"
                        />
                      </motion.div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* Unscheduled tray */}
      {undated.length > 0 && (
        <div className="border border-dashed border-border rounded-md p-4">
          <div className="label-mono mb-2 flex items-center gap-2"><Plus size={11} /> {t("مشاريع غير مجدولة", "Unscheduled projects")}</div>
          <div className="flex flex-wrap gap-2">
            {undated.map(p => (
              <Link key={p.id} to={`/projects/${p.id}`}
                className="px-3 py-1.5 rounded-md border border-border bg-background hover:border-primary/40 text-xs flex items-center gap-1.5">
                <div className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: p.color }} />
                {p.name}
              </Link>
            ))}
          </div>
          <p className="label-mono text-[10px] mt-3">{t("افتح المشروع لإضافة تاريخي البداية والنهاية. أو استخدم الجدولة الذكية من صفحة المشروع.", "Open a project to add start/end dates. Or use AI scheduling from the project page.")}</p>
        </div>
      )}

      {/* Hover tooltip */}
      {hover && (
        <div className="fixed pointer-events-none z-40 px-3 py-2 bg-popover border border-border rounded-md shadow-lg text-xs"
          style={{ left: hover.x + 12, top: hover.y + 12 }}>
          {(() => {
            const p = projects.find(x => x.id === hover.id);
            if (!p) return null;
            const ins = insightsByProject[p.id] || [];
            return (
              <div className="space-y-1 max-w-[260px]">
                <div className="font-medium">{p.name}</div>
                <div className="label-mono text-[9px]">{new Date(p.start_date).toLocaleDateString()} → {new Date(p.end_date).toLocaleDateString()}</div>
                <div className="label-mono text-[9px]">{p.progress || 0}% · {p.priority}</div>
                {ins.slice(0, 2).map((i, k) => (
                  <div key={k} className={`mt-1 text-[10px] ${SEVERITY[i.severity]?.text || ""}`}>· {i.message}</div>
                ))}
              </div>
            );
          })()}
        </div>
      )}
    </div>
  );
}
