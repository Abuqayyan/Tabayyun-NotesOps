import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { useLang } from "@/contexts/LanguageContext";
import { ChevronLeft, ChevronRight, Plus, X, Trash2, Loader2 } from "lucide-react";
import { toast } from "sonner";

const DAYS_AR = ["الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت"];
const DAYS_EN = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS_AR = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"];
const MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

function startOfMonth(d) { return new Date(d.getFullYear(), d.getMonth(), 1); }
function endOfMonth(d) { return new Date(d.getFullYear(), d.getMonth() + 1, 0); }
function addMonths(d, n) { return new Date(d.getFullYear(), d.getMonth() + n, 1); }
function fmtIsoLocal(d, hour = 9, min = 0) {
  const yyyy = d.getFullYear(), mm = String(d.getMonth() + 1).padStart(2, "0"), dd = String(d.getDate()).padStart(2, "0");
  const hh = String(hour).padStart(2, "0"), mi = String(min).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}T${hh}:${mi}:00+00:00`;
}

export default function Calendar() {
  const { lang, t } = useLang();
  const isAr = lang === "ar";
  const DAYS = isAr ? DAYS_AR : DAYS_EN;
  const MONTHS = isAr ? MONTHS_AR : MONTHS_EN;

  const [cursor, setCursor] = useState(new Date());
  const [events, setEvents] = useState([]);
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(false);
  const [openDay, setOpenDay] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ title: "", start: "", end: "", project_id: "", type: "event", notes: "" });

  const monthStart = startOfMonth(cursor);
  const monthEnd = endOfMonth(cursor);
  const firstWeekday = monthStart.getDay();

  const load = async () => {
    setLoading(true);
    try {
      const s = new Date(monthStart); s.setDate(s.getDate() - 7);
      const e = new Date(monthEnd); e.setDate(e.getDate() + 7);
      const r = await api.get("/calendar/events", { params: { start: s.toISOString(), end: e.toISOString() } });
      setEvents(r.data || []);
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [cursor]);
  useEffect(() => { api.get("/projects").then(r => setProjects(r.data || [])).catch(() => {}); }, []);

  const eventsByDay = useMemo(() => {
    const map = {};
    for (const ev of events) {
      const k = (ev.start || "").slice(0, 10);
      if (!k) continue;
      (map[k] = map[k] || []).push(ev);
    }
    return map;
  }, [events]);

  const days = useMemo(() => {
    const out = [];
    for (let i = 0; i < firstWeekday; i++) out.push(null);
    for (let d = 1; d <= monthEnd.getDate(); d++) {
      const date = new Date(cursor.getFullYear(), cursor.getMonth(), d);
      out.push(date);
    }
    while (out.length % 7 !== 0) out.push(null);
    return out;
  }, [cursor, firstWeekday, monthEnd]);

  const openCreate = (date) => {
    setForm({
      title: "",
      start: fmtIsoLocal(date, 9, 0),
      end: fmtIsoLocal(date, 10, 0),
      project_id: "",
      type: "event",
      notes: "",
    });
    setShowForm(true);
    setOpenDay(date);
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!form.title || !form.start || !form.end) return;
    try {
      await api.post("/calendar/events", {
        title: form.title, start: form.start, end: form.end,
        project_id: form.project_id || null, type: form.type, notes: form.notes,
      });
      toast.success(t("تم إنشاء الحدث", "Event created"));
      setShowForm(false);
      load();
    } catch { toast.error(t("فشل", "Failed")); }
  };

  const deleteEvent = async (id) => {
    if (id.startsWith("task-")) {
      toast.message(t("هذا حدث من مهمة — احذف المهمة بدلًا منه.", "This is a task-derived event — delete the task instead."));
      return;
    }
    try { await api.delete(`/calendar/events/${id}`); toast.success(t("تم الحذف", "Deleted")); load(); }
    catch { toast.error(t("فشل", "Failed")); }
  };

  const today = new Date(); today.setHours(0, 0, 0, 0);
  const todayKey = today.toISOString().slice(0, 10);

  return (
    <div className="p-6 lg:p-8 space-y-6" data-testid="calendar-page">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="label-mono">{t("التقويم الداخلي", "Internal calendar")}</div>
          <h1 className="text-3xl sm:text-4xl tracking-tight font-medium mt-1">
            {MONTHS[cursor.getMonth()]} {cursor.getFullYear()}
          </h1>
          <p className="text-sm text-muted-foreground mt-1">{t("الأحداث، الاجتماعات، وكل مهمة لها موعد.", "Events, meetings, and any task with a date.")}</p>
        </div>
        <div className="flex items-center gap-1">
          <button data-testid="cal-prev" onClick={() => setCursor(addMonths(cursor, -1))} className="w-9 h-9 border border-border rounded-md hover:bg-secondary flex items-center justify-center">
            <ChevronRight size={14} className="rtl:rotate-180" />
          </button>
          <button data-testid="cal-today" onClick={() => setCursor(new Date())} className="px-3 h-9 border border-border rounded-md hover:bg-secondary text-xs font-mono">
            {t("اليوم", "Today")}
          </button>
          <button data-testid="cal-next" onClick={() => setCursor(addMonths(cursor, 1))} className="w-9 h-9 border border-border rounded-md hover:bg-secondary flex items-center justify-center">
            <ChevronLeft size={14} className="rtl:rotate-180" />
          </button>
        </div>
      </div>

      <div className="border border-border bg-card rounded-md overflow-hidden">
        <div className="grid grid-cols-7 border-b border-border bg-secondary/30">
          {DAYS.map((d) => (
            <div key={d} className="px-3 py-2 label-mono text-[10px] text-center">{d}</div>
          ))}
        </div>
        <div className="grid grid-cols-7">
          {days.map((d, i) => {
            if (!d) return <div key={i} className="min-h-[110px] border-t border-e border-border bg-background/30" />;
            const k = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
            const dayEvents = eventsByDay[k] || [];
            const isToday = k === todayKey;
            return (
              <button
                key={i}
                data-testid={`cal-day-${k}`}
                onClick={() => openCreate(d)}
                className={`text-start min-h-[110px] border-t border-e border-border p-2 hover:bg-secondary/30 transition-colors ${isToday ? "bg-primary/5" : ""}`}
              >
                <div className={`text-xs font-mono ${isToday ? "text-primary font-semibold" : "text-muted-foreground"}`}>
                  {d.getDate()}
                </div>
                <div className="mt-1 space-y-0.5">
                  {dayEvents.slice(0, 3).map(ev => (
                    <div key={ev.id} className="truncate text-[11px] px-1.5 py-0.5 rounded" style={{ background: (ev.color || "#FF4500") + "22", color: ev.color || "#FF4500" }}>
                      {ev.title}
                    </div>
                  ))}
                  {dayEvents.length > 3 && <div className="label-mono text-[9px]">+{dayEvents.length - 3}</div>}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {showForm && (
        <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4" onClick={() => setShowForm(false)}>
          <div className="bg-card border border-border rounded-lg w-full max-w-md p-6 space-y-4" onClick={(e) => e.stopPropagation()} data-testid="event-form">
            <div className="flex items-center justify-between">
              <div>
                <div className="label-mono">{t("حدث جديد", "New event")}</div>
                <h3 className="text-lg font-medium mt-0.5">{openDay?.toLocaleDateString(isAr ? "ar-EG" : "en-US")}</h3>
              </div>
              <button onClick={() => setShowForm(false)} className="text-muted-foreground hover:text-foreground"><X size={16} /></button>
            </div>
            <form onSubmit={submit} className="space-y-3">
              <input data-testid="event-title" required value={form.title} onChange={e => setForm({ ...form, title: e.target.value })}
                placeholder={t("عنوان الحدث", "Event title")}
                className="w-full px-3 py-2 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary" />
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="label-mono mb-1 block">{t("من", "From")}</label>
                  <input data-testid="event-start" type="datetime-local" required
                    value={form.start.replace("+00:00", "").slice(0, 16)}
                    onChange={e => setForm({ ...form, start: e.target.value + ":00+00:00" })}
                    className="w-full px-2 py-2 bg-background border border-border rounded-md text-xs" />
                </div>
                <div>
                  <label className="label-mono mb-1 block">{t("إلى", "To")}</label>
                  <input data-testid="event-end" type="datetime-local" required
                    value={form.end.replace("+00:00", "").slice(0, 16)}
                    onChange={e => setForm({ ...form, end: e.target.value + ":00+00:00" })}
                    className="w-full px-2 py-2 bg-background border border-border rounded-md text-xs" />
                </div>
              </div>
              <select value={form.project_id} onChange={e => setForm({ ...form, project_id: e.target.value })}
                className="w-full px-3 py-2 bg-background border border-border rounded-md text-sm">
                <option value="">{t("بدون مشروع", "No project")}</option>
                {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
              <textarea value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })}
                placeholder={t("ملاحظات", "Notes")} rows={2}
                className="w-full px-3 py-2 bg-background border border-border rounded-md text-sm resize-none" />
              <button data-testid="event-submit" type="submit"
                className="w-full bg-primary text-primary-foreground py-2 rounded-md text-sm font-medium hover:opacity-90 flex items-center justify-center gap-2">
                <Plus size={13} /> {t("أضف", "Create")}
              </button>
            </form>

            {openDay && (eventsByDay[openDay.toISOString().slice(0, 10)] || []).length > 0 && (
              <div className="border-t border-border pt-3 space-y-2">
                <div className="label-mono">{t("في هذا اليوم", "On this day")}</div>
                {(eventsByDay[openDay.toISOString().slice(0, 10)] || []).map(ev => (
                  <div key={ev.id} className="flex items-center justify-between text-sm px-2 py-1.5 rounded hover:bg-secondary">
                    <div className="flex items-center gap-2">
                      <div className="w-1.5 h-1.5 rounded-full" style={{ background: ev.color || "#FF4500" }} />
                      <span className="truncate">{ev.title}</span>
                      {ev.synthetic && <span className="label-mono text-[9px] text-muted-foreground">{t("مهمة", "task")}</span>}
                    </div>
                    {!ev.synthetic && (
                      <button onClick={() => deleteEvent(ev.id)} className="text-muted-foreground hover:text-destructive">
                        <Trash2 size={12} />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {loading && <div className="fixed bottom-6 end-6 bg-card border border-border rounded-md px-3 py-1.5 text-xs flex items-center gap-2"><Loader2 size={12} className="animate-spin" /> {t("تحميل…", "Loading…")}</div>}
    </div>
  );
}
