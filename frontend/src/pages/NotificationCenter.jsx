import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { useLang } from "@/contexts/LanguageContext";
import { PageHeader, Section, Empty, Loading, Badge, GhostButton } from "@/components/kit";
import { Bell, CheckCheck, Archive } from "lucide-react";

const CATS = ["all", "approval", "escalation", "task", "meeting", "crm", "report", "knowledge", "intelligence", "system"];

export default function NotificationCenter() {
  const { t, lang } = useLang();
  const [status, setStatus] = useState("all");
  const [category, setCategory] = useState("all");
  const [rows, setRows] = useState(null);
  const locale = lang === "ar" ? "ar-EG" : "en-US";

  const load = useCallback(() => {
    const params = { status, limit: 100 };
    if (category !== "all") params.category = category;
    api.get("/notifications/center", { params }).then((r) => setRows(r.data)).catch(() => setRows([]));
  }, [status, category]);
  useEffect(() => { load(); }, [load]);

  const act = async (path) => { await api.post(path).catch(() => {}); load(); };

  return (
    <div className="p-6 lg:p-8 space-y-6" data-testid="notification-center-page">
      <PageHeader label={t("الإشعارات", "Inbox")} title={t("مركز الإشعارات", "Notification Center")}
        actions={<GhostButton data-testid="notif-read-all" onClick={() => act("/notifications/center/read-all")}><CheckCheck size={14} /> {t("قراءة الكل", "Mark all read")}</GhostButton>} />

      <div className="flex flex-wrap items-center gap-2">
        {["all", "unread", "read", "archived"].map((s) => (
          <button key={s} onClick={() => setStatus(s)} className={`px-3 py-1.5 rounded-md text-sm border ${status === s ? "border-primary text-foreground bg-secondary" : "border-border text-muted-foreground hover:bg-secondary/60"}`}>{t(s === "all" ? "الكل" : s === "unread" ? "غير مقروء" : s === "read" ? "مقروء" : "مؤرشف", s)}</button>
        ))}
        <span className="mx-2 h-5 w-px bg-border" />
        {CATS.map((c) => (
          <button key={c} onClick={() => setCategory(c)} className={`px-2.5 py-1 rounded-md text-xs border ${category === c ? "border-primary text-foreground" : "border-border text-muted-foreground hover:bg-secondary/60"}`}>{c}</button>
        ))}
      </div>

      {rows === null ? <Loading label={t("تحميل…", "Loading…")} /> : (
        <Section>
          <div className="divide-y divide-border">
            {rows.length === 0 && <Empty><Bell size={20} className="mx-auto mb-2 opacity-40" />{t("لا إشعارات.", "Nothing here.")}</Empty>}
            {rows.map((n) => (
              <div key={n.id} className={`px-5 py-3 flex items-start justify-between gap-3 ${n.read ? "opacity-60" : ""}`} data-testid="notif-row">
                <div className="min-w-0">
                  <div className="flex items-center gap-2"><span className="text-sm font-medium truncate">{n.title}</span><Badge>{n.category}</Badge></div>
                  {n.message && <div className="text-xs text-muted-foreground mt-0.5">{n.message}</div>}
                  <div className="font-mono text-[10px] text-muted-foreground mt-1">{n.created_at ? new Date(n.created_at).toLocaleString(locale) : ""}</div>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  {!n.read && <button onClick={() => act(`/notifications/center/${n.id}/read`)} title={t("مقروء", "Read")} className="p-1.5 hover:text-primary"><CheckCheck size={14} /></button>}
                  {!n.archived && <button onClick={() => act(`/notifications/center/${n.id}/archive`)} title={t("أرشفة", "Archive")} className="p-1.5 hover:text-foreground text-muted-foreground"><Archive size={14} /></button>}
                </div>
              </div>
            ))}
          </div>
        </Section>
      )}
    </div>
  );
}
