import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { useLang } from "@/contexts/LanguageContext";
import { usePermissions } from "@/lib/usePermissions";
import { PageHeader, Section, Empty, Loading, Field, Input, Textarea, Select, Modal, PrimaryButton, GhostButton, Badge } from "@/components/kit";
import ExportMenu from "@/components/ExportMenu";
import { BookOpen, Plus, Search, History } from "lucide-react";
import { toast } from "sonner";

const TYPES = ["policy", "procedure", "playbook", "runbook", "tech_doc", "department_doc", "meeting_archive", "internal_guide"];

export default function KnowledgeBase() {
  const { t, lang } = useLang();
  const { has } = usePermissions();
  const [q, setQ] = useState("");
  const [type, setType] = useState("");
  const [rows, setRows] = useState(null);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ title: "", body: "", article_type: "internal_guide", category: "general", tags: "", status: "published" });
  const [detail, setDetail] = useState(null);
  const locale = lang === "ar" ? "ar-EG" : "en-US";

  const load = useCallback(() => {
    const params = { limit: 100 };
    if (q) params.q = q;
    if (type) params.article_type = type;
    api.get("/knowledge", { params }).then((r) => setRows(r.data)).catch(() => setRows([]));
  }, [q, type]);
  useEffect(() => { const id = setTimeout(load, 200); return () => clearTimeout(id); }, [load]);

  const save = async () => {
    if (!form.title.trim()) return toast.error(t("أدخل العنوان", "Enter a title"));
    try {
      await api.post("/knowledge", { ...form, tags: form.tags.split(",").map((s) => s.trim()).filter(Boolean) });
      toast.success(t("تم النشر", "Published")); setOpen(false);
      setForm({ title: "", body: "", article_type: "internal_guide", category: "general", tags: "", status: "published" }); load();
    } catch (e) { toast.error(e?.response?.data?.detail || t("فشل", "Failed")); }
  };

  return (
    <div className="p-6 lg:p-8 space-y-6" data-testid="knowledge-page">
      <PageHeader label={t("المعرفة", "Knowledge")} title={t("قاعدة المعرفة", "Knowledge Base")}
        subtitle={t("السياسات والإجراءات والأدلة والكتيبات.", "Policies, procedures, playbooks, and runbooks.")}
        actions={<>
          {has("export.data") && <ExportMenu entity="knowledge" />}
          {has("kb.create") && <PrimaryButton onClick={() => setOpen(true)} data-testid="kb-new"><Plus size={14} /> {t("مقال", "Article")}</PrimaryButton>}
        </>} />

      <div className="flex flex-wrap items-center gap-2">
        <div className="flex-1 min-w-48 flex items-center gap-2 px-3 py-2 border border-border rounded-md bg-card">
          <Search size={14} className="text-muted-foreground" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("بحث في المعرفة…", "Search the library…")} className="bg-transparent outline-none text-sm flex-1" data-testid="kb-search" />
        </div>
        <Select value={type} onChange={(e) => setType(e.target.value)} className="w-48"><option value="">{t("كل الأنواع", "All types")}</option>{TYPES.map((x) => <option key={x} value={x}>{x}</option>)}</Select>
      </div>

      {rows === null ? <Loading label={t("تحميل المكتبة…", "Loading library…")} /> : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4" data-testid="kb-grid">
          {rows.length === 0 && <div className="col-span-full"><Section><Empty><BookOpen size={20} className="mx-auto mb-2 opacity-40" />{t("لا مقالات.", "No articles.")}</Empty></Section></div>}
          {rows.map((a) => (
            <button key={a.id} onClick={() => setDetail(a)} className="text-start border border-border bg-card rounded-md p-4 hover:border-primary/40 transition-colors" data-testid="kb-card">
              <div className="flex items-center justify-between"><Badge tone="primary">{a.article_type}</Badge><span className="label-mono text-[10px]">v{a.version}</span></div>
              <div className="text-sm font-medium mt-2 line-clamp-2">{a.title}</div>
              <div className="text-xs text-muted-foreground mt-1 line-clamp-2">{a.body}</div>
              <div className="font-mono text-[10px] text-muted-foreground mt-2">{new Date(a.updated_at).toLocaleDateString(locale)}</div>
            </button>
          ))}
        </div>
      )}

      <Modal open={open} onClose={() => setOpen(false)} wide title={t("مقال جديد", "New article")}
        footer={<><GhostButton onClick={() => setOpen(false)}>{t("إلغاء", "Cancel")}</GhostButton><PrimaryButton onClick={save} data-testid="kb-save">{t("نشر", "Publish")}</PrimaryButton></>}>
        <Field label={t("العنوان", "Title")}><Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} data-testid="kb-title" /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label={t("النوع", "Type")}><Select value={form.article_type} onChange={(e) => setForm({ ...form, article_type: e.target.value })}>{TYPES.map((x) => <option key={x} value={x}>{x}</option>)}</Select></Field>
          <Field label={t("التصنيف", "Category")}><Input value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} /></Field>
        </div>
        <Field label={t("الوسوم (مفصولة بفاصلة)", "Tags (comma-separated)")}><Input value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })} /></Field>
        <Field label={t("المحتوى", "Body")}><Textarea rows={6} value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} data-testid="kb-body" /></Field>
      </Modal>

      {detail && <ArticleDetail article={detail} onClose={() => setDetail(null)} />}
    </div>
  );
}

function ArticleDetail({ article, onClose }) {
  const { t } = useLang();
  const [versions, setVersions] = useState([]);
  useEffect(() => { api.get(`/knowledge/${article.id}/versions`).then((r) => setVersions(r.data || [])).catch(() => {}); }, [article.id]);
  return (
    <Modal open onClose={onClose} wide title={article.title}
      footer={<GhostButton onClick={onClose}>{t("إغلاق", "Close")}</GhostButton>}>
      <div className="flex items-center gap-2"><Badge tone="primary">{article.article_type}</Badge><Badge>{article.category}</Badge><span className="label-mono text-[10px]">v{article.version}</span></div>
      <div className="text-sm whitespace-pre-wrap text-foreground">{article.body || "—"}</div>
      {(article.tags || []).length > 0 && <div className="flex flex-wrap gap-1.5">{article.tags.map((tg) => <Badge key={tg}>{tg}</Badge>)}</div>}
      <div>
        <div className="label-mono mb-2 flex items-center gap-1"><History size={12} /> {t("سجل النسخ", "Version history")}</div>
        {versions.length === 0 ? <div className="text-sm text-muted-foreground">{t("لا نسخ سابقة.", "No prior versions.")}</div> :
          <div className="space-y-1">{versions.map((v) => <div key={v.id} className="flex items-center justify-between border border-border rounded-md px-3 py-1.5 text-xs"><span>v{v.version} · {v.title}</span><span className="font-mono text-muted-foreground">{new Date(v.created_at).toLocaleDateString()}</span></div>)}</div>}
      </div>
    </Modal>
  );
}
