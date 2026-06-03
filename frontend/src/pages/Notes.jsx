import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useLang } from "@/contexts/LanguageContext";
import { Plus, Sparkles, Loader2, Trash2, Check, Archive, RotateCcw } from "lucide-react";
import { toast } from "sonner";
import ReminderBell from "@/components/ReminderBell";

export default function Notes() {
  const { lang, t } = useLang();
  const [notes, setNotes] = useState([]);
  const [projects, setProjects] = useState([]);
  const [form, setForm] = useState({ title: "", content: "", project_id: "" });
  const [busy, setBusy] = useState(false);
  const [showDone, setShowDone] = useState(false);

  const load = () => api.get("/notes", { params: { include_done: showDone } }).then(r => setNotes(r.data));
  useEffect(() => {
    load();
    api.get("/projects").then(r => setProjects(r.data));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showDone]);

  const create = async (e) => {
    e.preventDefault();
    if (!form.title || !form.content) return;
    await api.post("/notes", { ...form, project_id: form.project_id || null });
    setForm({ title: "", content: "", project_id: "" });
    toast.success(t("تم الحفظ", "Saved"));
    load();
  };

  const remove = async (id) => { await api.delete(`/notes/${id}`); load(); };

  const toggleDone = async (n) => {
    const next = !n.done;
    await api.patch(`/notes/${n.id}`, { done: next });
    toast.success(next ? t("تم تعليمها كمنجزة", "Marked done") : t("تم إعادة الفتح", "Reopened"));
    load();
  };

  const rewrite = async () => {
    if (!form.content) return;
    setBusy(true);
    try {
      const r = await api.post("/ai/rewrite", { text: form.content, tone: "professional" });
      setForm({ ...form, content: r.data.rewritten });
      toast.success(t("تمت إعادة الصياغة", "Rewritten"));
    } catch { toast.error(t("خطأ في الذكاء", "AI error")); } finally { setBusy(false); }
  };

  const locale = lang === "ar" ? "ar-EG" : "en-US";

  return (
    <div className="p-6 lg:p-8 space-y-6" data-testid="notes-page">
      <div className="flex items-end justify-between flex-wrap gap-4">
        <div>
          <div className="label-mono">{t("الذاكرة", "Memory")}</div>
          <h1 className="text-3xl sm:text-4xl tracking-tight font-medium mt-1">{t("الملاحظات والسياق", "Notes & Context")}</h1>
          <p className="text-sm text-muted-foreground mt-1">{t("اكتب أفكارك المبدئية. الذكاء راح يعيد صياغتها وينظمها.", "Drop your raw thoughts. AI will rewrite and organize them.")}</p>
        </div>
        <button onClick={() => setShowDone(s => !s)} data-testid="toggle-done-btn"
          className="px-3 py-2 border border-border rounded-md text-xs font-mono hover:bg-secondary flex items-center gap-2">
          <Archive size={12} /> {showDone ? t("إخفاء المنجزة", "Hide done") : t("إظهار المنجزة", "Show done")}
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <form onSubmit={create} className="lg:col-span-1 border border-border bg-card rounded-md p-4 space-y-3 h-fit" data-testid="new-note-form">
          <div className="label-mono">{t("اكتب", "Write")}</div>
          <input value={form.title} onChange={e => setForm({ ...form, title: e.target.value })}
            placeholder={t("عنوان الملاحظة…", "Note title…")} data-testid="note-title"
            className="w-full px-3 py-2 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary" />
          <textarea value={form.content} onChange={e => setForm({ ...form, content: e.target.value })}
            placeholder={t("اكتب الأفكار، ملاحظات الاجتماع، العصف الذهني…", "Capture ideas, meeting notes, brainstorms…")} rows={8} data-testid="note-content"
            className="w-full px-3 py-2 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary" />
          <select value={form.project_id} onChange={e => setForm({ ...form, project_id: e.target.value })}
            className="w-full px-3 py-2 bg-background border border-border rounded-md text-sm">
            <option value="">{t("بدون مشروع", "No project")}</option>
            {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <div className="flex gap-2">
            <button type="button" onClick={rewrite} disabled={busy || !form.content}
              className="flex-1 px-3 py-2 border border-primary text-primary rounded-md text-sm font-medium hover:bg-primary hover:text-primary-foreground transition-colors flex items-center justify-center gap-2 disabled:opacity-40">
              {busy ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />} {t("إعادة صياغة", "AI Rewrite")}
            </button>
            <button data-testid="save-note-btn" type="submit" className="flex-1 px-3 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:opacity-90 flex items-center justify-center gap-2"><Plus size={13} /> {t("احفظ", "Save")}</button>
          </div>
        </form>

        <div className="lg:col-span-2 space-y-3">
          {notes.length === 0 ? (
            <div className="border border-dashed border-border rounded-md py-12 text-center text-sm text-muted-foreground">
              {showDone ? t("لا توجد ملاحظات بعد.", "No notes yet.") : t("لا توجد ملاحظات نشطة. الكل منجز ✓", "No active notes. All done ✓")}
            </div>
          ) : notes.map(n => (
            <div key={n.id} className={`border border-border bg-card rounded-md p-4 transition-opacity ${n.done ? "opacity-60" : ""}`} data-testid={`note-${n.id}`}>
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <div className={`font-medium tracking-tight ${n.done ? "line-through" : ""}`}>{n.title}</div>
                  <div className="text-sm text-muted-foreground mt-2 whitespace-pre-wrap leading-relaxed">{n.content}</div>
                </div>
                <div className="flex gap-1 shrink-0">
                  <ReminderBell entityType="note" entityId={n.id} />
                  <button onClick={() => toggleDone(n)} data-testid={`note-done-${n.id}`}
                    className={`w-8 h-8 rounded-md flex items-center justify-center transition-colors ${n.done ? "bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/20" : "hover:bg-secondary text-muted-foreground hover:text-emerald-500"}`}
                    title={n.done ? t("إعادة فتح", "Reopen") : t("تعليم كمنجزة", "Mark done")}>
                    {n.done ? <RotateCcw size={13}/> : <Check size={13}/>}
                  </button>
                  <button onClick={() => remove(n.id)} className="w-8 h-8 hover:bg-destructive/10 text-muted-foreground hover:text-destructive rounded-md flex items-center justify-center"><Trash2 size={13}/></button>
                </div>
              </div>
              <div className="label-mono text-[9px] mt-3 flex items-center gap-2">
                <span>{new Date(n.created_at).toLocaleString(locale)}</span>
                {n.done && n.done_at && <span className="text-emerald-500">✓ {t("منجزة", "done")} · {new Date(n.done_at).toLocaleDateString(locale)}</span>}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

