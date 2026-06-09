import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useLang } from "@/contexts/LanguageContext";
import { AlertTriangle, ArrowLeft, Loader2, Sparkles, Brain, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

export default function Memory() {
  const { lang, t } = useLang();
  const [items, setItems] = useState([]);
  const [bottlenecks, setBottlenecks] = useState([]);
  const [adding, setAdding] = useState("");
  const [extracting, setExtracting] = useState(false);

  const TYPE_LABEL = {
    note: t("ملاحظة", "Note"),
    blocker: t("عائق", "Blocker"),
    pattern: t("نمط", "Pattern"),
    client: t("عميل", "Client"),
    bottleneck: t("اختناق", "Bottleneck"),
    weekly_review: t("مراجعة أسبوعية", "Weekly review"),
  };

  const load = () => {
    api.get("/ai/memory").then(r => setItems(r.data));
    api.get("/dependencies/bottlenecks").then(r => setBottlenecks(r.data.bottlenecks || []));
  };
  useEffect(() => { load(); }, []);

  const add = async (e) => {
    e.preventDefault();
    if (!adding.trim()) return;
    await api.post("/ai/memory", { content: adding, type: "note" });
    setAdding(""); load();
  };

  const remove = async (id) => { await api.delete(`/ai/memory/${id}`); load(); };

  const extract = async () => {
    setExtracting(true);
    try {
      const r = await api.post("/ai/memory/extract");
      toast.success(`${r.data.extracted.length} ${t("نمط تم استخراجه", "patterns extracted")}`);
      load();
    } catch { toast.error(t("فشل الاستخراج", "Extraction failed")); } finally { setExtracting(false); }
  };

  const locale = lang === "ar" ? "ar-EG" : "en-US";

  return (
    <div className="p-6 lg:p-8 space-y-6 max-w-5xl" data-testid="memory-page">
      <div className="flex items-end justify-between flex-wrap gap-4">
        <div>
          <div className="label-mono">{t("الدماغ التشغيلي", "Operational brain")}</div>
          <h1 className="text-3xl sm:text-4xl tracking-tight font-medium mt-1">{t("الذاكرة والذكاء", "Memory & Intelligence")}</h1>
          <p className="text-sm text-muted-foreground mt-1">{t("ما الذي يتذكره رئيس عملياتك الذكي عن نشاطك.", "What your AI Chief of Operations remembers about your work.")}</p>
        </div>
        <button onClick={extract} disabled={extracting}
          className="px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:opacity-90 disabled:opacity-50 flex items-center gap-2">
          {extracting ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />} {t("استخرج الأنماط", "Extract patterns")}
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="border border-border bg-card rounded-md">
          <div className="hairline px-5 py-3 flex items-center gap-2"><Brain size={13} className="text-primary" /><div className="label-mono">{t("الذاكرة", "Memory")}</div></div>
          <form onSubmit={add} className="px-5 py-3 border-b border-border flex gap-2">
            <input value={adding} onChange={e => setAdding(e.target.value)} placeholder={t("أضف سياقًا تشغيليًا، عائقًا متكررًا، ملاحظة عميل…", "Add operational context, a recurring blocker, a client note…")}
              className="flex-1 px-3 py-2 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary" data-testid="memory-input" />
            <button type="submit" className="px-3 py-2 bg-primary text-primary-foreground rounded-md hover:opacity-90"><Plus size={13} /></button>
          </form>
          <div className="divide-y divide-border max-h-[500px] overflow-y-auto">
            {items.length === 0 && <div className="p-8 text-center text-sm text-muted-foreground">{t("لا توجد ذاكرة بعد. شغّل «استخرج الأنماط» لاستخراج المعلومات من مساحة عملك.", "No memory yet. Run \"Extract patterns\" to mine insights from your workspace.")}</div>}
            {items.map(m => (
              <div key={m.id} className="px-5 py-3 flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="label-mono text-[9px]">{TYPE_LABEL[m.type] || m.type}</span>
                    {m.source === "ai_extract" && <span className="label-mono text-[9px] text-primary">{t("ذكاء", "AI")}</span>}
                  </div>
                  {m.type === "weekly_review" ? (
                    <div className="text-sm mt-1 line-clamp-2">{m.content?.narrative || JSON.stringify(m.content).slice(0, 120)}</div>
                  ) : (
                    <div className="text-sm mt-1 whitespace-pre-wrap">{m.content}</div>
                  )}
                  <div className="label-mono text-[9px] mt-2">{new Date(m.created_at).toLocaleString(locale)}</div>
                </div>
                <button onClick={() => remove(m.id)} className="w-7 h-7 hover:bg-destructive/10 text-muted-foreground hover:text-destructive rounded-md flex items-center justify-center"><Trash2 size={12} /></button>
              </div>
            ))}
          </div>
        </div>

        <div className="border border-border bg-card rounded-md">
          <div className="hairline px-5 py-3 flex items-center gap-2"><AlertTriangle size={13} className="text-amber-500" /><div className="label-mono">{t("الاختناقات", "Bottlenecks")}</div></div>
          <div className="divide-y divide-border max-h-[600px] overflow-y-auto">
            {bottlenecks.length === 0 && <div className="p-8 text-center text-sm text-muted-foreground">{t("لم تُكتشف اختناقات. أضف اعتماديات بين المهام لإظهار مخاطر التنفيذ.", "No bottlenecks detected. Add task dependencies to surface execution risks.")}</div>}
            {bottlenecks.map(b => (
              <div key={b.task.id} className="px-5 py-3">
                <div className="flex items-center gap-2">
                  <div className={`w-1.5 h-1.5 rounded-full ${b.task.is_delayed ? "bg-red-500" : "bg-amber-500"}`} />
                  <div className="text-sm font-medium flex-1 truncate">{b.task.title}</div>
                  <span className="label-mono text-[9px]">{t("الأثر", "Impact")} {b.impact_score}</span>
                </div>
                <div className="mt-2 ms-3.5 space-y-1">
                  <div className="label-mono text-[9px]">{t("يحجب", "Blocks")} {b.blocks_count} {t("مهمة", "tasks")}</div>
                  {b.blocks.slice(0, 3).map(bt => (
                    <div key={bt.id} className="text-xs text-muted-foreground flex items-center gap-1">
                      <ArrowLeft size={10} className="rtl:rotate-180" /> {bt.title}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
