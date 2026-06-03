import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { useLang } from "@/contexts/LanguageContext";
import { Languages } from "lucide-react";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function Brief() {
  const { token } = useParams();
  const { lang, toggle: toggleLang, t } = useLang();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  const RISK_COLOR = { on_track: "bg-emerald-500", at_risk: "bg-amber-500", delayed: "bg-red-500" };
  const RISK_LABEL = {
    on_track: t("في المسار", "On track"),
    at_risk: t("تحت الخطر", "At risk"),
    delayed: t("متأخر", "Delayed"),
  };

  useEffect(() => {
    setData(null); setError(null);
    axios.get(`${API}/share/brief/${token}`, { headers: { "X-Lang": lang } })
      .then(r => setData(r.data))
      .catch(e => setError(e?.response?.data?.detail || t("غير موجود", "Not found")));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, lang]);

  const locale = lang === "ar" ? "ar-EG" : "en-US";

  if (error) {
    return <div className="min-h-screen flex items-center justify-center bg-background text-foreground">
      <div className="text-center">
        <div className="label-mono">{t("الملخص غير متاح", "Briefing unavailable")}</div>
        <div className="text-sm text-muted-foreground mt-2">{error}</div>
      </div>
    </div>;
  }
  if (!data) return <div className="min-h-screen flex items-center justify-center bg-background"><div className="label-mono animate-pulse">{t("جارٍ التحميل…", "Loading…")}</div></div>;

  return (
    <div className="min-h-screen bg-background text-foreground noise">
      <div className="max-w-4xl mx-auto px-6 sm:px-10 py-12 sm:py-20">
        <div className="flex items-center justify-between mb-12">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 bg-primary flex items-center justify-center rounded-sm">
              <span className="text-primary-foreground font-mono font-bold text-sm">O</span>
            </div>
            <span className="font-medium tracking-tight">{t("أوبس‌كور", "OpsCore")}</span>
            <span className="label-mono text-[10px] ms-2">{t("ملخص تنفيذي", "Executive brief")}</span>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={toggleLang}
              className="h-8 px-2.5 flex items-center gap-1.5 rounded-md border border-border hover:bg-secondary transition-colors text-xs font-mono"
              aria-label="Toggle language"
            >
              <Languages size={12} />
              <span className="uppercase">{lang === "ar" ? "EN" : "AR"}</span>
            </button>
            <div className="label-mono text-[10px]">{t("ع", "v")}{data.views || 1}</div>
          </div>
        </div>

        <div className="space-y-3 mb-12">
          <div className="label-mono">{new Date(data.generated_at).toLocaleDateString(locale, { weekday: "long", month: "long", day: "numeric" })}</div>
          <h1 className="text-4xl sm:text-5xl tracking-tight font-medium leading-[1.2]">{data.title}</h1>
          <p className="text-sm text-muted-foreground">{t("من نظام تشغيل", "From the OS of")} {data.owner_name}</p>
        </div>

        <div className="grid grid-cols-3 gap-px bg-border mb-12">
          <div className="bg-background p-5">
            <div className="label-mono">{t("السرعة", "Velocity")}</div>
            <div className="data-number text-4xl mt-2">{data.velocity}</div>
            <div className="label-mono text-[9px] mt-1">{t("مهام مكتملة · ٧ أيام", "Tasks completed · 7d")}</div>
          </div>
          <div className="bg-background p-5">
            <div className="label-mono">{t("تركيز عميق", "Deep focus")}</div>
            <div className="data-number text-4xl mt-2">{Math.floor((data.weekly_focus_minutes || 0) / 60)}<span className="text-lg text-muted-foreground">{t("س", "h")}</span></div>
            <div className="label-mono text-[9px] mt-1">{data.weekly_focus_minutes || 0} {t("د · ٧ أيام", "min · 7d")}</div>
          </div>
          <div className="bg-background p-5">
            <div className="label-mono">{t("نشطة", "Active")}</div>
            <div className="data-number text-4xl mt-2">{data.active_tasks}</div>
            <div className="label-mono text-[9px] mt-1">{t("مهام مفتوحة", "Open tasks")}</div>
          </div>
        </div>

        {data.narrative && (
          <div className="mb-12">
            <div className="label-mono mb-3">{t("حالة العمليات", "Operations status")}</div>
            <p className="text-lg leading-relaxed">{data.narrative}</p>
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mb-12">
          <div>
            <div className="label-mono mb-3">{t("أكبر المخاطر", "Top risks")}</div>
            <div className="space-y-2">
              {data.top_risks?.length ? data.top_risks.map((r, i) => (
                <div key={i} className="border-s-2 border-destructive ps-3 py-1">
                  <div className="text-sm leading-relaxed">{r}</div>
                </div>
              )) : <div className="text-sm text-muted-foreground">{t("لا توجد مخاطر حرجة.", "No critical risks.")}</div>}
            </div>
          </div>
          <div>
            <div className="label-mono mb-3">{t("الإجراءات الاستراتيجية", "Strategic actions")}</div>
            <div className="space-y-2">
              {data.strategic_actions?.length ? data.strategic_actions.map((a, i) => (
                <div key={i} className="border-s-2 border-primary ps-3 py-1">
                  <div className="text-sm leading-relaxed">{a}</div>
                </div>
              )) : <div className="text-sm text-muted-foreground">—</div>}
            </div>
          </div>
        </div>

        {data.projects?.length > 0 && (
          <div className="mb-12">
            <div className="label-mono mb-3">{t("صحة المشاريع", "Project health")}</div>
            <div className="border border-border rounded-md divide-y divide-border">
              {data.projects.map((p, i) => (
                <div key={i} className="px-4 py-3 flex items-center justify-between">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className={`w-2 h-2 rounded-full ${RISK_COLOR[p.risk] || "bg-muted-foreground"}`} />
                    <div className="min-w-0">
                      <div className="text-sm font-medium truncate">{p.name}</div>
                      <div className="label-mono text-[9px]">{RISK_LABEL[p.risk] || p.risk} · {p.task_count} {t("مهمة", "tasks")}</div>
                    </div>
                  </div>
                  <div className="text-end shrink-0">
                    <div className="font-mono text-sm">{p.progress}%</div>
                    <div className="w-24 h-1 bg-secondary rounded-full mt-1 overflow-hidden">
                      <div className="h-full bg-primary" style={{ width: `${p.progress}%` }} />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="border-t border-border pt-6 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          <div className="label-mono text-[10px]">{t("تم التوليد بواسطة رئيس العمليات الذكي · كلود سونيت ٤٫٥", "Generated by AI Chief of Operations · Claude Sonnet 4.5")}</div>
          <a href="/" className="text-sm text-primary hover:underline">{t("شغّل أوبس‌كور الخاص بك ←", "Run your own OpsCore →")}</a>
        </div>
      </div>
    </div>
  );
}
