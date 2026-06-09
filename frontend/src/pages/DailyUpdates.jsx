import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { useLang } from "@/contexts/LanguageContext";
import { PageHeader, Section, Empty, Loading, Field, Textarea, PrimaryButton } from "@/components/kit";
import { ClipboardList, CheckCircle2, CalendarDays, AlertOctagon } from "lucide-react";
import { toast } from "sonner";

export default function DailyUpdates() {
  const { t, lang } = useLang();
  const [list, setList] = useState(null);
  const [today, setToday] = useState(null);
  const [form, setForm] = useState({ today: "", tomorrow: "", blockers: "" });
  const [busy, setBusy] = useState(false);
  const locale = lang === "ar" ? "ar-EG" : "en-US";

  const load = useCallback(() => {
    api.get("/daily-updates", { params: { limit: 100 } }).then((r) => setList(r.data)).catch(() => setList([]));
    api.get("/daily-updates/me/today").then((r) => {
      setToday(r.data);
      if (r.data) setForm({ today: r.data.today || "", tomorrow: r.data.tomorrow || "", blockers: r.data.blockers || "" });
    }).catch(() => {});
  }, []);
  useEffect(() => { load(); }, [load]);

  const submit = async () => {
    setBusy(true);
    try {
      if (today) await api.patch(`/daily-updates/${today.id}`, form);
      else await api.post("/daily-updates", form);
      toast.success(t("تم حفظ التحديث", "Update saved"));
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || t("فشل الحفظ", "Save failed"));
    } finally { setBusy(false); }
  };

  if (list === null) return <Loading label={t("تحميل التحديثات…", "Loading updates…")} />;

  return (
    <div className="p-6 lg:p-8 space-y-6" data-testid="daily-updates-page">
      <PageHeader label={t("العمليات اليومية", "Daily operations")} title={t("التحديثات اليومية", "Daily Updates")}
        subtitle={t("ماذا أنجزت، وماذا ستفعل غدًا، وما العوائق.", "What got done, what's next, and any blockers.")} />

      <Section title={today ? t("تحديث اليوم (تحرير)", "Today's update (editing)") : t("إرسال تحديث اليوم", "Submit today's update")}>
        <div className="p-5 space-y-4">
          <Field label={t("أُنجز اليوم", "Completed today")}>
            <Textarea data-testid="du-today" rows={2} value={form.today} onChange={(e) => setForm({ ...form, today: e.target.value })} />
          </Field>
          <Field label={t("خطة الغد", "Planned for tomorrow")}>
            <Textarea data-testid="du-tomorrow" rows={2} value={form.tomorrow} onChange={(e) => setForm({ ...form, tomorrow: e.target.value })} />
          </Field>
          <Field label={t("العوائق", "Blockers")}>
            <Textarea data-testid="du-blockers" rows={2} value={form.blockers} onChange={(e) => setForm({ ...form, blockers: e.target.value })} />
          </Field>
          <div className="flex justify-end">
            <PrimaryButton data-testid="du-submit" onClick={submit} disabled={busy}>
              <CheckCircle2 size={14} /> {busy ? t("جارٍ الحفظ…", "Saving…") : today ? t("تحديث", "Update") : t("إرسال", "Submit")}
            </PrimaryButton>
          </div>
        </div>
      </Section>

      <Section title={t("تحديثات الفريق", "Team updates")} actions={<span className="label-mono">{list.length}</span>}>
        <div className="divide-y divide-border">
          {list.length === 0 && <Empty>{t("لا توجد تحديثات بعد.", "No updates yet.")}</Empty>}
          {list.map((u) => (
            <div key={u.id} className="px-5 py-4" data-testid="du-row">
              <div className="flex items-center justify-between">
                <div className="text-sm font-medium">{u.user_name || u.user_id}</div>
                <span className="font-mono text-xs text-muted-foreground flex items-center gap-1"><CalendarDays size={11} /> {new Date(u.update_date).toLocaleDateString(locale)}</span>
              </div>
              <div className="grid md:grid-cols-3 gap-3 mt-2 text-sm">
                <div><div className="label-mono mb-1 flex items-center gap-1"><CheckCircle2 size={11} className="text-emerald-500" /> {t("أُنجز", "Done")}</div><div className="text-muted-foreground whitespace-pre-wrap">{u.today || "—"}</div></div>
                <div><div className="label-mono mb-1 flex items-center gap-1"><ClipboardList size={11} /> {t("غدًا", "Next")}</div><div className="text-muted-foreground whitespace-pre-wrap">{u.tomorrow || "—"}</div></div>
                <div><div className="label-mono mb-1 flex items-center gap-1"><AlertOctagon size={11} className="text-amber-500" /> {t("عوائق", "Blockers")}</div><div className="text-muted-foreground whitespace-pre-wrap">{u.blockers || "—"}</div></div>
              </div>
            </div>
          ))}
        </div>
      </Section>
    </div>
  );
}
