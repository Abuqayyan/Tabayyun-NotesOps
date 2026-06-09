import { Calendar as CalendarIcon, X } from "lucide-react";

/** Premium datetime input — native popup (date + time), styled to match design language. */
export default function DateTimeField({ label, value, onChange, testId, min }) {
  // value: ISO string or "" — we convert to "YYYY-MM-DDTHH:mm" for the input
  const toLocal = (iso) => {
    if (!iso) return "";
    try {
      const d = new Date(iso);
      if (isNaN(d.getTime())) return "";
      const pad = (n) => String(n).padStart(2, "0");
      return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
    } catch { return ""; }
  };
  const fromLocal = (v) => {
    if (!v) return "";
    try {
      return new Date(v).toISOString();
    } catch { return ""; }
  };

  return (
    <div>
      {label && <label className="label-mono mb-1.5 block">{label}</label>}
      <div className="relative">
        <input
          type="datetime-local"
          data-testid={testId}
          value={toLocal(value)}
          min={toLocal(min)}
          onChange={(e) => onChange(fromLocal(e.target.value))}
          dir="ltr"
          className="w-full px-3 py-2 ps-9 bg-background border border-border rounded-md text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary cursor-pointer dark:[color-scheme:dark] text-left"
        />
        <CalendarIcon size={13} className="absolute start-3 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
        {value && (
          <button type="button" onClick={() => onChange("")}
            className="absolute start-8 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-destructive">
            <X size={12} />
          </button>
        )}
      </div>
    </div>
  );
}
