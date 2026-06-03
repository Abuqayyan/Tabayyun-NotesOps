import { useEffect, useState, useRef } from "react";
import { useParams, Link } from "react-router-dom";
import { api } from "@/lib/api";
import { useLang } from "@/contexts/LanguageContext";
import { ArrowRight, Sparkles, Loader2, Trash2, CalendarClock, Upload, FileText, Download, Paperclip, UserPlus, Shield, Edit3, Eye, X } from "lucide-react";
import { toast } from "sonner";
import DateTimeField from "@/components/DateTimeField";

export default function ProjectDetail() {
  const { id } = useParams();
  const { lang, t } = useLang();
  const [project, setProject] = useState(null);
  const [summary, setSummary] = useState("");
  const [busy, setBusy] = useState(false);
  const [newTask, setNewTask] = useState("");
  const [newNote, setNewNote] = useState({ title: "", content: "" });
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef(null);
  const [members, setMembers] = useState([]);
  const [shareEmail, setShareEmail] = useState("");
  const [shareRole, setShareRole] = useState("viewer");
  const [sharing, setSharing] = useState(false);

  const STATUS_LABEL = { active: t("نشط", "Active"), paused: t("متوقّف", "Paused"), completed: t("مكتمل", "Completed"), archived: t("مؤرشف", "Archived") };
  const PRIO_LABEL = { low: t("منخفض", "Low"), medium: t("متوسط", "Medium"), high: t("عالٍ", "High"), critical: t("حرج", "Critical") };
  const TASK_STATUS_LABEL = { todo: t("للقيام", "To do"), in_progress: t("جارٍ", "In progress"), blocked: t("معلّق", "Blocked"), done: t("منجز", "Done") };
  const locale = lang === "ar" ? "ar-EG" : "en-US";

  const load = () => api.get(`/projects/${id}`).then(r => setProject(r.data));
  const loadMembers = () => api.get(`/projects/${id}/members`).then(r => setMembers(r.data || [])).catch(() => {});
  useEffect(() => { load().catch(() => {}); loadMembers(); }, [id]);

  const shareProject = async (e) => {
    e.preventDefault();
    if (!shareEmail) return;
    setSharing(true);
    try {
      await api.post(`/projects/${id}/share`, { email: shareEmail, role: shareRole });
      toast.success(t("تمت المشاركة", "Shared"));
      setShareEmail("");
      loadMembers();
    } catch (err) {
      toast.error(err?.response?.data?.detail || t("فشل", "Failed"));
    } finally { setSharing(false); }
  };

  const updateMemberRole = async (uid, role) => {
    try { await api.patch(`/projects/${id}/members/${uid}`, { role }); loadMembers(); }
    catch { toast.error(t("فشل", "Failed")); }
  };

  const removeMember = async (uid) => {
    if (!window.confirm(t("إزالة هذا العضو من المشروع؟", "Remove this member from the project?"))) return;
    try { await api.delete(`/projects/${id}/members/${uid}`); loadMembers(); }
    catch { toast.error(t("فشل", "Failed")); }
  };

  const updateProject = async (patch) => {
    try {
      const r = await api.patch(`/projects/${id}`, patch);
      setProject(prev => ({ ...prev, ...r.data }));
    } catch { toast.error(t("فشل التحديث", "Update failed")); }
  };

  const aiSuggest = async () => {
    setBusy(true);
    try {
      const r = await api.post("/ai/schedule-suggest", { project_id: id });
      const { start_date, end_date, rationale, warnings } = r.data;
      if (start_date && end_date) {
        await updateProject({ start_date, end_date });
        toast.success(t("تم جدولة المشروع بالذكاء", "Project scheduled by AI"));
        if (rationale) toast.message(rationale);
        if (warnings?.length) toast.message(`⚠ ${warnings[0]}`);
      } else {
        toast.error(t("لم يقدر الذكاء يقترح جدولة", "AI couldn't propose a schedule"));
      }
    } catch { toast.error(t("خطأ في الذكاء", "AI error")); }
    finally { setBusy(false); }
  };

  const addTask = async (e) => {
    e.preventDefault();
    if (!newTask.trim()) return;
    await api.post("/tasks", { title: newTask, project_id: id });
    setNewTask(""); load();
  };

  const updateTaskStatus = async (tid, status) => {
    await api.patch(`/tasks/${tid}`, { status }); load();
  };

  const summarize = async () => {
    setBusy(true);
    try {
      const r = await api.post("/ai/summarize-project", { project_id: id });
      setSummary(r.data.summary);
    } catch { toast.error(t("خطأ في الذكاء", "AI error")); }
    finally { setBusy(false); }
  };

  const addNote = async (e) => {
    e.preventDefault();
    if (!newNote.title || !newNote.content) return;
    await api.post("/notes", { ...newNote, project_id: id });
    setNewNote({ title: "", content: "" }); load();
  };

  const deleteProject = async () => {
    if (!window.confirm(t("حذف المشروع؟ جميع المهام والملاحظات راح تنحذف.", "Delete this project? All tasks and notes will be removed."))) return;
    await api.delete(`/projects/${id}`);
    window.location.href = "/projects";
  };

  // ----- File uploads -----
  const uploadFiles = async (filesList) => {
    if (!filesList || filesList.length === 0) return;
    setUploading(true);
    try {
      for (const f of filesList) {
        const fd = new FormData();
        fd.append("file", f);
        try {
          await api.post(`/projects/${id}/files`, fd, { headers: { "Content-Type": "multipart/form-data" } });
        } catch (err) {
          toast.error(`${f.name}: ${err?.response?.data?.detail || t("فشل الرفع", "Upload failed")}`);
        }
      }
      toast.success(t("تم الرفع", "Uploaded"));
      load();
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const downloadFile = async (file) => {
    try {
      const r = await api.get(`/projects/${id}/files/${file.id}/download`, { responseType: "blob" });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement("a");
      a.href = url; a.download = file.filename;
      document.body.appendChild(a); a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch { toast.error(t("فشل التنزيل", "Download failed")); }
  };

  const removeFile = async (fid) => {
    if (!window.confirm(t("حذف الملف؟", "Delete this file?"))) return;
    await api.delete(`/projects/${id}/files/${fid}`);
    load();
  };

  const formatBytes = (b) => {
    if (b == null) return "—";
    if (b < 1024) return `${b} B`;
    if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
    return `${(b / 1024 / 1024).toFixed(1)} MB`;
  };

  if (!project) return <div className="p-8 label-mono">{t("جارٍ التحميل…", "Loading…")}</div>;

  return (
    <div className="p-6 lg:p-8 space-y-6 max-w-6xl" data-testid="project-detail-page">
      <Link to="/projects" className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1.5">
        <ArrowRight size={12} className="rtl:rotate-180" /> {t("المشاريع", "Projects")}
      </Link>

      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="flex items-start gap-3">
          <div className="w-3 h-3 rounded-full mt-2.5" style={{ backgroundColor: project.color }} />
          <div>
            <div className="label-mono">{STATUS_LABEL[project.status] || project.status} · {PRIO_LABEL[project.priority] || project.priority}</div>
            <h1 className="text-3xl sm:text-4xl tracking-tight font-medium mt-1">{project.name}</h1>
            <p className="text-sm text-muted-foreground mt-1 max-w-2xl">{project.description}</p>
          </div>
        </div>
        <div className="flex gap-2">
          <button data-testid="ai-schedule-btn" onClick={aiSuggest} disabled={busy}
            className="px-3 py-2 border border-primary text-primary rounded-md text-sm font-medium hover:bg-primary hover:text-primary-foreground transition-colors flex items-center gap-2 disabled:opacity-50">
            <CalendarClock size={13} /> {t("جدولة ذكية", "AI schedule")}
          </button>
          <button data-testid="ai-summary-btn" onClick={summarize} disabled={busy}
            className="px-3 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:opacity-90 disabled:opacity-50 flex items-center gap-2">
            {busy ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />} {t("ملخص ذكي", "AI summary")}
          </button>
          <button onClick={deleteProject} className="px-3 py-2 border border-border rounded-md text-sm text-muted-foreground hover:text-destructive flex items-center gap-2">
            <Trash2 size={13} />
          </button>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-px bg-border">
        {[
          { l: t("المهام", "Tasks"), v: project.tasks?.length || 0 },
          { l: t("التقدم", "Progress"), v: `${project.progress || 0}%` },
          { l: t("الملاحظات", "Notes"), v: project.notes?.length || 0 },
        ].map(s => (
          <div key={s.l} className="bg-card p-4">
            <div className="label-mono">{s.l}</div>
            <div className="data-number text-2xl mt-1">{s.v}</div>
          </div>
        ))}
      </div>

      {(project.start_date || project.end_date) && (
        <div className="border border-border bg-card rounded-md px-5 py-3 flex items-center justify-between text-sm">
          <div className="flex items-center gap-2">
            <span className="label-mono">{t("الجدول الزمني", "Timeline")}</span>
            <span className="font-mono">{project.start_date ? new Date(project.start_date).toLocaleString(locale) : "—"}</span>
          </div>
          <span className="text-muted-foreground">→</span>
          <span className="font-mono">{project.end_date ? new Date(project.end_date).toLocaleString(locale) : "—"}</span>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <DateTimeField label={t("تاريخ البداية", "Start date")} value={project.start_date} onChange={(v) => updateProject({ start_date: v || null })} testId="pd-start" />
        <DateTimeField label={t("تاريخ النهاية", "End date")} value={project.end_date} onChange={(v) => updateProject({ end_date: v || null })} testId="pd-end" min={project.start_date} />
      </div>

      {summary && (
        <div className="border border-primary/40 bg-card rounded-md p-5" data-testid="ai-summary-output">
          <div className="label-mono flex items-center gap-2 mb-3"><Sparkles size={12} className="text-primary" /> {t("رئيس العمليات الذكي", "AI Chief of Operations")}</div>
          <div className="text-sm whitespace-pre-wrap leading-relaxed">{summary}</div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="border border-border bg-card rounded-md">
          <div className="hairline px-5 py-3"><div className="label-mono">{t("المهام", "Tasks")}</div></div>
          <form onSubmit={addTask} className="px-5 py-3 border-b border-border">
            <input data-testid="quick-task-input" value={newTask} onChange={e => setNewTask(e.target.value)}
              placeholder={t("أضف مهمة واضغط إنتر…", "Add a task and press Enter…")}
              className="w-full px-3 py-2 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary" />
          </form>
          <div className="divide-y divide-border max-h-96 overflow-y-auto">
            {(project.tasks || []).map(tk => (
              <div key={tk.id} className="px-5 py-3 flex items-center justify-between">
                <div className="flex items-center gap-3 min-w-0">
                  <input type="checkbox" checked={tk.status === "done"}
                    onChange={e => updateTaskStatus(tk.id, e.target.checked ? "done" : "todo")} />
                  <span className={`text-sm truncate ${tk.status === "done" ? "line-through text-muted-foreground" : ""}`}>{tk.title}</span>
                </div>
                <select value={tk.status} onChange={e => updateTaskStatus(tk.id, e.target.value)}
                  className="text-xs bg-background border border-border rounded px-2 py-1">
                  {Object.entries(TASK_STATUS_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              </div>
            ))}
            {(project.tasks || []).length === 0 && <div className="p-8 text-center text-sm text-muted-foreground">{t("لا توجد مهام بعد.", "No tasks yet.")}</div>}
          </div>
        </div>

        <div className="border border-border bg-card rounded-md">
          <div className="hairline px-5 py-3"><div className="label-mono">{t("الملاحظات", "Notes")}</div></div>
          <form onSubmit={addNote} className="px-5 py-3 border-b border-border space-y-2">
            <input value={newNote.title} onChange={e => setNewNote({ ...newNote, title: e.target.value })}
              placeholder={t("عنوان الملاحظة…", "Note title…")}
              className="w-full px-3 py-2 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary" />
            <textarea value={newNote.content} onChange={e => setNewNote({ ...newNote, content: e.target.value })}
              rows={2} placeholder={t("اكتب السياق…", "Capture context…")}
              className="w-full px-3 py-2 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary" />
            <button type="submit" className="px-3 py-1.5 bg-primary text-primary-foreground text-sm rounded-md hover:opacity-90">{t("أضف", "Add")}</button>
          </form>
          <div className="divide-y divide-border max-h-96 overflow-y-auto">
            {(project.notes || []).map(n => (
              <div key={n.id} className="px-5 py-3">
                <div className="text-sm font-medium">{n.title}</div>
                <div className="text-xs text-muted-foreground mt-1 line-clamp-3 whitespace-pre-wrap">{n.content}</div>
                <div className="label-mono text-[9px] mt-2">{new Date(n.created_at).toLocaleString(locale)}</div>
              </div>
            ))}
            {(project.notes || []).length === 0 && <div className="p-8 text-center text-sm text-muted-foreground">{t("لا توجد ملاحظات بعد.", "No notes yet.")}</div>}
          </div>
        </div>
      </div>

      {/* Project sharing & members */}
      <div className="border border-border bg-card rounded-md" data-testid="project-share-section">
        <div className="hairline px-5 py-3 flex items-center gap-2">
          <UserPlus size={13} className="text-primary" />
          <div className="label-mono">{t("الأعضاء والصلاحيات", "Members & permissions")} <span className="text-muted-foreground">· {members.length}</span></div>
          {project.my_role && <span className="ms-auto label-mono text-[10px]">{t("دورك:", "You:")} <span className="text-primary">{project.my_role}</span></span>}
        </div>
        {project.my_role === "owner" && (
          <form onSubmit={shareProject} className="px-5 py-3 border-b border-border grid grid-cols-1 md:grid-cols-[1fr_auto_auto] gap-2" data-testid="share-form">
            <input value={shareEmail} onChange={e => setShareEmail(e.target.value)} type="email" placeholder="teammate@company.com" dir="ltr" data-testid="share-email"
              className="px-3 py-2 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary text-left" />
            <select value={shareRole} onChange={e => setShareRole(e.target.value)} data-testid="share-role"
              className="px-3 py-2 bg-background border border-border rounded-md text-sm">
              <option value="viewer">{t("مشاهد", "Viewer")}</option>
              <option value="editor">{t("محرّر", "Editor")}</option>
            </select>
            <button type="submit" disabled={sharing} data-testid="share-submit"
              className="px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:opacity-90 disabled:opacity-50">
              {sharing ? <Loader2 size={13} className="animate-spin" /> : t("شارك", "Share")}
            </button>
          </form>
        )}
        <div className="divide-y divide-border">
          {members.map(m => (
            <div key={m.id} className="px-5 py-3 flex items-center justify-between" data-testid={`pmember-${m.id}`}>
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-full bg-secondary flex items-center justify-center font-mono text-xs font-medium">{m.name?.[0]?.toUpperCase()}</div>
                <div>
                  <div className="text-sm font-medium flex items-center gap-2">
                    {m.name}
                    {m.role === "owner" && <Shield size={11} className="text-primary" />}
                  </div>
                  <div className="text-xs text-muted-foreground" dir="ltr">{m.email}</div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {m.role === "owner" ? (
                  <span className="label-mono text-[10px]">{t("مالك", "Owner")}</span>
                ) : project.my_role === "owner" ? (
                  <>
                    <select value={m.role} onChange={e => updateMemberRole(m.id, e.target.value)} data-testid={`role-${m.id}`}
                      className="text-xs bg-background border border-border rounded px-2 py-1">
                      <option value="viewer">{t("مشاهد", "Viewer")}</option>
                      <option value="editor">{t("محرّر", "Editor")}</option>
                    </select>
                    <button onClick={() => removeMember(m.id)} className="w-7 h-7 rounded-md hover:bg-destructive/10 text-muted-foreground hover:text-destructive flex items-center justify-center" data-testid={`remove-${m.id}`}>
                      <X size={12} />
                    </button>
                  </>
                ) : (
                  <span className="label-mono text-[10px] flex items-center gap-1">
                    {m.role === "editor" ? <Edit3 size={10} /> : <Eye size={10} />} {m.role}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Project files */}
      <div
        className="border border-border bg-card rounded-md"
        data-testid="project-files-section"
        onDragOver={(e) => { e.preventDefault(); }}
        onDrop={(e) => { e.preventDefault(); uploadFiles(e.dataTransfer.files); }}
      >
        <div className="hairline px-5 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2"><Paperclip size={13} className="text-primary" /><div className="label-mono">{t("ملفات المشروع", "Project files")} <span className="text-muted-foreground">· {(project.files || []).length}</span></div></div>
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            data-testid="upload-file-btn"
            className="px-3 py-1.5 bg-primary text-primary-foreground rounded-md text-xs font-medium hover:opacity-90 disabled:opacity-50 flex items-center gap-1.5"
          >
            {uploading ? <Loader2 size={12} className="animate-spin" /> : <Upload size={12} />} {t("ارفع", "Upload")}
          </button>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            data-testid="file-input"
            className="hidden"
            onChange={(e) => uploadFiles(e.target.files)}
          />
        </div>
        {(project.files || []).length === 0 ? (
          <div className="px-5 py-10 text-center text-sm text-muted-foreground">
            {t("اسحب وأفلت الملفات هنا أو اضغط «ارفع». استراتيجية، عقود، تصاميم، أي شي.", "Drag & drop files here or click Upload. Strategy docs, contracts, designs — anything.")}
          </div>
        ) : (
          <div className="divide-y divide-border">
            {project.files.map(f => (
              <div key={f.id} className="px-5 py-3 flex items-center justify-between gap-3 group hover:bg-secondary/30" data-testid={`file-${f.id}`}>
                <button onClick={() => downloadFile(f)} className="flex items-center gap-3 min-w-0 flex-1 text-start">
                  <FileText size={14} className="text-muted-foreground shrink-0" />
                  <div className="min-w-0">
                    <div className="text-sm font-medium truncate group-hover:text-primary transition-colors">{f.filename}</div>
                    <div className="label-mono text-[9px] mt-0.5">{formatBytes(f.size)} · {new Date(f.uploaded_at).toLocaleDateString(locale)}</div>
                  </div>
                </button>
                <div className="flex gap-1 shrink-0">
                  <button onClick={() => downloadFile(f)} className="w-8 h-8 hover:bg-secondary rounded-md flex items-center justify-center" title={t("تنزيل", "Download")}>
                    <Download size={12} />
                  </button>
                  <button onClick={() => removeFile(f.id)} className="w-8 h-8 hover:bg-destructive/10 text-muted-foreground hover:text-destructive rounded-md flex items-center justify-center" title={t("احذف", "Delete")}>
                    <Trash2 size={12} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
