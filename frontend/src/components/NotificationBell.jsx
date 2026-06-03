// Header notification bell (Module 5) — unread badge + dropdown fed by the persistent
// Notification Center API. Reuses the platform's dropdown + list patterns.
import { useState, useRef, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { useLang } from "@/contexts/LanguageContext";
import { useWebSocket } from "@/lib/useWebSocket";
import { Bell, CheckCheck, Archive } from "lucide-react";

const CAT_DOT = {
  approval: "bg-amber-500", escalation: "bg-red-500", task: "bg-primary",
  meeting: "bg-blue-500", crm: "bg-emerald-500", report: "bg-violet-500",
  knowledge: "bg-sky-500", intelligence: "bg-fuchsia-500", system: "bg-muted-foreground",
};

export default function NotificationBell() {
  const { t, lang } = useLang();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const [items, setItems] = useState([]);
  const ref = useRef(null);

  const loadCount = useCallback(() => {
    api.get("/notifications/center/unread-count").then((r) => setUnread(r.data.unread || 0)).catch(() => {});
  }, []);
  const loadItems = useCallback(() => {
    api.get("/notifications/center", { params: { limit: 12 } }).then((r) => setItems(r.data || [])).catch(() => {});
  }, []);

  useEffect(() => {
    loadCount();
    const id = setInterval(loadCount, 30000);
    return () => clearInterval(id);
  }, [loadCount]);

  useWebSocket((p) => {
    if (p.event === "notification.new") loadCount();
  });

  useEffect(() => {
    const onClick = (e) => ref.current && !ref.current.contains(e.target) && setOpen(false);
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const toggle = () => {
    const next = !open;
    setOpen(next);
    if (next) loadItems();
  };

  const markRead = async (id) => {
    await api.post(`/notifications/center/${id}/read`).catch(() => {});
    loadCount();
    loadItems();
  };
  const archive = async (id) => {
    await api.post(`/notifications/center/${id}/archive`).catch(() => {});
    loadCount();
    loadItems();
  };
  const markAll = async () => {
    await api.post("/notifications/center/read-all").catch(() => {});
    loadCount();
    loadItems();
  };

  const locale = lang === "ar" ? "ar-EG" : "en-US";

  return (
    <div className="relative" ref={ref}>
      <button
        data-testid="notification-bell-btn"
        onClick={toggle}
        className="relative w-9 h-9 flex items-center justify-center rounded-md border border-border hover:bg-secondary transition-colors"
        title={t("الإشعارات", "Notifications")}
        aria-label={t("الإشعارات", "Notifications")}
      >
        <Bell size={15} />
        {unread > 0 && (
          <span className="absolute -top-1 -end-1 min-w-4 h-4 px-1 bg-primary text-primary-foreground rounded-full text-[10px] font-mono flex items-center justify-center" data-testid="notification-unread-badge">
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute end-0 mt-2 w-80 bg-card border border-border rounded-md overflow-hidden z-50 glass" data-testid="notification-dropdown">
          <div className="hairline px-4 py-2.5 flex items-center justify-between">
            <span className="label-mono">{t("الإشعارات", "Notifications")}</span>
            <button onClick={markAll} className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1">
              <CheckCheck size={12} /> {t("قراءة الكل", "Mark all read")}
            </button>
          </div>
          <div className="max-h-96 overflow-y-auto divide-y divide-border">
            {items.length === 0 && (
              <div className="p-8 text-center text-sm text-muted-foreground">{t("لا توجد إشعارات.", "You're all caught up.")}</div>
            )}
            {items.map((n) => (
              <div key={n.id} className={`px-4 py-3 flex items-start gap-2.5 hover:bg-secondary/50 ${n.read ? "opacity-60" : ""}`}>
                <span className={`w-1.5 h-1.5 rounded-full mt-1.5 shrink-0 ${CAT_DOT[n.category] || "bg-muted-foreground"}`} />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium truncate">{n.title}</div>
                  {n.message && <div className="text-xs text-muted-foreground truncate">{n.message}</div>}
                  <div className="font-mono text-[10px] text-muted-foreground mt-1">{n.created_at ? new Date(n.created_at).toLocaleString(locale) : ""}</div>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  {!n.read && <button onClick={() => markRead(n.id)} title={t("تعليم كمقروء", "Mark read")} className="p-1 hover:text-primary"><CheckCheck size={13} /></button>}
                  <button onClick={() => archive(n.id)} title={t("أرشفة", "Archive")} className="p-1 hover:text-foreground text-muted-foreground"><Archive size={13} /></button>
                </div>
              </div>
            ))}
          </div>
          <button
            onClick={() => { setOpen(false); navigate("/inbox"); }}
            className="w-full hairline px-4 py-2.5 text-sm text-center hover:bg-secondary"
          >
            {t("عرض كل الإشعارات", "View all notifications")}
          </button>
        </div>
      )}
    </div>
  );
}
