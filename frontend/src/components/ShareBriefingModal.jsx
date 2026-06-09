import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useLang } from "@/contexts/LanguageContext";
import { Share2, Copy, Trash2, ExternalLink, Plus } from "lucide-react";
import { toast } from "sonner";

export default function ShareBriefingModal({ open, onClose }) {
  const { t } = useLang();
  const [briefs, setBriefs] = useState([]);
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState("");

  const load = () => api.get("/share/briefs").then(r => setBriefs(r.data));
  useEffect(() => { if (open) load(); }, [open]);

  const create = async (e) => {
    e?.preventDefault?.();
    setCreating(true);
    try {
      const r = await api.post("/share/brief", { title: title || undefined });
      toast.success(t("تم إنشاء رابط المشاركة", "Share link created"));
      setTitle("");
      load();
      const url = `${window.location.origin}${r.data.share_url}`;
      navigator.clipboard?.writeText(url);
      toast.message(t("تم النسخ", "Copied"));
    } catch { toast.error(t("فشل", "Failed")); } finally { setCreating(false); }
  };

  const copy = (token) => {
    const url = `${window.location.origin}/brief/${token}`;
    navigator.clipboard?.writeText(url);
    toast.success(t("تم النسخ", "Copied"));
  };

  const remove = async (token) => { await api.delete(`/share/brief/${token}`); load(); };

  if (!open) return null;

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={onClose} data-testid="share-brief-modal">
      <div onClick={e => e.stopPropagation()} className="bg-card border border-border rounded-md w-full max-w-lg max-h-[85vh] overflow-y-auto">
        <div className="hairline px-5 py-3 flex items-center gap-2">
          <Share2 size={13} className="text-primary" />
          <div className="label-mono">{t("ملخص ذكي للمشاركة", "Shareable AI briefing")}</div>
        </div>
        <div className="p-5 space-y-4">
          <p className="text-sm text-muted-foreground">
            {t(
              "أنشئ رابطًا للقراءة فقط لمشاركة ملخصك التنفيذي. شاركه مع الشركاء أو المستثمرين أو فريقك.",
              "Create a read-only link to share your executive briefing with partners, investors, or your team."
            )}
          </p>
          <form onSubmit={create} className="flex gap-2">
            <input value={title} onChange={e => setTitle(e.target.value)} placeholder={t("عنوان اختياري…", "Optional title…")}
              className="flex-1 px-3 py-2 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary" />
            <button type="submit" disabled={creating} data-testid="create-share-brief"
              className="px-3 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:opacity-90 disabled:opacity-50 flex items-center gap-2">
              <Plus size={13} /> {t("أنشئ", "Create")}
            </button>
          </form>

          <div className="space-y-2">
            {briefs.length === 0 && <div className="text-sm text-muted-foreground py-4 text-center">{t("لا توجد روابط بعد.", "No links yet.")}</div>}
            {briefs.map(b => (
              <div key={b.token} className="border border-border rounded-md p-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-sm font-medium truncate">{b.title}</div>
                    <div className="label-mono text-[9px] mt-0.5" dir="ltr">/brief/{b.token} · {b.views || 0} {t("مشاهدة", "views")}</div>
                  </div>
                  <div className="flex gap-1 shrink-0">
                    <button onClick={() => copy(b.token)} className="w-8 h-8 hover:bg-secondary rounded-md flex items-center justify-center" title={t("نسخ", "Copy")}><Copy size={12} /></button>
                    <a href={`/brief/${b.token}`} target="_blank" rel="noreferrer" className="w-8 h-8 hover:bg-secondary rounded-md flex items-center justify-center" title={t("افتح", "Open")}><ExternalLink size={12} /></a>
                    <button onClick={() => remove(b.token)} className="w-8 h-8 hover:bg-destructive/10 text-muted-foreground hover:text-destructive rounded-md flex items-center justify-center"><Trash2 size={12} /></button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
