import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useLang } from "@/contexts/LanguageContext";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  TrendingUp, Flame, Zap, AlertTriangle, Clock, CheckCircle2,
  Target, ArrowUpRight, FolderGit2, Pause, Share2
} from "lucide-react";
import DailyExecutionBrief from "@/components/DailyExecutionBrief";
import ShareBriefingModal from "@/components/ShareBriefingModal";
import GreetingCard from "@/components/GreetingCard";

const RISK_COLOR = { low: "text-emerald-500", medium: "text-amber-500", high: "text-red-500" };

function Stat({ label, value, sub, icon: Icon, tid }) {
  return (
    <div className="p-5 border border-border bg-card rounded-md hover:border-primary/40 transition-colors" data-testid={tid}>
      <div className="flex items-start justify-between">
        <div className="label-mono">{label}</div>
        {Icon && <Icon size={14} className="text-muted-foreground" />}
      </div>
      <div className="data-number text-3xl mt-3">{value}</div>
      {sub && <div className="text-xs text-muted-foreground mt-1">{sub}</div>}
    </div>
  );
}

function ScoreBar({ value, color = "bg-primary" }) {
  return (
    <div className="w-full h-1.5 bg-secondary rounded-full overflow-hidden">
      <motion.div initial={{ width: 0 }} animate={{ width: `${value}%` }} transition={{ duration: 0.6 }}
        className={`h-full ${color}`} />
    </div>
  );
}

export default function Dashboard() {
  const { lang, t } = useLang();
  const [data, setData] = useState(null);
  const [prio, setPrio] = useState(null);
  const [prioLoading, setPrioLoading] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);

  const reload = () => api.get("/dashboard/summary").then((r) => setData(r.data)).catch(() => {});
  useEffect(() => {
    reload();
    const handler = () => reload();
    window.addEventListener("opscore:task", handler);
    return () => window.removeEventListener("opscore:task", handler);
  }, []);

  const runPriority = async () => {
    setPrioLoading(true);
    try {
      const r = await api.get("/ai/prioritize");
      setPrio(r.data);
    } finally { setPrioLoading(false); }
  };

  const RISK_LABEL = { low: t("منخفض", "Low"), medium: t("متوسط", "Medium"), high: t("مرتفع", "High") };
  const locale = lang === "ar" ? "ar-EG" : "en-US";

  if (!data) {
    return <div className="p-8"><div className="label-mono animate-pulse">{t("جارٍ مزامنة مساحة العمل…", "Syncing workspace…")}</div></div>;
  }

  return (
    <div className="p-6 lg:p-8 space-y-6" data-testid="dashboard-page">
      <GreetingCard />
      <div className="flex items-end justify-between flex-wrap gap-4">
        <div>
          <div className="label-mono">{t("نظرة عامة", "Overview")}</div>
          <h1 className="text-3xl sm:text-4xl tracking-tight font-medium mt-1">{t("اليوم", "Today")}</h1>
          <p className="text-sm text-muted-foreground mt-1">{t("رئيس عملياتك الذكي راجَع مساحة عملك.", "Your AI Chief of Operations has reviewed your workspace.")}</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setShareOpen(true)} data-testid="share-brief-btn"
            className="px-3 py-2 border border-border rounded-md text-sm font-medium hover:bg-secondary flex items-center gap-2">
            <Share2 size={13} /> {t("شارك الملخص", "Share briefing")}
          </button>
          <button onClick={runPriority} disabled={prioLoading}
            className="px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:opacity-90 disabled:opacity-50 flex items-center gap-2"
            data-testid="ai-prioritize-btn">
            <Zap size={14} /> {prioLoading ? t("جارٍ التحليل…", "Analyzing…") : t("ترتيب ذكي", "Smart prioritize")}
          </button>
        </div>
      </div>

      <DailyExecutionBrief />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Stat label={t("المشاريع النشطة", "Active projects")} value={data.projects_active} sub={`${data.projects_total} ${t("مجموع", "total")}`} icon={FolderGit2} tid="stat-projects" />
        <Stat label={t("الإنجاز", "Completion")} value={`${data.completion_rate}%`} sub={`${data.tasks_done}/${data.tasks_total} ${t("مهمة", "tasks")}`} icon={CheckCircle2} tid="stat-completion" />
        <Stat label={t("المتأخرة", "Overdue")} value={data.tasks_delayed} sub={t("تحتاج انتباه", "Needs attention")} icon={AlertTriangle} tid="stat-delayed" />
        <Stat label={t("معلّقة", "Blocked")} value={data.tasks_blocked} sub={t("أزل العوائق", "Clear blockers")} icon={Pause} tid="stat-blocked" />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="p-5 border border-border bg-card rounded-md" data-testid="card-focus">
          <div className="flex items-center justify-between">
            <div className="label-mono">{t("درجة التركيز", "Focus score")}</div>
            <Target size={14} className="text-primary" />
          </div>
          <div className="flex items-baseline gap-2 mt-3">
            <span className="data-number text-4xl">{data.focus_score}</span>
            <span className="text-xs text-muted-foreground">{t("/١٠٠", "/100")}</span>
          </div>
          <div className="mt-3"><ScoreBar value={data.focus_score} /></div>
          <div className="text-xs text-muted-foreground mt-2">{data.weekly_focus_minutes} {t("دقيقة تركيز هذا الأسبوع", "focus minutes this week")}</div>
        </div>

        <div className="p-5 border border-border bg-card rounded-md" data-testid="card-execution">
          <div className="flex items-center justify-between">
            <div className="label-mono">{t("التنفيذ الأسبوعي", "Weekly execution")}</div>
            <TrendingUp size={14} className="text-primary" />
          </div>
          <div className="flex items-baseline gap-2 mt-3">
            <span className="data-number text-4xl">{data.execution_score}</span>
            <span className="text-xs text-muted-foreground">{t("/١٠٠", "/100")}</span>
          </div>
          <div className="mt-3"><ScoreBar value={data.execution_score} /></div>
          <div className="text-xs text-muted-foreground mt-2">{data.weekly_completed} {t("مهمة مكتملة", "tasks completed")}</div>
        </div>

        <div className="p-5 border border-border bg-card rounded-md" data-testid="card-burnout">
          <div className="flex items-center justify-between">
            <div className="label-mono">{t("خطر الإرهاق", "Burnout risk")}</div>
            <Flame size={14} className={RISK_COLOR[data.burnout_risk]} />
          </div>
          <div className="flex items-baseline gap-2 mt-3">
            <span className={`data-number text-2xl ${RISK_COLOR[data.burnout_risk]}`}>
              {RISK_LABEL[data.burnout_risk]}
            </span>
          </div>
          <div className="mt-3"><ScoreBar value={data.burnout_risk === "high" ? 90 : data.burnout_risk === "medium" ? 55 : 20}
            color={data.burnout_risk === "high" ? "bg-red-500" : data.burnout_risk === "medium" ? "bg-amber-500" : "bg-emerald-500"} /></div>
          <div className="text-xs text-muted-foreground mt-2">{data.workload_load} {t("عنصر نشط", "active items")}</div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 border border-border bg-card rounded-md">
          <div className="hairline px-5 py-3 flex items-center justify-between">
            <div className="label-mono">{t("المواعيد القادمة", "Upcoming deadlines")}</div>
            <Link to="/tasks" className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1">
              {t("كل المهام", "All tasks")} <ArrowUpRight size={11} />
            </Link>
          </div>
          <div className="divide-y divide-border">
            {data.upcoming_deadlines.length === 0 && (
              <div className="p-8 text-center text-sm text-muted-foreground">{t("لا توجد مواعيد خلال الأيام السبعة القادمة.", "No deadlines in the next 7 days.")}</div>
            )}
            {data.upcoming_deadlines.map((t2) => (
              <div key={t2.id} className="px-5 py-3 flex items-center justify-between hover:bg-secondary/50">
                <div className="flex items-center gap-3 min-w-0">
                  <div className={`w-1.5 h-1.5 rounded-full ${
                    t2.priority === "critical" ? "bg-red-500" :
                    t2.priority === "high" ? "bg-amber-500" : "bg-muted-foreground"
                  }`} />
                  <span className="text-sm truncate">{t2.title}</span>
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  <span className="label-mono text-[10px]">{t2.status}</span>
                  <Clock size={12} className="text-muted-foreground" />
                  <span className="font-mono text-xs">{new Date(t2.due_date).toLocaleDateString(locale)}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="border border-border bg-card rounded-md">
          <div className="hairline px-5 py-3 flex items-center justify-between">
            <div className="label-mono">{t("المشاريع النشطة", "Active projects")}</div>
            <Link to="/projects" className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1">
              {t("الكل", "All")} <ArrowUpRight size={11} />
            </Link>
          </div>
          <div className="divide-y divide-border">
            {data.projects.length === 0 && (
              <div className="p-8 text-center text-sm text-muted-foreground">{t("لا توجد مشاريع.", "No projects.")} <Link to="/projects" className="text-primary hover:underline">{t("أنشئ مشروعًا", "Create one")}</Link>.</div>
            )}
            {data.projects.map((p) => (
              <Link to={`/projects/${p.id}`} key={p.id} className="block px-5 py-3 hover:bg-secondary/50">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 min-w-0">
                    <div className="w-2 h-2 rounded-full" style={{ backgroundColor: p.color || "#FF4500" }} />
                    <span className="text-sm font-medium truncate">{p.name}</span>
                  </div>
                  <span className="font-mono text-xs text-muted-foreground">{p.progress || 0}%</span>
                </div>
                <div className="mt-2"><ScoreBar value={p.progress || 0} /></div>
              </Link>
            ))}
          </div>
        </div>
      </div>

      {prio && (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="border border-primary/40 bg-card rounded-md">
          <div className="hairline px-5 py-3 flex items-center gap-2">
            <Zap size={14} className="text-primary" />
            <div className="label-mono">{t("محرّك الأولوية الذكي", "Priority engine")}</div>
          </div>
          <div className="p-5 space-y-3">
            {prio.insights?.length > 0 && (
              <div className="text-sm text-muted-foreground space-y-1">
                {prio.insights.map((i, k) => <div key={k}>· {i}</div>)}
              </div>
            )}
            <div className="space-y-2">
              {prio.ranked?.slice(0, 6).map((r, k) => (
                <div key={r.id || k} className="flex items-center gap-3 p-2 border border-border rounded-md">
                  <span className="font-mono text-xs text-primary w-10">#{k + 1}</span>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium truncate">{r.title}</div>
                    <div className="text-xs text-muted-foreground truncate">{r.reason}</div>
                  </div>
                  <span className="font-mono text-xs">{r.score}</span>
                </div>
              ))}
            </div>
          </div>
        </motion.div>
      )}

      {data.blocked_tasks.length > 0 && (
        <div className="border border-border bg-card rounded-md">
          <div className="hairline px-5 py-3 flex items-center gap-2">
            <Pause size={14} className="text-amber-500" />
            <div className="label-mono">{t("المهام المعلّقة", "Blocked tasks")}</div>
          </div>
          <div className="divide-y divide-border">
            {data.blocked_tasks.map((t2) => (
              <div key={t2.id} className="px-5 py-3 flex items-center justify-between">
                <span className="text-sm">{t2.title}</span>
                <span className="label-mono text-[10px]">{t2.priority}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <ShareBriefingModal open={shareOpen} onClose={() => setShareOpen(false)} />
    </div>
  );
}
