// Reusable export control (Module 12). Downloads CSV/XLSX from the existing, audited
// export API and matches the platform's small button + inline-menu pattern.
import { useState, useRef, useEffect } from "react";
import { api } from "@/lib/api";
import { useLang } from "@/contexts/LanguageContext";
import { Download } from "lucide-react";
import { toast } from "sonner";

export default function ExportMenu({ entity, path, label }) {
  const { t } = useLang();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    const onClick = (e) => ref.current && !ref.current.contains(e.target) && setOpen(false);
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const download = async (format) => {
    setBusy(true);
    setOpen(false);
    try {
      const url = path || `/exports/${entity}`;
      const res = await api.get(url, { params: { format }, responseType: "blob" });
      const fallback = res.headers["x-export-fallback"] === "csv";
      const ext = format === "xlsx" && !fallback ? "xlsx" : "csv";
      const href = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = href;
      a.download = `tabayyun_${entity || "audit"}.${ext}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(href);
      if (fallback) toast.info(t("XLSX غير متاح — تم التصدير CSV", "XLSX unavailable — exported CSV"));
    } catch (e) {
      toast.error(t("فشل التصدير", "Export failed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="relative" ref={ref}>
      <button
        data-testid={`export-${entity}-btn`}
        onClick={() => setOpen((v) => !v)}
        disabled={busy}
        className="px-3 py-2 border border-border rounded-md text-sm font-medium hover:bg-secondary flex items-center gap-2 disabled:opacity-50"
      >
        <Download size={13} /> {label || t("تصدير", "Export")}
      </button>
      {open && (
        <div className="absolute end-0 mt-1 w-32 bg-card border border-border rounded-md overflow-hidden z-40 glass">
          <button onClick={() => download("csv")} className="w-full text-start px-3 py-2 text-sm hover:bg-secondary border-b border-border">CSV</button>
          <button onClick={() => download("xlsx")} className="w-full text-start px-3 py-2 text-sm hover:bg-secondary">XLSX</button>
        </div>
      )}
    </div>
  );
}
