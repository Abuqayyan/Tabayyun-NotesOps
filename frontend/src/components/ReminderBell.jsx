import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useLang } from "@/contexts/LanguageContext";
import { Bell, BellOff, Plus, X, Trash2, Loader2, Clock, Send, Zap, Users } from "lucide-react";
import { toast } from "sonner";

/**
 * Professional reminder popover for a task or note.
 * - Quick offsets (Now, 15m, 30m, 1h, 1d before due_date)
 * - Recipient multi-select (defaults to assignee for tasks, owner for notes)
 * - "Send now" instant fire
 * - Custom datetime
 */
export default function ReminderBell({ entityType, entityId, size = 13, compact = false, entity = null }) {
  const { lang, t } = useLang();
  const [open, setOpen] = useState(false);
  const [list, setList] = useState([]);
  const [members, setMembers] = useState([]);
  const [busy, setBusy] = useState(false);
  const [fireAt, setFireAt] = useState("");
  const [message, setMessage] = useState("");
  const [recipients, setRecipients] = useState([]); // user ids
  const [defaultOffsets, setDefaultOffsets] = useState([0, 15, 60, 1440]);

  const load = async () => {
    try {
      const r = await api.get("/reminders", { params: { entity_type: entityType, entity_id: entityId } });
      setList(r.data || []);
    } catch { /* ignore */ }
  };

  useEffect(() => {
    if (!open) return;
    load();
    api.get("/team/members").then(r => setMembers(r.data || [])).catch(() => {});
    api.get("/settings/reminders").then(r => {
      const off = r.data?.workspace?.default_offsets_minutes;
      if (Array.isArray(off) && off.length) setDefaultOffsets(off);
    }).catch(() => {});
    // eslint-disable-next-line
  }, [open, entityId]);

  const toggleRecipient = (uid) => {
    setRecipients(r => r.includes(uid) ? r.filter(x => x !== uid) : [...r, uid]);
  };

  const createReminder = async (payload) => {
    setBusy(true);
    try {
      await api.post("/reminders", {
        entity_type: entityType,
        entity_id: entityId,
        recipient_ids: recipients.length ? recipients : undefined,
        message: message || null,
        channel: "email",
        ...payload,
      });
      toast.success(t("تم ضبط التذكير", "Reminder set"));
      setFireAt(""); setMessage("");
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || t("فشل", "Failed"));
    } finally { setBusy(false); }
  };

  const submitCustom = async (e) => {
    e.preventDefault();
    if (!fireAt) return;
    await createReminder({ fire_at: new Date(fireAt).toISOString() });
  };

  const quickAdd = async (offsetMinutes) => {
    if (offsetMinutes === 0) {
      // Send now via /reminders/send-now (ephemeral, no fire_at needed)
      setBusy(true);
      try {
        const r = await api.post("/reminders/send-now", {
          entity_type: entityType,
          entity_id: entityId,
          recipient_ids: recipients.length ? recipients : undefined,
          message: message || null,
        });
        if (r.data.ok) toast.success(`${t("تم الإرسال إلى", "Sent to")} ${r.data.sent_to}`);
        else toast.error(t("فشل الإرسال — تأكد من إعداد SMTP", "Send failed — check SMTP setup"));
      } catch (err) {
        toast.error(err?.response?.data?.detail || t("فشل", "Failed"));
      } finally { setBusy(false); }
      return;
    }
    await createReminder({ offset_minutes: offsetMinutes });
  };

  const sendNowExisting = async (rid) => {
    setBusy(true);
    try {
      const r = await api.post("/reminders/send-now", { reminder_id: rid });
      if (r.data.ok) toast.success(`${t("تم الإرسال", "Sent")} (${r.data.sent_to})`);
      else toast.error(t("فشل الإرسال", "Send failed"));
      load();
    } catch (err) { toast.error(err?.response?.data?.detail || t("فشل", "Failed")); }
    finally { setBusy(false); }
  };

  const remove = async (rid) => {
    try { await api.delete(`/reminders/${rid}`); load(); toast.success(t("حُذف", "Removed")); }
    catch { toast.error(t("فشل", "Failed")); }
  };

  const upcoming = list.filter(r => !r.sent && r.enabled).length;
  const locale = lang === "ar" ? "ar-EG" : "en-US";

  const OFFSET_LABELS = {
    0: t("الآن", "Now"),
    15: t("قبل ١٥د", "15m before"),
    30: t("قبل ٣٠د", "30m before"),
    60: t("قبل ساعة", "1h before"),
    1440: t("قبل يوم", "1d before"),
  };

  return (
    <div className="relative inline-flex">
      <button
        type="button"
        data-testid={`reminder-toggle-${entityId}`}
        onClick={(e) => { e.stopPropagation(); setOpen(!open); }}
        className={`relative ${compact ? "w-7 h-7" : "w-8 h-8"} rounded-md hover:bg-secondary flex items-center justify-center transition-colors ${upcoming > 0 ? "text-primary" : "text-muted-foreground"}`}
        title={t("التذكيرات", "Reminders")}
      >
        {upcoming > 0 ? <Bell size={size} /> : <BellOff size={size} />}
        {upcoming > 0 && (
          <span className="absolute -top-0.5 -end-0.5 text-[9px] bg-primary text-primary-foreground rounded-full w-3.5 h-3.5 flex items-center justify-center font-mono">{upcoming}</span>
        )}
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute z-50 mt-1 end-0 top-full w-[340px] bg-card border border-border rounded-lg shadow-2xl p-3 space-y-3" onClick={(e) => e.stopPropagation()} data-testid={`reminder-popover-${entityId}`}>
            <div className="flex items-center justify-between">
              <div className="label-mono flex items-center gap-1.5"><Clock size={11} /> {t("التذكيرات", "Reminders")}</div>
              <button onClick={() => setOpen(false)} className="text-muted-foreground hover:text-foreground"><X size={12} /></button>
            </div>

            {/* Recipients */}
            <div className="space-y-1.5">
              <div className="label-mono text-[9px] flex items-center gap-1"><Users size={10} /> {t("المستلمون", "Recipients")} <span className="text-muted-foreground">· {recipients.length === 0 ? t("افتراضي", "default") : recipients.length}</span></div>
              <div className="flex flex-wrap gap-1 max-h-[68px] overflow-y-auto">
                {members.length === 0 ? (
                  <span className="text-[10px] text-muted-foreground">{t("فقط أنت", "Just you")}</span>
                ) : members.map(m => (
                  <button
                    key={m.id}
                    type="button"
                    onClick={() => toggleRecipient(m.id)}
                    data-testid={`recipient-${m.id}`}
                    className={`px-2 py-0.5 text-[10px] rounded-md border transition-colors ${recipients.includes(m.id) ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground hover:text-foreground"}`}
                  >
                    {m.name?.split(" ")[0] || m.email}
                  </button>
                ))}
              </div>
            </div>

            {/* Quick offsets */}
            <div className="space-y-1.5">
              <div className="label-mono text-[9px]">{t("سريع", "Quick")}</div>
              <div className="flex flex-wrap gap-1">
                {defaultOffsets.map(off => (
                  <button
                    key={off}
                    type="button"
                    disabled={busy}
                    onClick={() => quickAdd(off)}
                    data-testid={`offset-${off}`}
                    className={`px-2 py-1 text-[10px] rounded-md border ${off === 0 ? "border-primary bg-primary text-primary-foreground hover:opacity-90" : "border-border hover:bg-secondary"} disabled:opacity-50 flex items-center gap-1`}
                  >
                    {off === 0 ? <Send size={9} /> : <Zap size={9} />}
                    {OFFSET_LABELS[off] || `-${off}${t("د", "m")}`}
                  </button>
                ))}
              </div>
              {entityType === "task" && (
                <div className="text-[9px] text-muted-foreground">{t("الإزاحات تحتاج موعد نهائي للمهمة", "Offsets need a task due date")}</div>
              )}
            </div>

            {/* Custom datetime */}
            <form onSubmit={submitCustom} className="space-y-1.5 border-t border-border pt-2.5">
              <div className="label-mono text-[9px]">{t("وقت مخصص", "Custom time")}</div>
              <input
                type="datetime-local" value={fireAt} onChange={e => setFireAt(e.target.value)}
                data-testid={`reminder-time-${entityId}`}
                className="w-full px-2.5 py-1.5 bg-background border border-border rounded-md text-xs focus:outline-none focus:ring-1 focus:ring-primary"
              />
              <input
                value={message} onChange={e => setMessage(e.target.value)}
                placeholder={t("رسالة (اختياري)", "Message (optional)")}
                data-testid={`reminder-message-${entityId}`}
                className="w-full px-2.5 py-1.5 bg-background border border-border rounded-md text-xs focus:outline-none focus:ring-1 focus:ring-primary"
              />
              <button type="submit" disabled={busy || !fireAt} data-testid={`reminder-add-${entityId}`}
                className="w-full px-3 py-1.5 bg-primary text-primary-foreground rounded-md text-xs font-medium hover:opacity-90 disabled:opacity-50 flex items-center justify-center gap-1.5">
                {busy ? <Loader2 size={11} className="animate-spin" /> : <Plus size={11} />} {t("أضف تذكير", "Add reminder")}
              </button>
            </form>

            {/* Existing list */}
            <div className="border-t border-border pt-2 space-y-1 max-h-48 overflow-y-auto">
              {list.length === 0 ? (
                <div className="text-xs text-muted-foreground text-center py-2">{t("لا توجد تذكيرات", "No reminders")}</div>
              ) : (
                list.map(r => (
                  <div key={r.id} className="flex items-center justify-between gap-2 px-2 py-1.5 rounded hover:bg-secondary text-xs">
                    <div className="min-w-0 flex-1">
                      <div className="font-mono text-[11px]">{new Date(r.fire_at).toLocaleString(locale, { dateStyle: "short", timeStyle: "short" })}</div>
                      {r.message && <div className="text-muted-foreground truncate">{r.message}</div>}
                      <div className="label-mono text-[9px] mt-0.5 flex items-center gap-1.5">
                        <span className={r.sent ? "text-emerald-500" : "text-amber-500"}>{r.sent ? t("أُرسل", "sent") : t("قادم", "upcoming")}</span>
                        <span>·</span>
                        <span>{(r.recipient_ids || []).length} {t("مستلم", "recipient(s)")}</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-0.5 shrink-0">
                      <button onClick={() => sendNowExisting(r.id)} disabled={busy} className="w-6 h-6 rounded hover:bg-primary/10 text-primary disabled:opacity-50 flex items-center justify-center" title={t("أرسل الآن", "Send now")} data-testid={`reminder-fire-${r.id}`}>
                        <Send size={10} />
                      </button>
                      <button onClick={() => remove(r.id)} className="w-6 h-6 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive flex items-center justify-center" data-testid={`reminder-del-${r.id}`}>
                        <Trash2 size={10} />
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
