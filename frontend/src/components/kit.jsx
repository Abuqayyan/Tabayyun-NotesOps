// Shared page primitives for the Phase 6 screens. These are thin wrappers over the
// EXISTING Tabayyun NotesOps classes (border/bg-card/rounded-md, hairline, label-mono,
// data-number) so every new page is visually identical to the original ones.
import { motion, AnimatePresence } from "framer-motion";
import { X } from "lucide-react";

export function PageHeader({ label, title, subtitle, actions }) {
  return (
    <div className="flex items-end justify-between flex-wrap gap-4">
      <div>
        {label && <div className="label-mono">{label}</div>}
        <h1 className="text-3xl sm:text-4xl tracking-tight font-medium mt-1">{title}</h1>
        {subtitle && <p className="text-sm text-muted-foreground mt-1">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2 flex-wrap">{actions}</div>}
    </div>
  );
}

export function Section({ title, actions, children, className = "" }) {
  return (
    <div className={`border border-border bg-card rounded-md ${className}`}>
      {(title || actions) && (
        <div className="hairline px-5 py-3 flex items-center justify-between gap-2">
          <div className="label-mono">{title}</div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </div>
      )}
      {children}
    </div>
  );
}

export function Stat({ label, value, sub, icon: Icon, tid, color }) {
  return (
    <div className="p-5 border border-border bg-card rounded-md hover:border-primary/40 transition-colors" data-testid={tid}>
      <div className="flex items-start justify-between">
        <div className="label-mono">{label}</div>
        {Icon && <Icon size={14} className={color || "text-muted-foreground"} />}
      </div>
      <div className={`data-number text-3xl mt-3 ${color || ""}`}>{value}</div>
      {sub && <div className="text-xs text-muted-foreground mt-1">{sub}</div>}
    </div>
  );
}

export function Empty({ children }) {
  return <div className="p-8 text-center text-sm text-muted-foreground">{children}</div>;
}

export function Loading({ label }) {
  return <div className="p-8"><div className="label-mono animate-pulse">{label || "loading…"}</div></div>;
}

export function Forbidden({ label }) {
  return (
    <div className="p-12 text-center">
      <div className="label-mono">403</div>
      <div className="text-sm text-muted-foreground mt-2">{label || "You don't have access to this section."}</div>
    </div>
  );
}

export function Badge({ children, tone = "muted" }) {
  const tones = {
    muted: "bg-secondary text-muted-foreground", primary: "bg-primary/15 text-primary",
    green: "bg-emerald-500/15 text-emerald-500", amber: "bg-amber-500/15 text-amber-500",
    red: "bg-red-500/15 text-red-500", blue: "bg-blue-500/15 text-blue-500",
  };
  return <span className={`px-2 py-0.5 rounded text-[11px] font-medium ${tones[tone] || tones.muted}`}>{children}</span>;
}

export function Input(props) {
  return <input {...props} className={`w-full px-3 py-2 bg-background border border-border rounded-md text-sm outline-none focus:border-primary/50 ${props.className || ""}`} />;
}
export function Textarea(props) {
  return <textarea {...props} className={`w-full px-3 py-2 bg-background border border-border rounded-md text-sm outline-none focus:border-primary/50 ${props.className || ""}`} />;
}
export function Select({ children, ...props }) {
  return <select {...props} className={`w-full px-3 py-2 bg-background border border-border rounded-md text-sm outline-none focus:border-primary/50 ${props.className || ""}`}>{children}</select>;
}
export function Field({ label, children }) {
  return (
    <label className="block space-y-1">
      <span className="label-mono">{label}</span>
      {children}
    </label>
  );
}

export function PrimaryButton({ children, ...props }) {
  return <button {...props} className={`px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:opacity-90 disabled:opacity-50 flex items-center gap-2 ${props.className || ""}`}>{children}</button>;
}
export function GhostButton({ children, ...props }) {
  return <button {...props} className={`px-3 py-2 border border-border rounded-md text-sm font-medium hover:bg-secondary disabled:opacity-50 flex items-center gap-2 ${props.className || ""}`}>{children}</button>;
}

export function Modal({ open, onClose, title, children, footer, wide }) {
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          className="fixed inset-0 bg-black/50 z-50 flex items-start justify-center pt-24 p-4 overflow-y-auto"
          onClick={onClose} data-testid="modal-overlay"
        >
          <motion.div
            initial={{ y: -16, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: -16, opacity: 0 }}
            transition={{ duration: 0.15 }} onClick={(e) => e.stopPropagation()}
            className={`w-full ${wide ? "max-w-2xl" : "max-w-md"} bg-card border border-border rounded-md overflow-hidden glass`}
          >
            <div className="hairline px-5 py-3 flex items-center justify-between">
              <div className="label-mono">{title}</div>
              <button onClick={onClose} className="text-muted-foreground hover:text-foreground"><X size={16} /></button>
            </div>
            <div className="p-5 space-y-4 max-h-[70vh] overflow-y-auto">{children}</div>
            {footer && <div className="hairline px-5 py-3 flex items-center justify-end gap-2">{footer}</div>}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
