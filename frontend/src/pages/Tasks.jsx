import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useLang } from "@/contexts/LanguageContext";
import {
  Plus, Sparkles, X, Trash2, MessageSquare, Send,
  Search, LayoutGrid, CalendarDays, CalendarRange,
  Pin, PinOff, AlertTriangle
} from "lucide-react";
import { toast } from "sonner";
import { motion } from "framer-motion";
import DateTimeField from "@/components/DateTimeField";
import ReminderBell from "@/components/ReminderBell";

const PRIO_DOT = {
  critical: "bg-red-500",
  high: "bg-amber-500",
  medium: "bg-muted-foreground",
  low: "bg-emerald-500",
};

const todayISO = () => new Date().toISOString().slice(0, 10);

function isOverdue(t) {
  const d = t.due_date || t.end_date;
  if (!d || t.status === "done") return false;
  try { return new Date(d) < new Date(); } catch { return false; }
}

export default function Tasks() {
  const { lang, t } = useLang();
  const [tasks, setTasks] = useState([]);
  const [projects, setProjects] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ title: "", description: "", priority: "medium", complexity: "medium", project_id: "", estimated_minutes: 30, start_date: "", end_date: "", scheduled_for: "" });
  const [selected, setSelected] = useState(null);
  const [updates, setUpdates] = useState([]);
  const [newUpdate, setNewUpdate] = useState("");
  const [draggingId, setDraggingId] = useState(null);
  const [hoverCol, setHoverCol] = useState(null);

  // Filters & views
  const [view, setView] = useState(() => localStorage.getItem("opscore_tasks_view") || "all"); // all | today | week
  const [projectFilter, setProjectFilter] = useState("all"); // "all" | project_id
  const [dayFilter, setDayFilter] = useState("all"); // "all" | 0..6 (day of week)
  const [search, setSearch] = useState("");
  const [todayHints, setTodayHints] = useState({ overdue_unpinned: 0, in_progress_unpinned: 0 });
  const [teammates, setTeammates] = useState([]);

  useEffect(() => { api.get("/team/members").then(r => setTeammates(r.data || [])).catch(() => {}); }, []);

  const COLUMNS = [
    { key: "todo", label: t("للقيام", "To do") },
    { key: "in_progress", label: t("جارٍ", "In progress") },
    { key: "blocked", label: t("معلّق", "Blocked") },
    { key: "done", label: t("منجز", "Done") },
  ];
  const PRIORITIES = [
    { v: "low", l: t("منخفض", "Low") },
    { v: "medium", l: t("متوسط", "Medium") },
    { v: "high", l: t("عالٍ", "High") },
    { v: "critical", l: t("حرج", "Critical") },
  ];
  const COMPLEXITY = [
    { v: "low", l: t("منخفض", "Low") },
    { v: "medium", l: t("متوسط", "Medium") },
    { v: "high", l: t("عالٍ", "High") },
  ];
  const locale = lang === "ar" ? "ar-EG" : "en-US";

  // Project lookup by id (for chips on each card)
  const projectById = useMemo(() => Object.fromEntries(projects.map(p => [p.id, p])), [projects]);

  // Only the latest load() response wins — discard stale responses from earlier requests.
  const loadVersion = useRef(0);
  const load = () => {
    const myVersion = ++loadVersion.current;
    const params = {};
    if (view !== "all") { params.view = view; params.today = todayISO(); }
    if (projectFilter !== "all") params.project_id = projectFilter;
    if (dayFilter !== "all") params.day_of_week = dayFilter;
    if (search.trim()) params.q = search.trim();
    return api.get("/tasks", { params })
      .then(r => { if (myVersion === loadVersion.current) setTasks(r.data); });
  };

  // Refresh the small banner counts when entering Today view
  useEffect(() => {
    if (view !== "today") { setTodayHints({ overdue_unpinned: 0, in_progress_unpinned: 0 }); return; }
    api.get("/tasks/today-hints", { params: { today: todayISO() } })
      .then(r => setTodayHints(r.data))
      .catch(() => {});
  }, [view, tasks]);

  useEffect(() => {
    api.get("/projects").then(r => setProjects(r.data));
  }, []);

  // Debounce search; reload on any filter change
  useEffect(() => {
    const id = setTimeout(load, 250);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, projectFilter, dayFilter, search]);

  useEffect(() => {
    localStorage.setItem("opscore_tasks_view", view);
  }, [view]);

  useEffect(() => {
    const handler = () => load();
    window.addEventListener("opscore:task", handler);
    return () => window.removeEventListener("opscore:task", handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, projectFilter, dayFilter, search]);

  // ---- Drag & drop ----
  const onDragStart = (e, id) => {
    setDraggingId(id);
    e.dataTransfer.effectAllowed = "move";
    try { e.dataTransfer.setData("text/plain", id); } catch { /* noop */ }
  };
  const onDragEnd = () => { setDraggingId(null); setHoverCol(null); };
  const onDragOver = (e, key) => { e.preventDefault(); setHoverCol(key); };
  const onDrop = async (e, status) => {
    e.preventDefault();
    const id = draggingId || e.dataTransfer.getData("text/plain");
    setDraggingId(null); setHoverCol(null);
    if (!id) return;
    const task = tasks.find(tk => tk.id === id);
    if (!task || task.status === status) return;
    setTasks(prev => prev.map(tk => tk.id === id ? { ...tk, status } : tk));
    try { await api.patch(`/tasks/${id}`, { status }); }
    catch { load(); toast.error(t("فشل النقل", "Move failed")); }
  };

  // ---- CRUD ----
  const create = async (e) => {
    e.preventDefault();
    try {
      await api.post("/tasks", {
        ...form,
        project_id: form.project_id || null,
        start_date: form.start_date || null,
        end_date: form.end_date || null,
        due_date: form.end_date || null,
        scheduled_for: form.scheduled_for || null,
      });
      toast.success(form.scheduled_for === todayISO() ? t("تم إنشاؤها وتثبيتها في اليوم", "Created and pinned to today") : t("تم إنشاء المهمة", "Task created"));
      setOpen(false);
      setForm({ title: "", description: "", priority: "medium", complexity: "medium", project_id: projectFilter !== "all" ? projectFilter : "", estimated_minutes: 30, start_date: "", end_date: "", scheduled_for: view === "today" ? todayISO() : "" });
      load();
    } catch { toast.error(t("فشل", "Failed")); }
  };

  const update = async (tid, patch) => {
    await api.patch(`/tasks/${tid}`, patch); load();
    if (selected?.id === tid) setSelected({ ...selected, ...patch });
  };
  const remove = async (tid) => { await api.delete(`/tasks/${tid}`); setSelected(null); load(); };

  const pinToToday = async (tk, e) => {
    e?.stopPropagation();
    const now = todayISO();
    const isPinned = tk.scheduled_for === now;
    await update(tk.id, { scheduled_for: isPinned ? null : now });
    toast.success(isPinned ? t("تم الإزالة من اليوم", "Removed from today") : t("تم التثبيت في اليوم", "Pinned to today"));
  };

  // ---- Task updates log ----
  const loadUpdates = async (tid) => {
    try { const r = await api.get(`/tasks/${tid}/updates`); setUpdates(r.data); } catch { setUpdates([]); }
  };
  useEffect(() => {
    if (selected?.id) loadUpdates(selected.id);
    else { setUpdates([]); setNewUpdate(""); }
  }, [selected?.id]);

  const postUpdate = async (e) => {
    e?.preventDefault?.();
    const content = newUpdate.trim();
    if (!content || !selected?.id) return;
    try {
      await api.post(`/tasks/${selected.id}/updates`, { content });
      setNewUpdate("");
      toast.success(t("تم تسجيل التحديث", "Update logged"));
      loadUpdates(selected.id);
    } catch { toast.error(t("فشل", "Failed")); }
  };
  const removeUpdate = async (uid) => {
    if (!selected?.id) return;
    await api.delete(`/tasks/${selected.id}/updates/${uid}`);
    loadUpdates(selected.id);
  };

  const breakdown = async (tid) => {
    toast.message(t("يتم التجزئة بالذكاء…", "AI breakdown in progress…"));
    try {
      const r = await api.post("/ai/breakdown", { task_id: tid });
      toast.success(`${r.data.subtasks?.length || 0} ${t("مهمة فرعية تم توليدها", "subtasks generated")}`);
      load();
      if (selected?.id === tid) setSelected(r.data.task);
    } catch { toast.error(t("خطأ في الذكاء", "AI error")); }
  };

  // ---- Stats strip (responds to current filter) ----
  const stats = useMemo(() => {
    const open_ = tasks.filter(tk => tk.status !== "done");
    return {
      total: tasks.length,
      open: open_.length,
      in_progress: open_.filter(tk => tk.status === "in_progress").length,
      overdue: open_.filter(isOverdue).length,
      today: tasks.filter(tk => tk.scheduled_for === todayISO()).length,
    };
  }, [tasks]);

  const ProjectChip = ({ pid, size = "xs" }) => {
    if (!pid) return null;
    const p = projectById[pid];
    if (!p) return null;
    return (
      <span className={`inline-flex items-center gap-1 ${size === "xs" ? "text-[10px]" : "text-xs"} text-muted-foreground max-w-[120px]`}>
        <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: p.color || "#FF4500" }} />
        <span className="truncate">{p.name}</span>
      </span>
    );
  };

  return (
    <div className="p-6 lg:p-8 space-y-5" data-testid="tasks-page">
      <div className="flex items-end justify-between flex-wrap gap-4">
        <div>
          <div className="label-mono">{t("التنفيذ", "Execution")}</div>
          <h1 className="text-3xl sm:text-4xl tracking-tight font-medium mt-1">{t("المهام", "Tasks")}</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {projectFilter === "all" ? t("كل مشاريعك في مكان واحد.", "All your projects in one place.") : t("مفلتر على مشروع واحد.", "Filtered to a single project.")}
          </p>
        </div>
        <button data-testid="new-task-btn" onClick={() => { setForm(f => ({ ...f, project_id: projectFilter !== "all" ? projectFilter : "", scheduled_for: view === "today" ? todayISO() : "" })); setOpen(true); }}
          className="px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:opacity-90 flex items-center gap-2">
          <Plus size={14} /> {t("مهمة جديدة", "New task")}
        </button>
      </div>

      {/* Toolbar: view tabs, project filter, search */}
      <div className="border border-border bg-card rounded-md p-2 flex items-center gap-2 flex-wrap" data-testid="tasks-toolbar">
        <div className="flex items-center p-0.5 border border-border rounded-md">
          {[
            { k: "all", icon: LayoutGrid, l: t("الكل", "All") },
            { k: "today", icon: CalendarDays, l: t("اليوم", "Today") },
            { k: "week", icon: CalendarRange, l: t("الأسبوع", "Week") },
          ].map(v => (
            <button key={v.k} onClick={() => setView(v.k)} data-testid={`view-${v.k}`}
              className={`px-2.5 h-8 rounded-sm flex items-center gap-1.5 text-xs transition-colors ${view === v.k ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground"}`}>
              <v.icon size={12} /> {v.l}
            </button>
          ))}
        </div>

        <select
          value={projectFilter}
          onChange={(e) => setProjectFilter(e.target.value)}
          data-testid="project-filter"
          className="h-8 px-2.5 bg-background border border-border rounded-md text-xs focus:outline-none focus:ring-2 focus:ring-primary max-w-[200px]"
        >
          <option value="all">{t("كل المشاريع", "All projects")}</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>

        {/* Day-of-week filter (uses project.weekly_days schedule) */}
        <select
          value={dayFilter}
          onChange={(e) => setDayFilter(e.target.value === "all" ? "all" : parseInt(e.target.value))}
          data-testid="day-filter"
          className="h-8 px-2.5 bg-background border border-border rounded-md text-xs focus:outline-none focus:ring-2 focus:ring-primary"
          title={t("افلتر حسب يوم جدولة المشروع", "Filter by project's scheduled day")}
        >
          <option value="all">{t("كل الأيام", "All days")}</option>
          <option value={6}>{t("السبت", "Saturday")}</option>
          <option value={0}>{t("الأحد", "Sunday")}</option>
          <option value={1}>{t("الإثنين", "Monday")}</option>
          <option value={2}>{t("الثلاثاء", "Tuesday")}</option>
          <option value={3}>{t("الأربعاء", "Wednesday")}</option>
          <option value={4}>{t("الخميس", "Thursday")}</option>
          <option value={5}>{t("الجمعة", "Friday")}</option>
        </select>

        <div className="relative flex-1 min-w-[180px] max-w-md">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t("ابحث في المهام…", "Search tasks…")}
            data-testid="task-search"
            className="w-full h-8 ps-8 pe-2.5 bg-background border border-border rounded-md text-xs focus:outline-none focus:ring-2 focus:ring-primary"
          />
          <Search size={12} className="absolute start-2.5 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
        </div>

        {/* Stats chips */}
        <div className="ms-auto flex items-center gap-3 label-mono text-[10px]">
          <span><b className="text-foreground font-mono">{stats.total}</b> {t("الإجمالي", "total")}</span>
          <span>·</span>
          <span className={stats.in_progress ? "text-primary" : ""}><b className="font-mono">{stats.in_progress}</b> {t("جارٍ", "in progress")}</span>
          <span>·</span>
          <span className={stats.overdue ? "text-red-500" : ""}><b className="font-mono">{stats.overdue}</b> {t("متأخر", "overdue")}</span>
          <span>·</span>
          <span className={stats.today ? "text-primary" : ""}><b className="font-mono">{stats.today}</b> 📌 {t("اليوم", "today")}</span>
        </div>
      </div>

      {/* Today-view hint banner: surface overdue / in-progress that aren't pinned yet */}
      {view === "today" && (todayHints.overdue_unpinned > 0 || todayHints.in_progress_unpinned > 0) && (
        <div className="border border-amber-500/30 bg-amber-500/5 rounded-md px-4 py-2.5 flex items-center justify-between gap-3 flex-wrap" data-testid="today-hints">
          <div className="flex items-center gap-2 text-sm">
            <AlertTriangle size={13} className="text-amber-500 shrink-0" />
            <span>
              {todayHints.overdue_unpinned > 0 && (
                <>
                  <b className="font-mono text-amber-500">{todayHints.overdue_unpinned}</b> {t("مهمة متأخرة", "overdue task(s)")}{todayHints.in_progress_unpinned > 0 ? " · " : " "}
                </>
              )}
              {todayHints.in_progress_unpinned > 0 && (
                <>
                  <b className="font-mono">{todayHints.in_progress_unpinned}</b> {t("جارية", "in progress")}{" "}
                </>
              )}
              {t("غير مثبتة في اليوم.", "not pinned to today.")}
            </span>
          </div>
          <button
            onClick={() => setView("all")}
            data-testid="view-all-from-hint"
            className="text-xs font-mono text-amber-500 hover:underline"
          >
            {t("اعرضها في الكل ←", "View in All →")}
          </button>
        </div>
      )}

      {/* Banner for empty state */}
      {tasks.length === 0 && (
        <div className="border border-dashed border-border bg-card rounded-md p-10 text-center" data-testid="empty-state">
          <div className="label-mono mb-2">{view === "today" ? t("لا توجد مهام لليوم", "No tasks for today") : view === "week" ? t("لا توجد مهام لهذا الأسبوع", "No tasks for this week") : t("لا توجد مهام", "No tasks")}</div>
          <p className="text-sm text-muted-foreground max-w-md mx-auto">
            {view === "today"
              ? t("ثبّت أي مهمة باستخدام أيقونة 📌 من عرض «الكل»، أو أنشئ مهمة جديدة اليوم.", "Pin tasks with the 📌 icon from the All view, or create a new task for today.")
              : t("أنشئ مهمة جديدة وابدأ التنفيذ.", "Create a new task and start executing.")}
          </p>
        </div>
      )}

      {/* Kanban */}
      {tasks.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {COLUMNS.map(col => {
            const items = tasks.filter(tk => tk.status === col.key);
            const isHover = hoverCol === col.key;
            return (
              <div key={col.key}
                onDragOver={(e) => onDragOver(e, col.key)}
                onDragLeave={() => setHoverCol(null)}
                onDrop={(e) => onDrop(e, col.key)}
                className={`border bg-card rounded-md min-h-[300px] transition-colors ${isHover ? "border-primary ring-1 ring-primary/30" : "border-border"}`}
                data-testid={`column-${col.key}`}>
                <div className="hairline px-4 py-2.5 flex items-center justify-between">
                  <div className="label-mono">{col.label}</div>
                  <span className="font-mono text-xs text-muted-foreground">{items.length}</span>
                </div>
                <div className="p-2 space-y-2">
                  {items.map((tk, i) => {
                    const pinned = tk.scheduled_for === todayISO();
                    const overdue = isOverdue(tk);
                    return (
                      <motion.div key={tk.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.02 }}
                        draggable
                        onDragStart={(e) => onDragStart(e, tk.id)}
                        onDragEnd={onDragEnd}
                        onClick={() => setSelected(tk)}
                        className={`p-3 border bg-background rounded-md cursor-grab active:cursor-grabbing hover:border-primary/40 group ${draggingId === tk.id ? "opacity-50" : ""} ${pinned ? "border-primary/60" : "border-border"}`}
                        data-testid={`task-card-${tk.id}`}>
                        <div className="flex items-start gap-2">
                          <div className={`w-1.5 h-1.5 rounded-full mt-1.5 shrink-0 ${PRIO_DOT[tk.priority]}`} />
                          <div className="text-sm flex-1 line-clamp-2">{tk.title}</div>
                          <div onClick={(e) => e.stopPropagation()} className="shrink-0">
                            <ReminderBell entityType="task" entityId={tk.id} compact />
                          </div>
                          <button
                            onClick={(e) => pinToToday(tk, e)}
                            className={`w-6 h-6 rounded-md flex items-center justify-center shrink-0 transition-colors ${pinned ? "text-primary" : "text-muted-foreground/60 hover:text-primary hover:bg-secondary"}`}
                            data-testid={`pin-${tk.id}`}
                            title={pinned ? t("إزالة من اليوم", "Remove from today") : t("ثبّت في اليوم", "Pin to today")}
                          >
                            {pinned ? <Pin size={12} fill="currentColor" /> : <PinOff size={12} />}
                          </button>
                        </div>
                        <div className="mt-2 flex items-center justify-between gap-2">
                          <ProjectChip pid={tk.project_id} />
                          <div className="flex items-center gap-2 label-mono text-[9px] shrink-0">
                            {overdue && (
                              <span className="text-red-500 flex items-center gap-0.5"><AlertTriangle size={9} /> {t("متأخر", "overdue")}</span>
                            )}
                            {(tk.end_date || tk.due_date) && !pinned && (
                              <span>{new Date(tk.end_date || tk.due_date).toLocaleDateString(locale, { month: "short", day: "numeric" })}</span>
                            )}
                            {pinned && <span className="text-primary">📌 {t("اليوم", "Today")}</span>}
                            {tk.estimated_minutes ? <span>{tk.estimated_minutes}{t("د", "m")}</span> : null}
                          </div>
                        </div>
                      </motion.div>
                    );
                  })}
                  {items.length === 0 && <div className="p-4 text-center text-xs text-muted-foreground">{t("أفلت هنا", "Drop here")}</div>}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* New task modal */}
      {open && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setOpen(false)}>
          <form onClick={e => e.stopPropagation()} onSubmit={create}
            className="bg-card border border-border rounded-md p-6 w-full max-w-md space-y-3 max-h-[90vh] overflow-y-auto" data-testid="new-task-form">
            <div className="flex items-center justify-between"><h3 className="text-lg font-medium tracking-tight">{t("مهمة جديدة", "New task")}</h3>
              <button type="button" onClick={() => setOpen(false)} className="w-8 h-8 hover:bg-secondary rounded-md flex items-center justify-center"><X size={15} /></button>
            </div>
            <input data-testid="task-title" required value={form.title} onChange={e => setForm({ ...form, title: e.target.value })}
              placeholder={t("عنوان المهمة", "Task title")} className="w-full px-3 py-2 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary" />
            <textarea value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} rows={2}
              placeholder={t("الوصف", "Description")} className="w-full px-3 py-2 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary" />
            <div className="grid grid-cols-2 gap-2">
              <select value={form.priority} onChange={e => setForm({ ...form, priority: e.target.value })} className="px-3 py-2 bg-background border border-border rounded-md text-sm">
                {PRIORITIES.map(p => <option key={p.v} value={p.v}>{p.l}</option>)}
              </select>
              <select value={form.complexity} onChange={e => setForm({ ...form, complexity: e.target.value })} className="px-3 py-2 bg-background border border-border rounded-md text-sm">
                {COMPLEXITY.map(p => <option key={p.v} value={p.v}>{p.l}</option>)}
              </select>
            </div>
            <select value={form.project_id} onChange={e => setForm({ ...form, project_id: e.target.value })} data-testid="task-project"
              className="w-full px-3 py-2 bg-background border border-border rounded-md text-sm">
              <option value="">{t("بدون مشروع", "No project")}</option>
              {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="label-mono mb-1.5 block">{t("الوقت المقدّر (دقيقة)", "Estimated (minutes)")}</label>
                <input type="number" value={form.estimated_minutes} onChange={e => setForm({ ...form, estimated_minutes: parseInt(e.target.value) || 0 })}
                  className="w-full px-3 py-2 bg-background border border-border rounded-md text-sm" />
              </div>
              <div>
                <label className="label-mono mb-1.5 block flex items-center gap-1">📌 {t("ثبّت في", "Pin to")}</label>
                <select value={form.scheduled_for} onChange={(e) => setForm({ ...form, scheduled_for: e.target.value })}
                  data-testid="task-pin-select"
                  className="w-full px-3 py-2 bg-background border border-border rounded-md text-sm">
                  <option value="">{t("بدون", "None")}</option>
                  <option value={todayISO()}>{t("اليوم", "Today")}</option>
                  <option value={new Date(Date.now() + 86400000).toISOString().slice(0, 10)}>{t("غدًا", "Tomorrow")}</option>
                </select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <DateTimeField label={t("البداية", "Start")} value={form.start_date} onChange={(v) => setForm({ ...form, start_date: v })} testId="task-start" />
              <DateTimeField label={t("النهاية / الاستحقاق", "End / Due")} value={form.end_date} onChange={(v) => setForm({ ...form, end_date: v })} testId="task-end" min={form.start_date} />
            </div>
            <button data-testid="task-submit" type="submit" className="w-full bg-primary text-primary-foreground py-2.5 rounded-md font-medium text-sm hover:opacity-90">{t("أنشئ", "Create")}</button>
          </form>
        </div>
      )}

      {/* Selected task detail modal */}
      {selected && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setSelected(null)}>
          <div onClick={e => e.stopPropagation()} className="bg-card border border-border rounded-md p-6 w-full max-w-xl space-y-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-start justify-between">
              <div className="min-w-0">
                <div className="label-mono flex items-center gap-2 flex-wrap">
                  <span>{COLUMNS.find(c => c.key === selected.status)?.label}</span>
                  <span>·</span>
                  <span>{PRIORITIES.find(p => p.v === selected.priority)?.l}</span>
                  {selected.project_id && (<><span>·</span><ProjectChip pid={selected.project_id} size="sm" /></>)}
                  {selected.scheduled_for === todayISO() && <><span>·</span><span className="text-primary">📌 {t("اليوم", "Today")}</span></>}
                </div>
                <h3 className="text-xl tracking-tight font-medium mt-1">{selected.title}</h3>
              </div>
              <div className="flex gap-1 shrink-0">
                <button onClick={(e) => pinToToday(selected, e)} data-testid="detail-pin"
                  className={`px-3 py-1.5 border rounded-md text-xs font-medium flex items-center gap-1 ${selected.scheduled_for === todayISO() ? "border-primary text-primary" : "border-border text-muted-foreground hover:text-primary"}`}>
                  {selected.scheduled_for === todayISO() ? <Pin size={12} fill="currentColor" /> : <PinOff size={12} />}
                  {selected.scheduled_for === todayISO() ? t("في اليوم", "In today") : t("ثبّت", "Pin")}
                </button>
                <button onClick={() => breakdown(selected.id)} className="px-3 py-1.5 bg-primary text-primary-foreground rounded-md text-xs font-medium flex items-center gap-1"><Sparkles size={12}/> {t("تجزئة ذكية", "AI breakdown")}</button>
                <button onClick={() => remove(selected.id)} className="w-9 h-9 hover:bg-destructive/10 text-destructive rounded-md flex items-center justify-center"><Trash2 size={14} /></button>
                <button onClick={() => setSelected(null)} className="w-9 h-9 hover:bg-secondary rounded-md flex items-center justify-center"><X size={15} /></button>
              </div>
            </div>
            {selected.description && <div className="text-sm text-muted-foreground whitespace-pre-wrap">{selected.description}</div>}

            <div className="grid grid-cols-3 gap-px bg-border">
              {[
                { l: t("التعقيد", "Complexity"), v: COMPLEXITY.find(c => c.v === selected.complexity)?.l || selected.complexity },
                { l: t("المقدّر", "Estimated"), v: `${selected.estimated_minutes || 0} ${t("د", "min")}` },
                { l: t("الفعلي", "Actual"), v: `${selected.actual_minutes || 0} ${t("د", "min")}` },
              ].map(s => <div key={s.l} className="bg-card p-3"><div className="label-mono text-[9px]">{s.l}</div><div className="text-sm mt-1">{s.v}</div></div>)}
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="label-mono mb-1.5 block">{t("المشروع", "Project")}</label>
                <select value={selected.project_id || ""} onChange={(e) => update(selected.id, { project_id: e.target.value || null })}
                  className="w-full px-3 py-2 bg-background border border-border rounded-md text-sm">
                  <option value="">{t("بدون مشروع", "No project")}</option>
                  {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
              </div>
              <div>
                <label className="label-mono mb-1.5 block">📌 {t("اليوم المخطط له", "Planned day")}</label>
                <select value={selected.scheduled_for || ""} onChange={(e) => update(selected.id, { scheduled_for: e.target.value || null })}
                  className="w-full px-3 py-2 bg-background border border-border rounded-md text-sm">
                  <option value="">{t("بدون", "None")}</option>
                  <option value={todayISO()}>{t("اليوم", "Today")}</option>
                  <option value={new Date(Date.now() + 86400000).toISOString().slice(0, 10)}>{t("غدًا", "Tomorrow")}</option>
                </select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="label-mono mb-1.5 block">{t("المُكلَّف", "Assignee")}</label>
                <select
                  data-testid="detail-assignee"
                  value={selected.assignee_id || ""}
                  onChange={(e) => update(selected.id, { assignee_id: e.target.value || null })}
                  className="w-full px-3 py-2 bg-background border border-border rounded-md text-sm"
                >
                  <option value="">{t("بدون", "Unassigned")}</option>
                  {teammates.map(u => <option key={u.id} value={u.id}>{u.name} ({u.email})</option>)}
                </select>
              </div>
              <div className="flex items-end">
                <ReminderBell entityType="task" entityId={selected.id} size={14} />
                <span className="label-mono text-[10px] ms-2 text-muted-foreground">{t("التذكيرات", "Reminders")}</span>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <DateTimeField label={t("تاريخ البداية", "Start date")} value={selected.start_date} onChange={(v) => update(selected.id, { start_date: v || null })} testId="detail-start" />
              <DateTimeField label={t("تاريخ النهاية", "End date")} value={selected.end_date} onChange={(v) => update(selected.id, { end_date: v || null, due_date: v || null })} testId="detail-end" min={selected.start_date} />
            </div>

            {selected.subtasks?.length > 0 && (
              <div>
                <div className="label-mono mb-2">{t("المهام الفرعية", "Subtasks")}</div>
                <div className="space-y-1">
                  {selected.subtasks.map(s => (
                    <div key={s.id} className="px-3 py-2 border border-border rounded-md text-sm flex items-center gap-2">
                      <input type="checkbox" defaultChecked={s.done} />
                      <span className="flex-1">{s.title}</span>
                      <span className="label-mono text-[9px]">{s.estimated_minutes} {t("د", "min")}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Progress updates log */}
            <div data-testid="task-updates-section">
              <div className="label-mono mb-2 flex items-center gap-2"><MessageSquare size={11} /> {t("التحديثات", "Updates")} <span className="text-muted-foreground">· {updates.length}</span></div>
              <form onSubmit={postUpdate} className="flex gap-2 mb-3">
                <input
                  value={newUpdate}
                  onChange={(e) => setNewUpdate(e.target.value)}
                  placeholder={t("سويت ايش اليوم على هذه المهمة؟", "What did you do on this task?")}
                  data-testid="task-update-input"
                  className="flex-1 px-3 py-2 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                />
                <button
                  type="submit"
                  disabled={!newUpdate.trim()}
                  data-testid="task-update-submit"
                  className="px-3 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:opacity-90 disabled:opacity-40 flex items-center gap-1"
                >
                  <Send size={12} className="rtl:rotate-180" /> {t("أضف", "Add")}
                </button>
              </form>
              <div className="space-y-2 max-h-60 overflow-y-auto">
                {updates.length === 0 ? (
                  <div className="text-xs text-muted-foreground px-1 py-2">{t("لا توجد تحديثات بعد. سجّل تقدّمك حتى لو المهمة ما خلصت.", "No updates yet. Log your progress even if the task isn't finished.")}</div>
                ) : updates.map(u => (
                  <div key={u.id} className="border-s-2 border-primary/40 bg-background/50 ps-3 pe-2 py-2 rounded-e-md flex items-start justify-between gap-2 group">
                    <div className="min-w-0 flex-1">
                      <div className="text-sm whitespace-pre-wrap leading-relaxed">{u.content}</div>
                      <div className="label-mono text-[9px] mt-1">{new Date(u.created_at).toLocaleString(locale)}</div>
                    </div>
                    <button
                      onClick={() => removeUpdate(u.id)}
                      className="opacity-0 group-hover:opacity-100 w-6 h-6 hover:bg-destructive/10 text-muted-foreground hover:text-destructive rounded-md flex items-center justify-center shrink-0"
                      title={t("احذف", "Delete")}
                    >
                      <Trash2 size={11} />
                    </button>
                  </div>
                ))}
              </div>
            </div>

            <div className="flex gap-2">
              <select value={selected.status} onChange={e => update(selected.id, { status: e.target.value })}
                className="flex-1 px-3 py-2 bg-background border border-border rounded-md text-sm">
                {COLUMNS.map(c => <option key={c.key} value={c.key}>{c.label}</option>)}
              </select>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
