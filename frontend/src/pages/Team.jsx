import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useLang } from "@/contexts/LanguageContext";
import { Mail, UserPlus, Send, Loader2, Shield, Eye, Edit3, XCircle, Copy } from "lucide-react";
import { toast } from "sonner";

export default function Team() {
  const { t } = useLang();
  const [members, setMembers] = useState([]);
  const [invites, setInvites] = useState([]);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState("viewer");
  const [busy, setBusy] = useState(false);
  const [lastInvite, setLastInvite] = useState(null);

  const load = () => {
    api.get("/team/members").then(r => setMembers(r.data)).catch(() => {});
    api.get("/team/invites").then(r => setInvites(r.data)).catch(() => {});
  };
  useEffect(() => { load(); }, []);

  const invite = async (e) => {
    e.preventDefault();
    if (!email) return;
    setBusy(true);
    try {
      const r = await api.post("/team/invite", { email, name: name || null, role });
      if (r.data.emailed) {
        toast.success(`${t("تم إرسال الدعوة إلى", "Invite sent to")} ${email}`);
        setLastInvite(null);
      } else {
        toast.message(t("تم إنشاء الدعوة لكن البريد فشل — انسخ كلمة المرور المؤقتة وأرسلها يدويًا.", "Invite created but email failed — copy the temp password and send it manually."));
        setLastInvite(r.data);
      }
      setEmail(""); setName("");
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || t("فشل", "Failed"));
    } finally { setBusy(false); }
  };

  const revoke = async (iid) => {
    if (!window.confirm(t("إلغاء هذه الدعوة؟", "Revoke this invite?"))) return;
    await api.delete(`/team/invites/${iid}`);
    load();
  };

  const copyText = (text) => {
    navigator.clipboard.writeText(text);
    toast.success(t("تم النسخ", "Copied"));
  };

  return (
    <div className="p-6 lg:p-8 space-y-6" data-testid="team-page">
      <div>
        <div className="label-mono">{t("تعاون", "Collaboration")}</div>
        <h1 className="text-3xl sm:text-4xl tracking-tight font-medium mt-1">{t("الفريق", "Team")}</h1>
        <p className="text-sm text-muted-foreground mt-1">{t("ادعُ أعضاء الفريق وتتبّع حجم العمل.", "Invite teammates and track workload.")}</p>
      </div>

      <form onSubmit={invite} className="border border-border bg-card rounded-md p-4 grid grid-cols-1 md:grid-cols-[1.4fr_1fr_0.7fr_auto] gap-2" data-testid="invite-form">
        <input value={email} onChange={e => setEmail(e.target.value)} type="email" required
          placeholder="teammate@company.com" data-testid="invite-email" dir="ltr"
          className="px-3 py-2 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary text-left" />
        <input value={name} onChange={e => setName(e.target.value)}
          placeholder={t("الاسم (اختياري)", "Name (optional)")} data-testid="invite-name"
          className="px-3 py-2 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary" />
        <select value={role} onChange={e => setRole(e.target.value)} data-testid="invite-role"
          className="px-3 py-2 bg-background border border-border rounded-md text-sm">
          <option value="viewer">{t("مشاهد", "Viewer")}</option>
          <option value="editor">{t("محرّر", "Editor")}</option>
        </select>
        <button data-testid="invite-submit" disabled={busy} type="submit"
          className="px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:opacity-90 flex items-center gap-2 disabled:opacity-50">
          {busy ? <Loader2 size={13} className="animate-spin" /> : <Send size={13} />} {t("ادعُ", "Invite")}
        </button>
      </form>

      {lastInvite?.temp_password && (
        <div className="border border-amber-500/40 bg-amber-500/5 rounded-md p-4 space-y-2" data-testid="invite-fallback">
          <div className="text-sm font-medium">{t("الإيميل لم يُرسل تلقائيًا. شارك هذه التفاصيل يدويًا:", "Email did not send automatically. Share these details manually:")}</div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs font-mono">
            <div className="flex items-center justify-between bg-background border border-border rounded px-2 py-1.5">
              <span dir="ltr">{lastInvite.email}</span>
              <button onClick={() => copyText(lastInvite.email)} className="text-muted-foreground hover:text-foreground"><Copy size={12} /></button>
            </div>
            <div className="flex items-center justify-between bg-background border border-border rounded px-2 py-1.5">
              <span dir="ltr">{lastInvite.temp_password}</span>
              <button onClick={() => copyText(lastInvite.temp_password)} className="text-muted-foreground hover:text-foreground"><Copy size={12} /></button>
            </div>
          </div>
          <div className="flex items-center justify-between bg-background border border-border rounded px-2 py-1.5 text-xs">
            <span dir="ltr" className="truncate flex-1">{lastInvite.invite_url}</span>
            <button onClick={() => copyText(lastInvite.invite_url)} className="text-muted-foreground hover:text-foreground"><Copy size={12} /></button>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="border border-border bg-card rounded-md">
          <div className="hairline px-5 py-3 flex items-center gap-2"><UserPlus size={13} /><div className="label-mono">{t("الأعضاء", "Members")}</div></div>
          <div className="divide-y divide-border">
            {members.length === 0 && <div className="p-8 text-center text-sm text-muted-foreground">{t("فقط أنت حتى الآن.", "Just you for now.")}</div>}
            {members.map(m => (
              <div key={m.id} className="px-5 py-3 flex items-center justify-between" data-testid={`member-${m.id}`}>
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-full bg-secondary flex items-center justify-center font-mono text-sm font-medium">
                    {m.name?.[0]?.toUpperCase()}
                  </div>
                  <div>
                    <div className="text-sm font-medium flex items-center gap-2">{m.name} {m.is_admin && <Shield size={11} className="text-primary" />}</div>
                    <div className="text-xs text-muted-foreground" dir="ltr">{m.email}</div>
                  </div>
                </div>
                <div className="text-end">
                  <div className="font-mono text-sm">{m.active_tasks}</div>
                  <div className="label-mono text-[9px]">{t("نشطة", "active")}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="border border-border bg-card rounded-md">
          <div className="hairline px-5 py-3 flex items-center gap-2"><Mail size={13} /><div className="label-mono">{t("الدعوات المرسلة", "Sent invites")}</div></div>
          <div className="divide-y divide-border">
            {invites.length === 0 && <div className="p-8 text-center text-sm text-muted-foreground">{t("لا توجد دعوات بعد.", "No invites yet.")}</div>}
            {invites.map(i => (
              <div key={i.id} className="px-5 py-3 flex items-center justify-between" data-testid={`invite-${i.id}`}>
                <div className="flex items-center gap-2">
                  <div className="text-sm" dir="ltr">{i.email}</div>
                  <span className="label-mono text-[9px] flex items-center gap-1">
                    {i.role === "editor" ? <Edit3 size={10} /> : <Eye size={10} />}
                    {i.role}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`label-mono text-[9px] ${i.status === "accepted" ? "text-emerald-500" : i.status === "revoked" ? "text-destructive" : ""}`}>
                    {i.status === "pending" ? t("قيد الانتظار", "pending") : i.status}
                  </span>
                  {i.status === "pending" && (
                    <button onClick={() => revoke(i.id)} className="text-muted-foreground hover:text-destructive" data-testid={`revoke-${i.id}`}>
                      <XCircle size={13} />
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <p className="label-mono text-[10px] text-muted-foreground">{t("لتفعيل إرسال الدعوات تلقائيًا: اذهب إلى الإعدادات > البريد (SMTP).", "To send invites automatically: go to Settings → Email (SMTP).")}</p>
    </div>
  );
}
