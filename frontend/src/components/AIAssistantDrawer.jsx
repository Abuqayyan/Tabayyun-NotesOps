import { useEffect, useState, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useLang } from "@/contexts/LanguageContext";
import { X, Send, Sparkles, Loader2 } from "lucide-react";
import { api } from "@/lib/api";

export default function AIAssistantDrawer({ open, onClose }) {
  const { t } = useLang();
  const [sessionId, setSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    if (open && messages.length === 0) {
      setMessages([{
        role: "assistant",
        content: t(
          "أنا أوبس‌كور — رئيس عملياتك الذكي. لدي السياق الكامل لمشاريعك ومهامك ومواعيدك وحجم عملك. شو نهاجم أول شي؟",
          "I'm OpsCore — your AI Chief of Operations. I have full context on your projects, tasks, deadlines, and workload. What should we tackle first?"
        )
      }]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = async () => {
    if (!input.trim() || loading) return;
    const msg = input.trim();
    setInput("");
    setMessages((m) => [...m, { role: "user", content: msg }]);
    setLoading(true);
    try {
      const r = await api.post("/ai/chat", { message: msg, session_id: sessionId });
      if (!sessionId) setSessionId(r.data.session_id);
      setMessages((m) => [...m, { role: "assistant", content: r.data.reply }]);
    } catch {
      setMessages((m) => [...m, { role: "assistant", content: t("خطأ في الاتصال. حاول مرة ثانية.", "Connection error. Please try again.") }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/40 z-40"
            onClick={onClose}
          />
          <motion.div
            initial={{ x: "-100%" }} animate={{ x: 0 }} exit={{ x: "-100%" }}
            transition={{ type: "tween", duration: 0.25 }}
            className="fixed top-0 start-0 h-full w-full sm:w-[460px] bg-card border-e border-border z-50 flex flex-col"
            data-testid="ai-drawer"
          >
            <div className="hairline px-5 h-14 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Sparkles size={15} className="text-primary" />
                <div>
                  <div className="text-sm font-medium tracking-tight">{t("رئيس العمليات الذكي", "AI Chief of Operations")}</div>
                  <div className="label-mono text-[9px]">{t("كلود سونيت ٤٫٥", "Claude Sonnet 4.5")}</div>
                </div>
              </div>
              <button onClick={onClose} className="w-8 h-8 flex items-center justify-center rounded-md hover:bg-secondary" data-testid="close-ai-btn">
                <X size={15} />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-5 space-y-4">
              {messages.map((m, i) => (
                <div key={i} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
                  <div className={`max-w-[85%] rounded-md px-3 py-2 text-sm leading-relaxed ${
                    m.role === "user"
                      ? "bg-primary text-primary-foreground"
                      : "bg-secondary text-foreground"
                  }`}>
                    <div className="whitespace-pre-wrap">{m.content}</div>
                  </div>
                </div>
              ))}
              {loading && (
                <div className="flex justify-start">
                  <div className="bg-secondary rounded-md px-3 py-2 text-sm flex items-center gap-2">
                    <Loader2 size={13} className="animate-spin" /> {t("يفكّر…", "Thinking…")}
                  </div>
                </div>
              )}
              <div ref={bottomRef} />
            </div>

            <div className="border-t border-border p-3">
              <div className="flex gap-2">
                <input
                  data-testid="ai-input"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && send()}
                  placeholder={t("اسأل أي شي عن مساحة عملك…", "Ask anything about your workspace…")}
                  className="flex-1 px-3 py-2 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                />
                <button
                  data-testid="ai-send-btn"
                  onClick={send}
                  disabled={loading || !input.trim()}
                  className="px-3 py-2 bg-primary text-primary-foreground rounded-md hover:opacity-90 disabled:opacity-40"
                >
                  <Send size={14} className="rtl:rotate-180" />
                </button>
              </div>
              <div className="label-mono text-[9px] mt-2">{t("⌘J للتبديل · واعٍ بالسياق", "⌘J to toggle · Context-aware")}</div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
