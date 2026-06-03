import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useLang } from "@/contexts/LanguageContext";
import { Link } from "react-router-dom";
import { Plus, FolderGit2, X, LayoutGrid, GanttChartSquare } from "lucide-react";
import { toast } from "sonner";
import { motion } from "framer-motion";
import DateTimeField from "@/components/DateTimeField";
import Timeline from "@/components/Timeline";

const COLORS = ["#FF4500", "#06B6D4", "#10B981", "#F59E0B", "#A855F7", "#EC4899"];

export default function Projects() {
  const { lang, t } = useLang();
  const [projects, setProjects] = useState([]);
  const [open, setOpen] = useState(false);
  const [view, setView] = useState(() => localStorage.getItem("opscore_projects_view") || "grid");
  const [form, setForm] = useState({ name: "", description: "", priority: "medium", color: "#FF4500", status: "active", start_date: "", end_date: "" });

  const PRIORITIES = [
    { v: "low", l: t("منخفض", "Low") },
    { v: "medium", l: t("متوسط", "Medium") },
    { v: "high", l: t("عالٍ", "High") },
    { v: "critical", l: t("حرج", "Critical") },
  ];
  const STATUSES = [
    { v: "active", l: t("نشط", "Active") },
    { v: "paused", l: t("متوقّف", "Paused") },
    { v: "completed", l: t("مكتمل", "Completed") },
    { v: "archived", l: t("مؤرشف", "Archived") },
  ];

  const load = () => api.get("/projects").then((r) => setProjects(r.data)).catch(() => {});
  useEffect(() => { load(); }, []);
  useEffect(() => { localStorage.setItem("opscore_projects_view", view); }, [view]);

  const create = async (e) => {
    e.preventDefault();
    try {
      await api.post("/projects", { ...form, start_date: form.start_date || null, end_date: form.end_date || null });
      toast.success(t("تم إنشاء المشروع", "Project created"));
      setOpen(false); setForm({ name: "", description: "", priority: "medium", color: "#FF4500", status: "active", start_date: "", end_date: "" });
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || t("فشل", "Failed"));
    }
  };

  const locale = lang === "ar" ? "ar-EG" : "en-US";

  return (
    <div className="p-6 lg:p-8 space-y-6" data-testid="projects-page">
      <div className="flex items-end justify-between flex-wrap gap-4">
        <div>
          <div className="label-mono">{t("المساحة", "Workspace")}</div>
          <h1 className="text-3xl sm:text-4xl tracking-tight font-medium mt-1">{t("المشاريع", "Projects")}</h1>
          <p className="text-sm text-muted-foreground mt-1">{projects.length} {t("مجموع", "total")} · {projects.filter(p => p.status === "active").length} {t("نشط", "active")}</p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center p-0.5 border border-border rounded-md">
            <button onClick={() => setView("grid")} data-testid="view-grid"
              className={`px-2.5 h-8 rounded-sm flex items-center gap-1.5 text-xs transition-colors ${view === "grid" ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground"}`}>
              <LayoutGrid size={12} /> {t("شبكة", "Grid")}
            </button>
            <button onClick={() => setView("timeline")} data-testid="view-timeline"
              className={`px-2.5 h-8 rounded-sm flex items-center gap-1.5 text-xs transition-colors ${view === "timeline" ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground"}`}>
              <GanttChartSquare size={12} /> {t("الجدول الزمني", "Timeline")}
            </button>
          </div>
          <button data-testid="new-project-btn" onClick={() => setOpen(true)}
            className="px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:opacity-90 flex items-center gap-2">
            <Plus size={14} /> {t("مشروع جديد", "New project")}
          </button>
        </div>
      </div>

      {view === "timeline" ? <Timeline /> : projects.length === 0 ? (
        <div className="border border-dashed border-border rounded-md py-20 text-center">
          <FolderGit2 className="mx-auto text-muted-foreground mb-4" size={32} />
          <div className="label-mono">{t("لا توجد مشاريع", "No projects yet")}</div>
          <p className="text-sm text-muted-foreground mt-2 max-w-sm mx-auto">{t("أنشئ مشروعك الأول. المهام، الملاحظات، الملخصات الذكية، وتتبع التقدم ترتبط تلقائيًا.", "Create your first project. Tasks, notes, AI summaries, and progress tracking connect automatically.")}</p>
          <button onClick={() => setOpen(true)} className="mt-6 px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium">{t("أنشئ مشروعًا", "Create a project")}</button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {projects.map((p, i) => (
            <motion.div key={p.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }}>
              <Link to={`/projects/${p.id}`} data-testid={`project-card-${p.id}`}
                className="block p-5 border border-border bg-card rounded-md hover:border-primary/40 transition-colors group">
                <div className="flex items-center justify-between">
                  <div className="w-2 h-2 rounded-full" style={{ backgroundColor: p.color || "#FF4500" }} />
                  <span className="label-mono text-[10px]">{STATUSES.find(s => s.v === p.status)?.l || p.status}</span>
                </div>
                <div className="mt-4 font-medium tracking-tight text-lg">{p.name}</div>
                <p className="text-sm text-muted-foreground mt-1 line-clamp-2 min-h-[2.5rem]">{p.description || t("بدون وصف.", "No description.")}</p>
                <div className="mt-4 flex items-center justify-between text-xs text-muted-foreground">
                  <span className="font-mono">{p.task_count || 0} {t("مهمة", "tasks")}</span>
                  <span className="font-mono">{p.progress || 0}%</span>
                </div>
                {(p.start_date || p.end_date) && (
                  <div className="mt-2 label-mono text-[9px] flex items-center justify-between">
                    <span>{p.start_date ? new Date(p.start_date).toLocaleDateString(locale) : "—"}</span>
                    <span>→</span>
                    <span>{p.end_date ? new Date(p.end_date).toLocaleDateString(locale) : "—"}</span>
                  </div>
                )}
                <div className="mt-2 h-1 bg-secondary rounded-full overflow-hidden">
                  <div className="h-full bg-primary" style={{ width: `${p.progress || 0}%` }} />
                </div>
              </Link>
            </motion.div>
          ))}
        </div>
      )}

      {open && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setOpen(false)}>
          <form onClick={(e) => e.stopPropagation()} onSubmit={create}
            className="bg-card border border-border rounded-md p-6 w-full max-w-md space-y-4" data-testid="new-project-form">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-medium tracking-tight">{t("مشروع جديد", "New project")}</h3>
              <button type="button" onClick={() => setOpen(false)} className="w-8 h-8 flex items-center justify-center hover:bg-secondary rounded-md"><X size={15} /></button>
            </div>
            <div>
              <label className="label-mono mb-1.5 block">{t("الاسم", "Name")}</label>
              <input data-testid="proj-name" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="w-full px-3 py-2 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary" />
            </div>
            <div>
              <label className="label-mono mb-1.5 block">{t("الوصف", "Description")}</label>
              <textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })}
                rows={3} className="w-full px-3 py-2 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="label-mono mb-1.5 block">{t("الأولوية", "Priority")}</label>
                <select value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}
                  className="w-full px-3 py-2 bg-background border border-border rounded-md text-sm">
                  {PRIORITIES.map(p => <option key={p.v} value={p.v}>{p.l}</option>)}
                </select>
              </div>
              <div>
                <label className="label-mono mb-1.5 block">{t("الحالة", "Status")}</label>
                <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}
                  className="w-full px-3 py-2 bg-background border border-border rounded-md text-sm">
                  {STATUSES.map(s => <option key={s.v} value={s.v}>{s.l}</option>)}
                </select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <DateTimeField label={t("تاريخ البداية", "Start date")} value={form.start_date} onChange={(v) => setForm({ ...form, start_date: v })} testId="proj-start" />
              <DateTimeField label={t("تاريخ النهاية", "End date")} value={form.end_date} onChange={(v) => setForm({ ...form, end_date: v })} testId="proj-end" min={form.start_date} />
            </div>
            <div>
              <label className="label-mono mb-1.5 block">{t("اللون", "Color")}</label>
              <div className="flex gap-2">
                {COLORS.map(c => (
                  <button type="button" key={c} onClick={() => setForm({ ...form, color: c })}
                    className={`w-7 h-7 rounded-full ${form.color === c ? "ring-2 ring-offset-2 ring-foreground ring-offset-card" : ""}`}
                    style={{ backgroundColor: c }} />
                ))}
              </div>
            </div>
            <button data-testid="proj-submit" type="submit" className="w-full bg-primary text-primary-foreground py-2.5 rounded-md font-medium text-sm hover:opacity-90">{t("أنشئ", "Create")}</button>
          </form>
        </div>
      )}
    </div>
  );
}
