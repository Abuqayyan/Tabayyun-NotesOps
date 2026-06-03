import { useCallback, useEffect, useState, useRef } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  ReactFlow, Background, Controls, MiniMap, addEdge,
  applyNodeChanges, applyEdgeChanges, MarkerType,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { api } from "@/lib/api";
import { useLang } from "@/contexts/LanguageContext";
import { Plus, Save, Trash2, FilePlus, ChevronRight, Network, Link2, FolderGit2, Loader2 } from "lucide-react";
import { toast } from "sonner";

const NODE_COLORS = ["#FF4500", "#06B6D4", "#A855F7", "#10B981", "#F59E0B", "#EC4899"];

export default function Graph() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { lang, t } = useLang();
  const isAr = lang === "ar";

  const [canvases, setCanvases] = useState([]);
  const [active, setActive] = useState(null); // {id, name, nodes, edges, project_id}
  const [projects, setProjects] = useState([]);
  const [nodes, setNodes] = useState([]);
  const [edges, setEdges] = useState([]);
  const [loading, setLoading] = useState(false);
  const [dirty, setDirty] = useState(false);
  const saveTimer = useRef(null);

  const loadList = async () => {
    const r = await api.get("/canvases");
    setCanvases(r.data || []);
    return r.data || [];
  };

  const loadCanvas = async (cid) => {
    setLoading(true);
    try {
      const r = await api.get(`/canvases/${cid}`);
      setActive(r.data);
      setNodes(r.data.nodes || []);
      setEdges(r.data.edges || []);
      setDirty(false);
    } finally { setLoading(false); }
  };

  useEffect(() => {
    api.get("/projects").then(r => setProjects(r.data || [])).catch(() => {});
    loadList().then((list) => {
      if (id) loadCanvas(id);
      else if (list.length > 0) navigate(`/graph/${list[0].id}`, { replace: true });
    });
    // eslint-disable-next-line
  }, []);

  useEffect(() => { if (id && active?.id !== id) loadCanvas(id); /* eslint-disable-next-line */ }, [id]);

  const onNodesChange = useCallback((changes) => {
    setNodes((nds) => applyNodeChanges(changes, nds));
    setDirty(true);
  }, []);
  const onEdgesChange = useCallback((changes) => {
    setEdges((eds) => applyEdgeChanges(changes, eds));
    setDirty(true);
  }, []);
  const onConnect = useCallback((conn) => {
    setEdges((eds) => addEdge({ ...conn, markerEnd: { type: MarkerType.ArrowClosed }, animated: false }, eds));
    setDirty(true);
  }, []);

  // Auto-save debounced
  useEffect(() => {
    if (!dirty || !active?.id) return;
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(async () => {
      try {
        await api.patch(`/canvases/${active.id}`, { nodes, edges });
        setDirty(false);
      } catch { /* ignore */ }
    }, 1200);
    return () => saveTimer.current && clearTimeout(saveTimer.current);
  }, [nodes, edges, dirty, active]);

  const createCanvas = async () => {
    const name = window.prompt(t("اسم الرسم", "Canvas name"), t("رسم جديد", "Untitled canvas"));
    if (!name) return;
    const r = await api.post("/canvases", { name, nodes: [], edges: [] });
    await loadList();
    navigate(`/graph/${r.data.id}`);
  };

  const renameCanvas = async () => {
    if (!active) return;
    const name = window.prompt(t("اسم جديد", "Rename canvas"), active.name);
    if (!name) return;
    await api.patch(`/canvases/${active.id}`, { name });
    setActive({ ...active, name });
    loadList();
  };

  const deleteCanvas = async () => {
    if (!active) return;
    if (!window.confirm(t("حذف هذا الرسم؟", "Delete this canvas?"))) return;
    await api.delete(`/canvases/${active.id}`);
    setActive(null); setNodes([]); setEdges([]);
    const list = await loadList();
    if (list.length) navigate(`/graph/${list[0].id}`);
    else navigate("/graph");
  };

  const addNode = (label = "Node") => {
    const id = `n_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
    const color = NODE_COLORS[nodes.length % NODE_COLORS.length];
    setNodes((nds) => nds.concat({
      id,
      type: "default",
      position: { x: 120 + Math.random() * 320, y: 80 + Math.random() * 240 },
      data: { label },
      style: { background: "#141414", color: "#fafafa", border: `2px solid ${color}`, borderRadius: 8, padding: 10, fontSize: 13, minWidth: 120 },
    }));
    setDirty(true);
  };

  const linkProject = async (pid) => {
    if (!active) return;
    await api.patch(`/canvases/${active.id}`, { project_id: pid || null });
    setActive({ ...active, project_id: pid || null });
    toast.success(t("تم الربط", "Linked"));
  };

  const importTasks = async () => {
    if (!active?.project_id) {
      toast.message(t("اربط بمشروع أولاً", "Link to a project first"));
      return;
    }
    try {
      const r = await api.get("/tasks", { params: { project_id: active.project_id } });
      const tasks = r.data || [];
      const newNodes = tasks.slice(0, 20).map((t, idx) => ({
        id: `task_${t.id}`,
        type: "default",
        position: { x: 80 + (idx % 5) * 200, y: 80 + Math.floor(idx / 5) * 120 },
        data: { label: t.title },
        style: {
          background: t.status === "done" ? "#0a0a0a" : "#141414",
          color: t.status === "done" ? "#737373" : "#fafafa",
          border: `2px solid ${t.priority === "critical" ? "#EF4444" : t.priority === "high" ? "#FF4500" : "#404040"}`,
          borderRadius: 8, padding: 10, fontSize: 12, minWidth: 140,
          textDecoration: t.status === "done" ? "line-through" : "none",
        },
      }));
      setNodes((nds) => [...nds.filter(n => !n.id.startsWith("task_")), ...newNodes]);
      setDirty(true);
      toast.success(`${newNodes.length} ${t("مهمة مستوردة", "tasks imported")}`);
    } catch { toast.error(t("فشل الاستيراد", "Import failed")); }
  };

  return (
    <div className="flex h-[calc(100vh-3.5rem)]" data-testid="graph-page">
      {/* Sidebar */}
      <aside className="w-60 shrink-0 border-e border-border bg-card flex flex-col">
        <div className="p-3 border-b border-border flex items-center justify-between">
          <div className="label-mono">{t("الرسوم", "Canvases")}</div>
          <button data-testid="canvas-new" onClick={createCanvas} className="w-7 h-7 rounded-md border border-border hover:bg-secondary flex items-center justify-center" title={t("جديد", "New")}>
            <Plus size={13} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
          {canvases.length === 0 && <div className="p-4 text-xs text-muted-foreground text-center">{t("لا توجد رسومات بعد", "No canvases yet")}</div>}
          {canvases.map(c => (
            <button
              key={c.id}
              data-testid={`canvas-item-${c.id}`}
              onClick={() => navigate(`/graph/${c.id}`)}
              className={`w-full text-start px-3 py-2 rounded-md text-sm flex items-center gap-2 transition-colors ${
                active?.id === c.id ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground hover:bg-secondary/60"
              }`}
            >
              <Network size={12} className="shrink-0" />
              <span className="truncate flex-1">{c.name}</span>
              <span className="label-mono text-[9px]">{c.node_count || 0}</span>
            </button>
          ))}
        </div>
      </aside>

      {/* Main canvas area */}
      <div className="flex-1 flex flex-col min-w-0">
        {active ? (
          <>
            <div className="hairline px-5 h-12 flex items-center justify-between">
              <div className="flex items-center gap-2 min-w-0">
                <Network size={14} className="text-primary shrink-0" />
                <button onClick={renameCanvas} className="text-sm font-medium truncate hover:text-primary" data-testid="canvas-name">
                  {active.name}
                </button>
                {dirty && <span className="label-mono text-[9px] text-amber-500">{t("جارٍ الحفظ…", "Saving…")}</span>}
                {!dirty && <span className="label-mono text-[9px] text-emerald-500">{t("محفوظ", "Saved")}</span>}
              </div>
              <div className="flex items-center gap-1">
                <select
                  data-testid="canvas-project-link"
                  value={active.project_id || ""}
                  onChange={(e) => linkProject(e.target.value)}
                  className="px-2 py-1.5 bg-background border border-border rounded-md text-xs max-w-[180px]"
                >
                  <option value="">{t("بدون مشروع", "No project")}</option>
                  {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
                <button data-testid="canvas-add-node" onClick={() => addNode("Node")} className="px-2.5 py-1.5 border border-border rounded-md text-xs hover:bg-secondary flex items-center gap-1">
                  <Plus size={12} /> {t("عقدة", "Node")}
                </button>
                <button data-testid="canvas-import-tasks" onClick={importTasks} disabled={!active.project_id} className="px-2.5 py-1.5 border border-border rounded-md text-xs hover:bg-secondary disabled:opacity-50 flex items-center gap-1">
                  <Link2 size={12} /> {t("استيراد المهام", "Import tasks")}
                </button>
                <button data-testid="canvas-delete" onClick={deleteCanvas} className="w-8 h-8 border border-border rounded-md hover:bg-destructive/10 hover:text-destructive flex items-center justify-center">
                  <Trash2 size={12} />
                </button>
              </div>
            </div>

            <div className="flex-1 relative" style={{ background: "#0a0a0a" }}>
              {loading && <div className="absolute top-3 start-3 z-10 bg-card border border-border px-3 py-1.5 rounded-md text-xs flex items-center gap-2"><Loader2 size={12} className="animate-spin" /> {t("تحميل…", "Loading…")}</div>}
              <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onConnect={onConnect}
                fitView
                proOptions={{ hideAttribution: true }}
                onNodeDoubleClick={(_, node) => {
                  const newLabel = window.prompt(t("اسم العقدة", "Node label"), node.data?.label || "");
                  if (newLabel != null) {
                    setNodes((nds) => nds.map(n => n.id === node.id ? { ...n, data: { ...n.data, label: newLabel } } : n));
                    setDirty(true);
                  }
                }}
              >
                <Background color="#262626" gap={20} />
                <Controls position="bottom-right" />
                <MiniMap maskColor="rgba(10,10,10,0.7)" nodeColor={() => "#FF4500"} style={{ background: "#141414", border: "1px solid #262626" }} />
              </ReactFlow>
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center max-w-sm space-y-4">
              <div className="w-16 h-16 mx-auto rounded-md bg-primary/10 border border-primary/30 flex items-center justify-center">
                <Network size={28} className="text-primary" />
              </div>
              <h2 className="text-xl font-medium">{t("ابدأ رسمك الأول", "Start your first canvas")}</h2>
              <p className="text-sm text-muted-foreground">{t("ارسم الأفكار، اربط المهام، وصمّم تدفقات مشاريعك بصريًا.", "Map ideas, link tasks, and design project flows visually.")}</p>
              <button data-testid="canvas-empty-create" onClick={createCanvas} className="px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:opacity-90 inline-flex items-center gap-2">
                <FilePlus size={13} /> {t("رسم جديد", "New canvas")}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
