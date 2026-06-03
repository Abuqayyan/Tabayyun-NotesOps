import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useLang } from "@/contexts/LanguageContext";
import { Bell, AlertTriangle, Clock, Pause } from "lucide-react";

const ICONS = { overdue: AlertTriangle, due_soon: Clock, blocked: Pause };

export default function Notifications() {
  const { lang, t } = useLang();
  const [items, setItems] = useState([]);
  useEffect(() => { api.get("/notifications").then(r => setItems(r.data)); }, [lang]);
  const locale = lang === "ar" ? "ar-EG" : "en-US";

  return (
    <div className="p-6 lg:p-8 space-y-6" data-testid="notifications-page">
      <div>
        <div className="label-mono">{t("إشارات", "Signals")}</div>
        <h1 className="text-3xl sm:text-4xl tracking-tight font-medium mt-1">{t("الإشعارات", "Notifications")}</h1>
        <p className="text-sm text-muted-foreground mt-1">{items.length} {t("تنبيهات ذكية", "smart alerts")}</p>
      </div>

      <div className="border border-border bg-card rounded-md">
        {items.length === 0 ? (
          <div className="p-12 text-center"><Bell className="mx-auto text-muted-foreground mb-3" size={28} /><div className="text-sm text-muted-foreground">{t("كل شيء هادئ. لا شيء يحترق.", "All quiet. Nothing on fire.")}</div></div>
        ) : (
          <div className="divide-y divide-border">
            {items.map(n => {
              const I = ICONS[n.type] || Bell;
              return (
                <div key={n.id} className="px-5 py-3 flex items-center justify-between hover:bg-secondary/50">
                  <div className="flex items-center gap-3 min-w-0">
                    <I size={14} className={n.type === "overdue" ? "text-red-500" : n.type === "blocked" ? "text-amber-500" : "text-primary"} />
                    <div className="min-w-0">
                      <div className="text-sm font-medium">{n.title}</div>
                      <div className="text-xs text-muted-foreground truncate">{n.message}</div>
                    </div>
                  </div>
                  <div className="label-mono text-[9px] shrink-0">{new Date(n.created_at).toLocaleDateString(locale)}</div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
