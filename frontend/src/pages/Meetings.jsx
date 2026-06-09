import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { useLang } from "@/contexts/LanguageContext";
import { usePermissions } from "@/lib/usePermissions";
import { PageHeader, Section, Empty, Loading, Field, Input, Textarea, Modal, PrimaryButton, GhostButton, Badge } from "@/components/kit";
import ExportMenu from "@/components/ExportMenu";
import { CalendarClock, Plus, Sparkles, ListChecks, XCircle } from "lucide-react";
import { toast } from "sonner";

const STATUS_TONE = { scheduled: "blue", completed: "green", cancelled: "muted" };

export default function Meetings() {
  const { t, lang } = useLang();
  const { has } = usePermissions();
  const [rows, setRows] = useState(null);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ title: "", meeting_at: "", agenda: "" });
  const [detail, setDetail] = useState(null);
  const locale = lang === "ar" ? "ar-EG" : "en-US";

  const load = useCallback(() => {
    api.get("/meetings", { params: { limit: 100 } }).then((r) => setRows(r.data)).catch(() => setRows([]));
  }, []);
  useEffect(() => { load(); }, [load]);

  const create = async () => {
    if (!form.title.trim()) return toast.error(t("أدخل العنوان", "Enter a title"));
    try {
      await api.post("/meetings", form);
      toast.success(t("تم إنشاء الاجتماع", "Meeting created"));
      setOpen(false); setForm({ title: "", meeting_at: "", agenda: "" }); load();
    } catch (e) { toast.error(e?.response?.data?.detail || t("فشل", "Failed")); }
  };

  return (
    <div className="p-6 lg:p-8 space-y-6" data-testid="meetings-page">
      <PageHeader label={t("العمليات", "Operations")} title={t("الاجتماعات", "Meetings")}
        subtitle={t("جدول الاجتماعات، المحاضر، وبنود العمل.", "Schedule meetings, minutes, and action items.")}
        actions={<>
          {has("export.data") && <ExportMenu entity="meetings" />}
          {has("meeting.create") && <PrimaryButton data-testid="meeting-new-btn" onClick={() => setOpen(true)}><Plus size={14} /> {t("اجتماع جديد", "New meeting")}</PrimaryButton>}
        </>} />

      {rows === null ? <Loading label={t("تحميل الاجتماعات…", "Loading meetings…")} /> : (
        <Section>
          <div className="divide-y divide-border">
            {rows.length === 0 && <Empty>{t("لا اجتماعات.", "No meetings yet.")}</Empty>}
            {rows.map((m) => (
              <button key={m.id} onClick={() => setDetail(m)} data-testid="meeting-row"
                className="w-full text-start px-5 py-3 flex items-center justify-between gap-3 hover:bg-secondary/50">
                <div className="min-w-0">
                  <div className="text-sm font-medium truncate">{m.title}</div>
                  <div className="text-xs text-muted-foreground flex items-center gap-1"><CalendarClock size={11} /> {m.meeting_at ? new Date(m.meeting_at).toLocaleString(locale) : t("غير مجدول", "Unscheduled")}</div>
                </div>
                <Badge tone={STATUS_TONE[m.status]}>{m.status}</Badge>
              </button>
            ))}
          </div>
        </Section>
      )}

      <Modal open={open} onClose={() => setOpen(false)} title={t("اجتماع جديد", "New meeting")}
        footer={<><GhostButton onClick={() => setOpen(false)}>{t("إلغاء", "Cancel")}</GhostButton><PrimaryButton data-testid="meeting-create" onClick={create}>{t("إنشاء", "Create")}</PrimaryButton></>}>
        <Field label={t("العنوان", "Title")}><Input data-testid="meeting-title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></Field>
        <Field label={t("التاريخ والوقت", "Date & time")}><Input type="datetime-local" value={form.meeting_at} onChange={(e) => setForm({ ...form, meeting_at: e.target.value ? `${e.target.value}:00` : "" })} /></Field>
        <Field label={t("جدول الأعمال", "Agenda")}><Textarea rows={3} value={form.agenda} onChange={(e) => setForm({ ...form, agenda: e.target.value })} /></Field>
      </Modal>

      {detail && <MeetingDetail meeting={detail} onClose={() => { setDetail(null); load(); }} canEdit={has("meeting.edit") || has("meeting.mom.edit")} canCancel={has("meeting.cancel")} />}
    </div>
  );
}

function MeetingDetail({ meeting, onClose, canEdit, canCancel }) {
  const { t } = useLang();
  const [mom, setMom] = useState({ notes: "", decisions: "", discussion_points: "" });
  const [items, setItems] = useState([]);
  const [newItem, setNewItem] = useState({ title: "", due_in_days: 7 });
  const [summary, setSummary] = useState(null);

  const loadItems = useCallback(() => {
    api.get(`/meetings/${meeting.id}/action-items`).then((r) => setItems(r.data || [])).catch(() => {});
  }, [meeting.id]);

  useEffect(() => {
    api.get(`/meetings/${meeting.id}/mom`).then((r) => setMom({
      notes: r.data.notes || "",
      decisions: (r.data.decisions || []).join("\n"),
      discussion_points: (r.data.discussion_points || []).join("\n"),
    })).catch(() => {});
    loadItems();
  }, [meeting.id, loadItems]);

  const saveMom = async () => {
    try {
      await api.put(`/meetings/${meeting.id}/mom`, {
        notes: mom.notes,
        decisions: mom.decisions.split("\n").map((s) => s.trim()).filter(Boolean),
        discussion_points: mom.discussion_points.split("\n").map((s) => s.trim()).filter(Boolean),
      });
      toast.success(t("تم حفظ المحضر", "Minutes saved"));
    } catch (e) { toast.error(t("فشل الحفظ", "Save failed")); }
  };

  const addItem = async () => {
    if (!newItem.title.trim()) return;
    try {
      await api.post(`/meetings/${meeting.id}/action-items`, newItem);
      setNewItem({ title: "", due_in_days: 7 });
      loadItems();
      toast.success(t("أُضيف بند العمل وأُنشئت مهمة", "Action item added — task created"));
    } catch (e) { toast.error(e?.response?.data?.detail || t("فشل", "Failed")); }
  };

  const genSummary = async () => {
    try {
      const r = await api.post(`/intelligence/summaries/meeting/${meeting.id}`);
      setSummary(r.data);
    } catch (e) { toast.error(e?.response?.data?.detail || t("غير متاح", "Unavailable")); }
  };

  const cancel = async () => {
    try { await api.post(`/meetings/${meeting.id}/cancel`); toast.success(t("أُلغي الاجتماع", "Meeting cancelled")); onClose(); }
    catch (e) { toast.error(t("فشل", "Failed")); }
  };

  return (
    <Modal open onClose={onClose} wide title={meeting.title}
      footer={<>
        {canCancel && meeting.status !== "cancelled" && <GhostButton onClick={cancel}><XCircle size={14} /> {t("إلغاء الاجتماع", "Cancel meeting")}</GhostButton>}
        <GhostButton data-testid="meeting-summary-btn" onClick={genSummary}><Sparkles size={14} /> {t("ملخص ذكي", "AI summary")}</GhostButton>
        {canEdit && <PrimaryButton data-testid="mom-save" onClick={saveMom}>{t("حفظ المحضر", "Save minutes")}</PrimaryButton>}
      </>}>
      {summary && (
        <div className="border border-primary/40 bg-card rounded-md p-4">
          <div className="label-mono mb-1 flex items-center gap-1"><Sparkles size={12} className="text-primary" /> {t("ملخص تنفيذي", "Executive summary")}</div>
          <div className="text-sm text-muted-foreground">{summary.narrative}</div>
        </div>
      )}
      <Field label={t("ملاحظات المحضر", "Minutes notes")}><Textarea rows={3} value={mom.notes} disabled={!canEdit} onChange={(e) => setMom({ ...mom, notes: e.target.value })} /></Field>
      <div className="grid md:grid-cols-2 gap-4">
        <Field label={t("القرارات (سطر لكل قرار)", "Decisions (one per line)")}><Textarea rows={3} value={mom.decisions} disabled={!canEdit} onChange={(e) => setMom({ ...mom, decisions: e.target.value })} /></Field>
        <Field label={t("نقاط النقاش", "Discussion points")}><Textarea rows={3} value={mom.discussion_points} disabled={!canEdit} onChange={(e) => setMom({ ...mom, discussion_points: e.target.value })} /></Field>
      </div>

      <div>
        <div className="label-mono mb-2 flex items-center gap-1"><ListChecks size={12} /> {t("بنود العمل", "Action items")}</div>
        <div className="space-y-1.5">
          {items.length === 0 && <div className="text-sm text-muted-foreground">{t("لا بنود.", "None yet.")}</div>}
          {items.map((it) => (
            <div key={it.id} className="flex items-center justify-between border border-border rounded-md px-3 py-2">
              <span className="text-sm truncate">{it.title}</span>
              <Badge tone={it.status === "done" ? "green" : it.status === "in_progress" ? "blue" : "amber"}>{it.status}</Badge>
            </div>
          ))}
        </div>
        {canEdit && (
          <div className="flex items-end gap-2 mt-2">
            <div className="flex-1"><Input data-testid="action-item-title" placeholder={t("بند عمل جديد…", "New action item…")} value={newItem.title} onChange={(e) => setNewItem({ ...newItem, title: e.target.value })} /></div>
            <div className="w-24"><Input type="number" value={newItem.due_in_days} onChange={(e) => setNewItem({ ...newItem, due_in_days: Number(e.target.value) })} /></div>
            <PrimaryButton data-testid="action-item-add" onClick={addItem}><Plus size={14} /></PrimaryButton>
          </div>
        )}
      </div>
    </Modal>
  );
}
