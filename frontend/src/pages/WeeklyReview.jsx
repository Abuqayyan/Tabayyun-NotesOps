import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useLang } from "@/contexts/LanguageContext";
import { Loader2, Sparkles, TrendingUp, TrendingDown, AlertTriangle, Target, Lightbulb } from "lucide-react";
import { toast } from "sonner";

function Section({ title, icon: Icon, items, tone = "default", emptyLabel }) {
  const toneClass = tone === "wins" ? "text-emerald-500" : tone === "misses" ? "text-amber-500" : tone === "risks" ? "text-destructive" : "text-primary";
  return (
    <div className="border border-border bg-card rounded-md">
      <div className="hairline px-5 py-3 flex items-center gap-2">
        <Icon size={13} className={toneClass} />
        <div className="label-mono">{title}</div>
      </div>
      <div className="p-5 space-y-2">
        {items?.length ? items.map((s, i) => (
          <div key={i} className="text-sm leading-relaxed flex gap-2">
            <span className="text-muted-foreground font-mono text-xs mt-1">{String(i + 1).padStart(2, "0")}</span>
            <span>{s}</span>
          </div>
        )) : <div className="text-sm text-muted-foreground">{emptyLabel}</div>}
      </div>
    </div>
  );
}

export default function WeeklyReview() {
  const { lang, t } = useLang();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const generate = async () => {
    setLoading(true);
    try {
      const r = await api.get("/ai/weekly-review");
      setData(r.data);
    } catch { toast.error(t("فشل التوليد", "Generation failed")); } finally { setLoading(false); }
  };

  useEffect(() => { generate(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [lang]);

  const empty = t("لا توجد عناصر.", "No items.");

  return (
    <div className="p-6 lg:p-8 space-y-6 max-w-5xl" data-testid="weekly-review-page">
      <div className="flex items-end justify-between flex-wrap gap-4">
        <div>
          <div className="label-mono">{t("مراجعة", "Review")}</div>
          <h1 className="text-3xl sm:text-4xl tracking-tight font-medium mt-1">{t("المراجعة الأسبوعية", "Weekly Review")}</h1>
          <p className="text-sm text-muted-foreground mt-1">{t("ملخصك التنفيذي للأيام السبعة الماضية، مولّد بالذكاء.", "Your executive summary for the past 7 days, AI-generated.")}</p>
        </div>
        <button onClick={generate} disabled={loading}
          className="px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:opacity-90 disabled:opacity-50 flex items-center gap-2">
          {loading ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />} {t("إعادة توليد", "Regenerate")}
        </button>
      </div>

      {loading && !data ? (
        <div className="border border-border bg-card rounded-md p-16 text-center">
          <Loader2 className="mx-auto animate-spin text-muted-foreground mb-3" size={24} />
          <div className="label-mono">{t("كلود يراجع الأسبوع", "Claude is reviewing your week")}</div>
        </div>
      ) : data ? (
        <>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-px bg-border">
            {[
              { l: t("مكتملة", "Completed"), v: data.stats?.completed_count },
              { l: t("متأخرة", "Delayed"), v: data.stats?.delayed_count },
              { l: t("دقائق تركيز", "Focus minutes"), v: data.stats?.focus_minutes },
              { l: t("جلسات", "Sessions"), v: data.stats?.focus_sessions },
              { l: t("معلّقة", "Blocked"), v: data.stats?.blocked_count },
            ].map(s => (
              <div key={s.l} className="bg-card p-4">
                <div className="label-mono">{s.l}</div>
                <div className="data-number text-3xl mt-1">{s.v || 0}</div>
              </div>
            ))}
          </div>

          {data.narrative && (
            <div className="border border-primary/40 bg-card rounded-md p-5">
              <div className="label-mono flex items-center gap-2 mb-3"><Sparkles size={12} className="text-primary" /> {t("السرد", "Narrative")}</div>
              <p className="text-sm leading-relaxed whitespace-pre-wrap">{data.narrative}</p>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Section title={t("الانتصارات", "Wins")} icon={TrendingUp} items={data.wins} tone="wins" emptyLabel={empty} />
            <Section title={t("الإخفاقات", "Misses")} icon={TrendingDown} items={data.misses} tone="misses" emptyLabel={empty} />
            <Section title={t("الأنماط", "Patterns")} icon={Target} items={data.patterns} emptyLabel={empty} />
            <Section title={t("الاختناقات", "Bottlenecks")} icon={AlertTriangle} items={data.bottlenecks} tone="risks" emptyLabel={empty} />
          </div>

          <Section title={t("أولويات الأسبوع القادم", "Next week priorities")} icon={Target} items={data.next_week_priorities} emptyLabel={empty} />
          <Section title={t("رؤى الذكاء", "AI insights")} icon={Lightbulb} items={data.insights} emptyLabel={empty} />
        </>
      ) : null}
    </div>
  );
}
