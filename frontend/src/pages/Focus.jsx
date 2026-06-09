import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useLang } from "@/contexts/LanguageContext";
import { Play, Pause, RotateCcw, CheckCircle2, Timer as TimerIcon } from "lucide-react";
import { toast } from "sonner";
import { motion } from "framer-motion";

function playCompletionSound() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const o = ctx.createOscillator();
    const g = ctx.createGain();
    o.connect(g); g.connect(ctx.destination);
    o.type = "sine"; o.frequency.value = 880;
    g.gain.setValueAtTime(0.0001, ctx.currentTime);
    g.gain.exponentialRampToValueAtTime(0.3, ctx.currentTime + 0.05);
    o.frequency.linearRampToValueAtTime(1320, ctx.currentTime + 0.3);
    g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 1.2);
    o.start(); o.stop(ctx.currentTime + 1.3);
  } catch { /* noop */ }
}

export default function Focus() {
  const { t } = useLang();
  const MODES = [
    { key: "pomodoro", label: t("بومودورو", "Pomodoro"), minutes: 25 },
    { key: "deep_work", label: t("تركيز عميق", "Deep work"), minutes: 50 },
    { key: "sprint", label: t("سبرنت", "Sprint"), minutes: 15 },
  ];
  const [mode, setMode] = useState(MODES[0]);
  const [running, setRunning] = useState(false);
  const [remaining, setRemaining] = useState(MODES[0].minutes * 60);
  const [tasks, setTasks] = useState([]);
  const [selectedTask, setSelectedTask] = useState("");
  const [done, setDone] = useState(false);
  const intervalRef = useRef(null);

  useEffect(() => {
    api.get("/tasks").then(r => setTasks(r.data.filter(tk => tk.status !== "done")));
  }, []);

  useEffect(() => {
    if (running && remaining > 0) {
      intervalRef.current = setInterval(() => setRemaining(r => r - 1), 1000);
    } else {
      clearInterval(intervalRef.current);
    }
    return () => clearInterval(intervalRef.current);
  }, [running, remaining]);

  useEffect(() => {
    if (remaining === 0 && running) {
      setRunning(false);
      setDone(true);
      playCompletionSound();
      api.post("/focus/sessions", {
        task_id: selectedTask || null,
        duration_minutes: mode.minutes,
        mode: mode.key,
        completed: true,
      }).then(() => toast.success(t("تم تسجيل الجلسة", "Session logged")));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [remaining, running, mode.minutes, mode.key, selectedTask]);

  const start = () => { setDone(false); setRunning(true); };
  const pause = () => setRunning(false);
  const reset = () => { setRunning(false); setRemaining(mode.minutes * 60); setDone(false); };
  const switchMode = (m) => { setMode(m); setRemaining(m.minutes * 60); setRunning(false); setDone(false); };

  const min = Math.floor(remaining / 60);
  const sec = remaining % 60;
  const pct = ((mode.minutes * 60 - remaining) / (mode.minutes * 60)) * 100;
  const selectedTaskObj = tasks.find(tk => tk.id === selectedTask);

  return (
    <div className="min-h-[calc(100vh-3.5rem)] p-8 flex flex-col items-center justify-center relative" data-testid="focus-page">
      <div className="absolute inset-0 grid-bg opacity-20 pointer-events-none" />

      <div className="relative z-10 w-full max-w-xl space-y-8">
        <div className="text-center">
          <div className="label-mono flex items-center justify-center gap-2"><TimerIcon size={11} /> {t("وضع العمل العميق", "Deep work mode")}</div>
          <h1 className="text-3xl sm:text-4xl tracking-tight font-medium mt-2">{t("جلسة تركيز", "Focus session")}</h1>
        </div>

        <div className="flex justify-center gap-2">
          {MODES.map(m => (
            <button key={m.key} onClick={() => switchMode(m)} data-testid={`mode-${m.key}`}
              className={`px-4 py-1.5 rounded-md text-sm border ${mode.key === m.key ? "bg-primary text-primary-foreground border-primary" : "border-border text-muted-foreground hover:text-foreground"}`}>
              {m.label} · {m.minutes} {t("د", "min")}
            </button>
          ))}
        </div>

        <div className="relative aspect-square max-w-sm mx-auto">
          <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
            <circle cx="50" cy="50" r="46" fill="none" stroke="hsl(var(--border))" strokeWidth="1" />
            <motion.circle
              cx="50" cy="50" r="46" fill="none"
              stroke="hsl(var(--primary))" strokeWidth="2"
              strokeDasharray={2 * Math.PI * 46}
              strokeDashoffset={(1 - pct / 100) * 2 * Math.PI * 46}
              strokeLinecap="round"
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <div className="data-number text-7xl font-mono">{String(min).padStart(2, "0")}:{String(sec).padStart(2, "0")}</div>
            <div className="label-mono mt-2">{running ? t("في تركيز", "Focusing") : done ? t("اكتملت", "Complete") : t("جاهز", "Ready")}</div>
            {selectedTaskObj && <div className="text-sm text-muted-foreground mt-3 max-w-xs text-center line-clamp-2">{selectedTaskObj.title}</div>}
          </div>
        </div>

        {done && (
          <motion.div initial={{ scale: 0.9, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
            className="border border-primary bg-card rounded-md p-5 text-center vermilion-glow">
            <CheckCircle2 className="mx-auto text-primary mb-2" size={28} />
            <div className="text-sm">{t("اكتملت الجلسة. خذ استراحة أو رتّب المهمة التالية.", "Session complete. Take a break or queue the next task.")}</div>
          </motion.div>
        )}

        <div className="flex items-center justify-center gap-3">
          {!running ? (
            <button data-testid="focus-start" onClick={start} className="px-6 py-3 bg-primary text-primary-foreground rounded-md font-medium flex items-center gap-2 hover:opacity-90"><Play size={15} /> {t("ابدأ", "Start")}</button>
          ) : (
            <button data-testid="focus-pause" onClick={pause} className="px-6 py-3 bg-primary text-primary-foreground rounded-md font-medium flex items-center gap-2 hover:opacity-90"><Pause size={15} /> {t("أوقف", "Pause")}</button>
          )}
          <button data-testid="focus-reset" onClick={reset} className="px-4 py-3 border border-border rounded-md hover:bg-secondary"><RotateCcw size={15} /></button>
        </div>

        <div>
          <div className="label-mono mb-2 text-center">{t("اربط بمهمة", "Link to a task")}</div>
          <select value={selectedTask} onChange={e => setSelectedTask(e.target.value)} data-testid="focus-task-select"
            className="w-full px-3 py-2 bg-background border border-border rounded-md text-sm">
            <option value="">{t("بدون مهمة", "No task")}</option>
            {tasks.map(tk => <option key={tk.id} value={tk.id}>{tk.title}</option>)}
          </select>
        </div>
      </div>
    </div>
  );
}
