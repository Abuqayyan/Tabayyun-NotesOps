import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate, Outlet } from "react-router-dom";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { LanguageProvider } from "@/contexts/LanguageContext";
import { AuthProvider, useAuth } from "@/contexts/AuthContext";
import { Toaster } from "@/components/ui/sonner";

import Login from "@/pages/Login";
import AppShell from "@/components/layout/AppShell";
import Dashboard from "@/pages/Dashboard";
import Projects from "@/pages/Projects";
import ProjectDetail from "@/pages/ProjectDetail";
import Tasks from "@/pages/Tasks";
import Focus from "@/pages/Focus";
import Notes from "@/pages/Notes";
import Team from "@/pages/Team";
import Analytics from "@/pages/Analytics";
import Notifications from "@/pages/Notifications";
import Assistant from "@/pages/Assistant";
import Settings from "@/pages/Settings";
import WeeklyReview from "@/pages/WeeklyReview";
import Memory from "@/pages/Memory";
import Brief from "@/pages/Brief";
import Schedule from "@/pages/Schedule";
import Calendar from "@/pages/Calendar";
import Graph from "@/pages/Graph";
// Phase 6 — platform integration screens
import ExecutiveDashboard from "@/pages/ExecutiveDashboard";
import DailyUpdates from "@/pages/DailyUpdates";
import Meetings from "@/pages/Meetings";
import Approvals from "@/pages/Approvals";
import CRM from "@/pages/CRM";
import KnowledgeBase from "@/pages/KnowledgeBase";
import Organization from "@/pages/Organization";
import OperationsCenter from "@/pages/OperationsCenter";
import SettingsCenter from "@/pages/SettingsCenter";
import NotificationCenter from "@/pages/NotificationCenter";

function Protected() {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="label-mono animate-pulse">loading workspace</div>
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  return (
    <AppShell>
      <Outlet />
    </AppShell>
  );
}

export default function App() {
  return (
    <LanguageProvider>
      <ThemeProvider>
        <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Navigate to="/login" replace />} />
            <Route path="/brief/:token" element={<Brief />} />
            <Route element={<Protected />}>
              <Route path="/" element={<Dashboard />} />
              <Route path="/projects" element={<Projects />} />
              <Route path="/projects/:id" element={<ProjectDetail />} />
              <Route path="/tasks" element={<Tasks />} />
              <Route path="/schedule" element={<Schedule />} />
              <Route path="/calendar" element={<Calendar />} />
              <Route path="/graph" element={<Graph />} />
              <Route path="/graph/:id" element={<Graph />} />
              <Route path="/focus" element={<Focus />} />
              <Route path="/notes" element={<Notes />} />
              <Route path="/team" element={<Team />} />
              <Route path="/analytics" element={<Analytics />} />
              <Route path="/notifications" element={<Notifications />} />
              <Route path="/inbox" element={<NotificationCenter />} />
              <Route path="/assistant" element={<Assistant />} />
              <Route path="/memory" element={<Memory />} />
              <Route path="/review" element={<WeeklyReview />} />
              <Route path="/settings" element={<Settings />} />
              {/* Phase 6 — company platform */}
              <Route path="/executive" element={<ExecutiveDashboard />} />
              <Route path="/daily-updates" element={<DailyUpdates />} />
              <Route path="/meetings" element={<Meetings />} />
              <Route path="/approvals" element={<Approvals />} />
              <Route path="/crm" element={<CRM />} />
              <Route path="/knowledge" element={<KnowledgeBase />} />
              <Route path="/organization" element={<Organization />} />
              <Route path="/ops" element={<OperationsCenter />} />
              <Route path="/settings-center" element={<SettingsCenter />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
        <Toaster position="top-right" richColors />
      </AuthProvider>
    </ThemeProvider>
    </LanguageProvider>
  );
}
