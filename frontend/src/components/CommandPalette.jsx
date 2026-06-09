import { useState, useEffect, useRef, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useLang } from "@/contexts/LanguageContext";
import { api } from "@/lib/api";
import { Command, Search, Clock, X, CornerDownLeft } from "lucide-react";

// Global-search-enabled command palette (Module 4). Typing queries GET /api/search
// (permission-aware, ranked); an empty query shows quick actions + recent searches.
const TYPE_ROUTE = {
  task: "/tasks", project: "/projects", employee: "/organization", department: "/organization",
  meeting: "/meetings", approval: "/approvals", knowledge: "/knowledge",
  crm_company: "/crm", crm_contact: "/crm", crm_opportunity: "/crm", report: "/executive", activity: "/",
};
const TYPE_LABEL = {
  task: ["مهمة", "Task"], project: ["مشروع", "Project"], employee: ["موظف", "Employee"],
  department: ["قسم", "Department"], meeting: ["اجتماع", "Meeting"], approval: ["موافقة", "Approval"],
  knowledge: ["معرفة", "Knowledge"], crm_company: ["شركة", "Company"], crm_contact: ["جهة اتصال", "Contact"],
  crm_opportunity: ["فرصة", "Opportunity"], report: ["تقرير", "Report"], activity: ["نشاط", "Activity"],
};

export default function CommandPalette({ open, onClose, navigate }) {
  const { t } = useLang();
  const [q, setQ] = useState("");
  const [results, setResults] = useState([]);
  const [recent, setRecent] = useState([]);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef(null);

  const ACTIONS = [
    { label: t("اذهب إلى لوحة القيادة", "Go to Dashboard"), path: "/", hint: "G D" },
    { label: t("لوحة التنفيذيين", "Executive dashboard"), path: "/executive", hint: "G E" },
    { label: t("إدارة العملاء", "Open CRM"), path: "/crm", hint: "G C" },
    { label: t("الموافقات", "Approvals"), path: "/approvals", hint: "G A" },
    { label: t("الاجتماعات", "Meetings"), path: "/meetings", hint: "G M" },
    { label: t("قاعدة المعرفة", "Knowledge Base"), path: "/knowledge", hint: "G K" },
    { label: t("التحديثات اليومية", "Daily Updates"), path: "/daily-updates", hint: "G U" },
    { label: t("الإعدادات", "Settings"), path: "/settings", hint: "G S" },
  ];

  const loadRecent = useCallback(() => {
    api.get("/search/recent").then((r) => setRecent(r.data || [])).catch(() => {});
  }, []);

  useEffect(() => {
    if (open) {
      setQ("");
      setResults([]);
      loadRecent();
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open, loadRecent]);

  useEffect(() => {
    if (!open) return;
    const term = q.trim();
    if (term.length < 2) {
      setResults([]);
      return;
    }
    setLoading(true);
    const id = setTimeout(() => {
      api.get("/search", { params: { q: term, limit: 24 } })
        .then((r) => setResults(r.data.results || []))
        .catch(() => setResults([]))
        .finally(() => setLoading(false));
    }, 250);
    return () => clearTimeout(id);
  }, [q, open]);

  const go = (path) => { navigate(path); onClose(); };
  const openResult = (res) => go(TYPE_ROUTE[res.type] || "/");
  const clearRecent = async () => { await api.delete("/search/recent").catch(() => {}); setRecent([]); };

  const onKeyDown = (e) => {
    if (e.key === "Enter" && results.length > 0) openResult(results[0]);
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          className="fixed inset-0 bg-black/50 z-50 flex items-start justify-center pt-28 p-4"
          onClick={onClose}
          data-testid="command-palette"
        >
          <motion.div
            initial={{ y: -16, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: -16, opacity: 0 }}
            transition={{ duration: 0.15 }}
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-xl bg-card border border-border rounded-md overflow-hidden glass"
          >
            <div className="hairline px-4 py-2.5 flex items-center gap-2">
              <Search size={15} className="text-muted-foreground shrink-0" />
              <input
                ref={inputRef}
                value={q}
                onChange={(e) => setQ(e.target.value)}
                onKeyDown={onKeyDown}
                data-testid="command-search-input"
                placeholder={t("ابحث في كل شيء…", "Search everything…")}
                className="flex-1 bg-transparent outline-none text-sm placeholder:text-muted-foreground"
              />
              {loading && <span className="label-mono text-[10px] animate-pulse">{t("بحث…", "searching")}</span>}
              <span className="font-mono text-[10px] text-muted-foreground">ESC</span>
            </div>

            <div className="max-h-96 overflow-y-auto">
              {q.trim().length >= 2 && (
                <div data-testid="search-results">
                  {results.length === 0 && !loading && (
                    <div className="p-8 text-center text-sm text-muted-foreground">{t("لا نتائج.", "No results.")}</div>
                  )}
                  {results.map((r) => (
                    <button
                      key={`${r.type}-${r.id}`}
                      onClick={() => openResult(r)}
                      className="w-full flex items-center justify-between gap-3 px-4 py-2.5 hover:bg-secondary text-start border-b border-border last:border-0"
                    >
                      <div className="min-w-0">
                        <div className="text-sm truncate">{r.title || r.id}</div>
                        {r.subtitle && <div className="text-xs text-muted-foreground truncate">{r.subtitle}</div>}
                      </div>
                      <span className="label-mono text-[10px] shrink-0">{t(...(TYPE_LABEL[r.type] || [r.type, r.type]))}</span>
                    </button>
                  ))}
                </div>
              )}

              {q.trim().length < 2 && recent.length > 0 && (
                <div>
                  <div className="px-4 pt-3 pb-1 flex items-center justify-between">
                    <span className="label-mono flex items-center gap-1.5"><Clock size={11} /> {t("عمليات بحث حديثة", "Recent")}</span>
                    <button onClick={clearRecent} className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"><X size={11} /> {t("مسح", "Clear")}</button>
                  </div>
                  {recent.map((rc) => (
                    <button key={rc.q} onClick={() => setQ(rc.q)} className="w-full flex items-center justify-between px-4 py-2 hover:bg-secondary text-start text-sm">
                      <span className="text-muted-foreground">{rc.q}</span>
                      <span className="font-mono text-[10px] text-muted-foreground">{rc.hits}</span>
                    </button>
                  ))}
                </div>
              )}

              {q.trim().length < 2 && (
                <div>
                  <div className="px-4 pt-3 pb-1 label-mono">{t("انتقل إلى…", "Jump to…")}</div>
                  {ACTIONS.map((a) => (
                    <button
                      key={a.path}
                      onClick={() => go(a.path)}
                      className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-secondary text-start text-sm border-b border-border last:border-0"
                    >
                      <span>{a.label}</span>
                      <span className="font-mono text-[10px] text-muted-foreground">{a.hint}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="hairline px-4 py-2 flex items-center justify-between text-[10px] text-muted-foreground font-mono">
              <span className="flex items-center gap-1"><CornerDownLeft size={11} /> {t("للفتح", "to open")}</span>
              <span className="flex items-center gap-1"><Command size={11} /> K</span>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
