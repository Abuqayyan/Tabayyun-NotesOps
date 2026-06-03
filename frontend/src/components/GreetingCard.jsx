import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useLang } from "@/contexts/LanguageContext";
import { motion } from "framer-motion";
import { Sun, Cloud, Moon, Sunrise } from "lucide-react";

const ICONS = { morning: Sunrise, afternoon: Sun, evening: Cloud, night: Moon, late: Moon };

export default function GreetingCard() {
  const { lang, t } = useLang();
  const [data, setData] = useState(null);
  const [dismissed] = useState(() => {
    const todayKey = new Date().toDateString();
    const last = localStorage.getItem("opscore_greet_day");
    if (last === todayKey) return true;
    localStorage.setItem("opscore_greet_day", todayKey);
    return false;
  });

  useEffect(() => {
    if (dismissed) return;
    api.get("/dashboard/greeting").then(r => setData(r.data)).catch(() => {});
  }, [dismissed, lang]);

  if (!data || dismissed) return null;
  const Icon = ICONS[data.period] || Sun;

  return (
    <motion.div
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="flex items-center justify-between gap-6 py-2"
      data-testid="greeting-card"
    >
      <div className="flex items-center gap-4">
        <div className="w-10 h-10 rounded-md bg-primary/10 border border-primary/30 flex items-center justify-center shrink-0">
          <Icon size={16} className="text-primary" />
        </div>
        <div>
          <h2 className="text-2xl sm:text-3xl tracking-tight font-medium">
            {data.greeting}{data.name ? `، ${data.name}` : ""}.
          </h2>
          <p className="text-sm text-muted-foreground mt-0.5">{data.prompt}</p>
        </div>
      </div>
      <div className="hidden sm:flex items-center gap-4 text-end">
        <div>
          <div className="data-number text-xl">{data.stats.open_tasks}</div>
          <div className="label-mono text-[9px]">{t("مفتوحة", "Open")}</div>
        </div>
        <div>
          <div className={`data-number text-xl ${data.stats.in_progress ? "text-primary" : ""}`}>{data.stats.in_progress}</div>
          <div className="label-mono text-[9px]">{t("جارية", "In progress")}</div>
        </div>
        <div>
          <div className={`data-number text-xl ${data.stats.overdue ? "text-red-500" : ""}`}>{data.stats.overdue}</div>
          <div className="label-mono text-[9px]">{t("متأخرة", "Overdue")}</div>
        </div>
      </div>
    </motion.div>
  );
}
