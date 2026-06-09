import { NavLink, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { useTheme } from "@/contexts/ThemeContext";
import { useLang } from "@/contexts/LanguageContext";
import {
  LayoutDashboard, FolderGit2, CheckSquare, Timer, NotebookPen,
  BarChart3, Sparkles, Sun, Moon, LogOut, Command,
  Settings as SettingsIcon, Brain, CalendarCheck, Languages, CalendarDays,
  Calendar as CalendarIcon, Network, Crown, ClipboardList, CalendarClock,
  Stamp, BookOpen, Briefcase, Building2, Activity, SlidersHorizontal
} from "lucide-react";
import { motion } from "framer-motion";
import AIAssistantDrawer from "@/components/AIAssistantDrawer";
import CommandPalette from "@/components/CommandPalette";
import NotificationBell from "@/components/NotificationBell";
import { useWebSocket } from "@/lib/useWebSocket";
import { usePermissions } from "@/lib/usePermissions";

export default function AppShell({ children }) {
  const { user, logout } = useAuth();
  const { theme, toggle } = useTheme();
  const { lang, toggle: toggleLang, t } = useLang();
  const { has, hasAny } = usePermissions();
  const navigate = useNavigate();
  const [aiOpen, setAiOpen] = useState(false);
  const [cmdOpen, setCmdOpen] = useState(false);

  // Grouped, permission-aware navigation. `perm` undefined => always visible.
  // Pages also enforce access server-side, so this is defense-in-depth, not the gate.
  const GROUPS = [
    {
      label: t("شخصي", "Personal"),
      items: [
        { to: "/", label: t("لوحة القيادة", "Dashboard"), icon: LayoutDashboard, tid: "nav-dashboard" },
        { to: "/tasks", label: t("المهام", "Tasks"), icon: CheckSquare, tid: "nav-tasks" },
        { to: "/projects", label: t("المشاريع", "Projects"), icon: FolderGit2, tid: "nav-projects" },
        { to: "/schedule", label: t("الجدول الأسبوعي", "Schedule"), icon: CalendarDays, tid: "nav-schedule" },
        { to: "/calendar", label: t("التقويم", "Calendar"), icon: CalendarIcon, tid: "nav-calendar" },
        { to: "/graph", label: t("الرسم البياني", "Graph"), icon: Network, tid: "nav-graph" },
        { to: "/focus", label: t("التركيز", "Focus"), icon: Timer, tid: "nav-focus" },
        { to: "/notes", label: t("الملاحظات", "Notes"), icon: NotebookPen, tid: "nav-notes" },
        { to: "/memory", label: t("الذاكرة", "Memory"), icon: Brain, tid: "nav-memory" },
        { to: "/review", label: t("المراجعة الأسبوعية", "Weekly Review"), icon: CalendarCheck, tid: "nav-review" },
      ],
    },
    {
      label: t("الشركة", "Company"),
      items: [
        { to: "/executive", label: t("لوحة التنفيذيين", "Executive"), icon: Crown, tid: "nav-executive",
          show: () => hasAny("company.dashboard.view", "intelligence.view") },
        { to: "/daily-updates", label: t("التحديثات اليومية", "Daily Updates"), icon: ClipboardList, tid: "nav-daily-updates",
          show: () => hasAny("daily_update.submit", "daily_update.view_team", "daily_update.view_department", "daily_update.view_all") },
        { to: "/meetings", label: t("الاجتماعات", "Meetings"), icon: CalendarClock, tid: "nav-meetings",
          show: () => has("meeting.view") },
        { to: "/approvals", label: t("الموافقات", "Approvals"), icon: Stamp, tid: "nav-approvals",
          show: () => hasAny("approval.create", "approval.view", "approval.approve") },
        { to: "/knowledge", label: t("قاعدة المعرفة", "Knowledge Base"), icon: BookOpen, tid: "nav-knowledge",
          show: () => has("kb.view") },
        { to: "/analytics", label: t("التحليلات", "Analytics"), icon: BarChart3, tid: "nav-analytics" },
      ],
    },
    {
      label: t("إدارة العملاء", "CRM"),
      items: [
        { to: "/crm", label: t("إدارة العملاء", "CRM"), icon: Briefcase, tid: "nav-crm",
          show: () => hasAny("crm.company.view", "crm.contact.view", "crm.lead.view", "crm.opportunity.view") },
      ],
    },
    {
      label: t("الإدارة", "Administration"),
      items: [
        { to: "/organization", label: t("التنظيم", "Organization"), icon: Building2, tid: "nav-organization",
          show: () => hasAny("department.view", "employee.view", "role.view", "role.manage") },
        { to: "/ops", label: t("مركز العمليات", "Operations"), icon: Activity, tid: "nav-ops",
          show: () => has("ops.view") },
        { to: "/settings-center", label: t("التهيئة", "Configuration"), icon: SlidersHorizontal, tid: "nav-settings-center",
          show: () => has("settings.manage") },
        { to: "/settings", label: t("الإعدادات", "Settings"), icon: SettingsIcon, tid: "nav-settings" },
      ],
    },
  ];

  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") { e.preventDefault(); setCmdOpen(true); }
      if ((e.metaKey || e.ctrlKey) && e.key === "j") { e.preventDefault(); setAiOpen((v) => !v); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useWebSocket((payload) => {
    if (payload.event?.startsWith("task.")) {
      window.dispatchEvent(new CustomEvent("opscore:task", { detail: payload }));
    }
  });

  return (
    <div className="min-h-screen flex bg-background text-foreground">
      <aside className="w-64 shrink-0 border-e border-border flex flex-col" data-testid="sidebar">
        <div className="p-5 border-b border-border flex items-center gap-2">
          <div className="w-7 h-7 bg-primary flex items-center justify-center" style={{ borderRadius: 4 }}>
            <span className="text-primary-foreground font-mono font-bold text-sm">O</span>
          </div>
          <div>
            <div className="font-medium text-sm tracking-tight">{t("تبيُّن نوتس‌أوبس", "Tabayyun NotesOps")}</div>
            <div className="label-mono text-[10px]">{t("نظام تشغيل الشركة", "Company Operating System")}</div>
          </div>
        </div>

        <nav className="flex-1 p-3 space-y-3 overflow-y-auto">
          {GROUPS.map((group) => {
            const visible = group.items.filter((it) => !it.show || it.show());
            if (visible.length === 0) return null;
            return (
              <div key={group.label} className="space-y-0.5">
                <div className="label-mono px-3 pt-1 pb-1 text-[10px] opacity-60">{group.label}</div>
                {visible.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={item.to === "/"}
                    data-testid={item.tid}
                    className={({ isActive }) =>
                      `flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors group ${
                        isActive
                          ? "bg-secondary text-foreground"
                          : "text-muted-foreground hover:text-foreground hover:bg-secondary/60"
                      }`
                    }
                  >
                    <item.icon size={15} className="shrink-0" />
                    <span>{item.label}</span>
                  </NavLink>
                ))}
              </div>
            );
          })}
        </nav>

        <div className="p-3 border-t border-border space-y-2">
          <button
            data-testid="open-assistant-btn"
            onClick={() => setAiOpen(true)}
            className="w-full flex items-center justify-between gap-2 px-3 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:opacity-90 transition-opacity"
          >
            <span className="flex items-center gap-2"><Sparkles size={14} /> {t("المساعد الذكي", "AI Assistant")}</span>
            <span className="font-mono text-[10px] opacity-70">⌘J</span>
          </button>
          <button
            data-testid="open-command-btn"
            onClick={() => setCmdOpen(true)}
            className="w-full flex items-center justify-between gap-2 px-3 py-2 border border-border rounded-md text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            <span className="flex items-center gap-2"><Command size={14} /> {t("الأوامر", "Commands")}</span>
            <span className="font-mono text-[10px]">⌘K</span>
          </button>
        </div>
      </aside>

      <div className="flex-1 flex flex-col min-w-0">
        <header className="hairline px-6 h-14 flex items-center justify-between sticky top-0 glass z-30">
          <div className="flex items-center gap-3">
            <div className="label-mono">{t("المساحة", "Workspace")}</div>
            <div className="text-sm font-medium tracking-tight">{user?.name}</div>
          </div>
          <div className="flex items-center gap-2">
            <NotificationBell />
            <button
              data-testid="lang-toggle-btn"
              onClick={toggleLang}
              className="h-9 px-3 flex items-center gap-1.5 rounded-md border border-border hover:bg-secondary transition-colors text-xs font-mono"
              title={t("تبديل اللغة", "Toggle language")}
              aria-label={t("تبديل اللغة", "Toggle language")}
            >
              <Languages size={14} />
              <span className="uppercase">{lang === "ar" ? "EN" : "AR"}</span>
            </button>
            <button
              data-testid="theme-toggle-btn"
              onClick={toggle}
              className="w-9 h-9 flex items-center justify-center rounded-md border border-border hover:bg-secondary transition-colors"
              title={t("تبديل المظهر", "Toggle theme")}
            >
              {theme === "dark" ? <Sun size={15} /> : <Moon size={15} />}
            </button>
            <button
              data-testid="logout-btn"
              onClick={logout}
              className="w-9 h-9 flex items-center justify-center rounded-md border border-border hover:bg-secondary transition-colors"
              title={t("خروج", "Sign out")}
            >
              <LogOut size={15} />
            </button>
            <div className="ms-2 flex items-center gap-2 ps-3 border-s border-border">
              <div className="w-8 h-8 rounded-full bg-secondary flex items-center justify-center font-mono text-sm font-medium">
                {user?.name?.[0]?.toUpperCase() || "U"}
              </div>
            </div>
          </div>
        </header>

        <motion.main
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.2 }}
          className="flex-1 overflow-y-auto"
        >
          {children}
        </motion.main>
      </div>

      <AIAssistantDrawer open={aiOpen} onClose={() => setAiOpen(false)} />
      <CommandPalette open={cmdOpen} onClose={() => setCmdOpen(false)} navigate={navigate} />
    </div>
  );
}
