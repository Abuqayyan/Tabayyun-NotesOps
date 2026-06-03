import { useEffect, useState, useRef } from "react";
import { api } from "@/lib/api";
import { useLang } from "@/contexts/LanguageContext";
import { Send, Sparkles, Loader2, Plus } from "lucide-react";

export default function Assistant() {
  const { t } = useLang();
  const [conversations, setConversations] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef(null);

  const loadList = () => api.get("/ai/conversations").then(r => setConversations(r.data));
  useEffect(() => { loadList(); }, []);

  const loadConvo = async (sid) => {
    setActiveId(sid);
    const r = await api.get(`/ai/conversations/${sid}`);
    setMessages(r.data.messages || []);
  };

  const newChat = () => { setActiveId(null); setMessages([{ role: "assistant", content: t("جلسة جديدة. قل لي شو بنهاجم.", "Fresh session. Tell me what we're tackling.") }]); };

  const send = async () => {
    if (!input.trim() || busy) return;
    const msg = input.trim(); setInput("");
    setMessages(m => [...m, { role: "user", content: msg }]);
    setBusy(true);
    try {
      const r = await api.post("/ai/chat", { message: msg, session_id: activeId });
      if (!activeId) setActiveId(r.data.session_id);
      setMessages(m => [...m, { role: "assistant", content: r.data.reply }]);
      loadList();
    } catch { setMessages(m => [...m, { role: "assistant", content: t("خطأ في الاتصال.", "Connection error.") }]); }
    finally { setBusy(false); }
  };

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  return (
    <div className="h-[calc(100vh-3.5rem)] flex" data-testid="assistant-page">
      <div className="w-64 border-e border-border flex flex-col">
        <div className="hairline px-4 h-12 flex items-center justify-between">
          <div className="label-mono">{t("الجلسات", "Sessions")}</div>
          <button onClick={newChat} className="w-7 h-7 hover:bg-secondary rounded-md flex items-center justify-center" data-testid="new-chat-btn"><Plus size={13} /></button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {conversations.length === 0 && <div className="p-4 text-xs text-muted-foreground">{t("لا توجد جلسات", "No sessions")}</div>}
          {conversations.map(c => (
            <button key={c.session_id} onClick={() => loadConvo(c.session_id)}
              className={`w-full text-start px-4 py-3 border-b border-border hover:bg-secondary ${activeId === c.session_id ? "bg-secondary" : ""}`}>
              <div className="text-xs line-clamp-2">{c.preview || t("محادثة جديدة", "New conversation")}</div>
              <div className="label-mono text-[9px] mt-1">{c.message_count} {t("رسالة", "messages")}</div>
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 flex flex-col">
        <div className="hairline px-6 h-12 flex items-center gap-2">
          <Sparkles size={13} className="text-primary" />
          <div className="text-sm font-medium tracking-tight">{t("رئيس العمليات الذكي", "AI Chief of Operations")}</div>
          <div className="label-mono text-[9px]">{t("كلود سونيت ٤٫٥", "Claude Sonnet 4.5")}</div>
        </div>
        <div className="flex-1 overflow-y-auto p-6 space-y-4 max-w-3xl mx-auto w-full">
          {messages.length === 0 && (
            <div className="text-center py-20">
              <Sparkles className="mx-auto text-primary mb-3" size={28} />
              <div className="text-sm text-muted-foreground">{t("اسألني أي شي. عندي السياق الكامل لمساحة عملك.", "Ask me anything. I have full context of your workspace.")}</div>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
              <div className={`max-w-[80%] rounded-md px-4 py-2.5 text-sm leading-relaxed ${m.role === "user" ? "bg-primary text-primary-foreground" : "bg-secondary"}`}>
                <div className="whitespace-pre-wrap">{m.content}</div>
              </div>
            </div>
          ))}
          {busy && <div className="flex justify-start"><div className="bg-secondary rounded-md px-3 py-2 text-sm flex items-center gap-2"><Loader2 size={13} className="animate-spin" /> {t("يفكّر…", "Thinking…")}</div></div>}
          <div ref={bottomRef} />
        </div>
        <div className="border-t border-border p-4 max-w-3xl mx-auto w-full">
          <div className="flex gap-2">
            <input data-testid="assistant-input" value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === "Enter" && send()}
              placeholder={t("على شو أركّز الحين؟", "What should I focus on now?")}
              className="flex-1 px-3 py-2.5 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary" />
            <button data-testid="assistant-send" onClick={send} disabled={busy || !input.trim()}
              className="px-4 bg-primary text-primary-foreground rounded-md hover:opacity-90 disabled:opacity-40"><Send size={14} className="rtl:rotate-180" /></button>
          </div>
        </div>
      </div>
    </div>
  );
}
