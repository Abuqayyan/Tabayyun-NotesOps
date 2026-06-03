import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useLang } from "@/contexts/LanguageContext";
import { motion } from "framer-motion";
import { Target, ArrowLeft, Pause, Zap, Timer, Sparkles, Loader2 } from "lucide-react";
import { toast } from "sonner";

const PRIO_DOT = {
  critical: "bg-red-500",
  high: "bg-amber-500",
  medium: "bg-muted-foreground",
  low: "bg-emerald-500",
};

function MiniTask({ task, accent = false }) {
  if (!task) return <div className="text-xs text-muted-foreground">—</div>;
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2">
        <div className={`w-1.5 h-1.5 rounded-full ${PRIO_DOT[task.priority]}`} />
        <span className={`text-sm ${accent ? "font-medium" : ""} line-clamp-1`}>{task.title}</span>
      </div>
      {task.project_name && <div className="label-mono text-[9px]">{task.project_name}</div>}
    </div>
  );
}

export default function DailyExecutionBrief() {
  const { lang, t } = useLang();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = async (silent = false) => {
    if (!silent) setLoading(true);
    else setRefreshing(true);
    try {
      const r = await api.get("/ai/daily-brief");
      setData(r.data);
    } catch { toast.error(t("فشل توليد الملخص", "Failed to generate brief")); }
    finally { setLoading(false); setRefreshing(false); }
  };

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [lang]);

  if (loading) {
    return (
      <div className="border border-border bg-card rounded-md p-8 text-center">
        <Loader2 className="mx-auto animate-spin text-muted-foreground mb-2" size={20} />
        <div className="label-mono">{t("رئيس العمليات يراجع مساحة عملك", "AI Chief of Operations is reviewing your workspace")}</div>
      </div>
    );
  }
  if (!data) return null;

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
      className="border border-primary/40 bg-card rounded-md overflow-hidden" data-testid="daily-brief">
      <div className="hairline px-5 py-3 flex items-center justify-between bg-primary/5">
        <div className="flex items-center gap-2">
          <Sparkles size={13} className="text-primary" />
          <div className="label-mono">{t("الملخص اليومي للتنفيذ", "Daily execution brief")}</div>
        </div>
        <button onClick={() => load(true)} disabled={refreshing}
          className="label-mono text-[10px] text-muted-foreground hover:text-foreground flex items-center gap-1">
          {refreshing ? <Loader2 size={10} className="animate-spin" /> : "↻"} {t("إعادة توليد", "Regenerate")}
        </button>
      </div>

      {data.summary && (
        <div className="px-5 py-4 border-b border-border">
          <p className="text-sm leading-relaxed whitespace-pre-wrap">{data.summary}</p>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-px bg-border">
        <div className="bg-card p-4">
          <div className="label-mono flex items-center gap-1.5"><Target size={10} className="text-primary"/> {t("التركيز الحالي", "Current focus")}</div>
          <div className="mt-2"><MiniTask task={data.current_focus} accent /></div>
        </div>
        <div className="bg-card p-4">
          <div className="label-mono flex items-center gap-1.5"><ArrowLeft size={10} className="text-primary rtl:rotate-180"/> {t("الإجراء التالي", "Next action")}</div>
          <div className="mt-2"><MiniTask task={data.next_action} /></div>
        </div>
        <div className="bg-card p-4">
          <div className="label-mono flex items-center gap-1.5"><Zap size={10} className="text-primary"/> {t("عالي الأثر", "High leverage")}</div>
          <div className="mt-2 space-y-2">
            {data.high_leverage?.length ? data.high_leverage.map(tk => <MiniTask key={tk.id} task={tk} />) : <div className="text-xs text-muted-foreground">—</div>}
          </div>
        </div>
        <div className="bg-card p-4">
          <div className="label-mono flex items-center gap-1.5"><Pause size={10} className="text-amber-500"/> {t("معلّقة", "Blocked")}</div>
          <div className="mt-2 space-y-2">
            {data.blocked?.length ? data.blocked.map(tk => <MiniTask key={tk.id} task={tk} />) : <div className="text-xs text-muted-foreground">{t("لا شيء", "None")}</div>}
          </div>
        </div>
        <div className="bg-card p-4">
          <div className="label-mono flex items-center gap-1.5"><Timer size={10} className="text-primary"/> {t("عمل عميق", "Deep work")}</div>
          <div className="mt-2"><MiniTask task={data.recommended_deep_work} /></div>
          {data.recommended_deep_work && (
            <a href="/focus" className="label-mono text-[9px] text-primary hover:underline mt-2 inline-block">{t("ابدأ الجلسة ←", "Start session →")}</a>
          )}
        </div>
      </div>
    </motion.div>
  );
}
