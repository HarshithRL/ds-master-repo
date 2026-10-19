"use client";

import { memo, useState, useEffect, useRef } from "react";
import { cn, formatDate, formatAmount, roundTo } from "@/lib/utils";
import { InfoHint } from "@/components/ui/info-hint";
import { useReadOnly } from "@/components/ui/read-only-context";

/* ═══════════════════════════════════════════════════════════════════
   useAutoSave — shared debounced-save hook
   ═══════════════════════════════════════════════════════════════════ */

function useAutoSave(externalValue: string, onSave: (v: string) => void) {
  const [draft, setDraft] = useState(externalValue);
  const savedValue = useRef(externalValue);

  useEffect(() => { setDraft(externalValue); savedValue.current = externalValue; }, [externalValue]);

  const handleChange = (v: string) => {
    setDraft(v);
    onSave(v);
  };

  const handleBlur = () => {
    if (draft !== externalValue) onSave(draft);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      e.preventDefault();
      setDraft(savedValue.current);
      (e.target as HTMLElement).blur();
    }
  };

  return { draft, handleChange, handleBlur, handleKeyDown };
}

/* ═══════════════════════════════════════════════════════════════════
   AutoInput — single-line text, debounced save
   ═══════════════════════════════════════════════════════════════════ */

export function AutoInput({
  value,
  onSave,
  placeholder,
  className,
  bare,
}: {
  value: string;
  onSave: (v: string) => void;
  placeholder?: string;
  className?: string;
  /** Skip the .form-control styles (height/border/font-size) so the caller
   *  can fully restyle the input — used by oversized headings. */
  bare?: boolean;
}) {
  const readOnly = useReadOnly();
  const { draft, handleChange, handleBlur, handleKeyDown } = useAutoSave(value, onSave);

  if (readOnly) {
    return (
      <div className={cn(!bare && "form-control-readonly text-sm", "w-full", className)}>
        {value || <span className="text-muted-foreground">{placeholder || "—"}</span>}
      </div>
    );
  }

  return (
    <input
      type="text"
      value={draft}
      onChange={(e) => handleChange(e.target.value)}
      onBlur={handleBlur}
      onKeyDown={handleKeyDown}
      placeholder={placeholder}
      className={cn(!bare && "form-control text-sm", "w-full", className)}
    />
  );
}

/* ═══════════════════════════════════════════════════════════════════
   AutoTextarea — multi-line text, debounced save
   ═══════════════════════════════════════════════════════════════════ */

export function AutoTextarea({
  value,
  onSave,
  placeholder,
  maxRows = 10,
  className,
}: {
  value: string;
  onSave: (v: string) => void;
  placeholder?: string;
  maxRows?: number;
  className?: string;
}) {
  const readOnly = useReadOnly();
  const { draft, handleChange, handleBlur, handleKeyDown } = useAutoSave(value, onSave);
  const taRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize to content, capped at maxRows lines
  const resize = () => {
    const el = taRef.current;
    if (!el) return;
    el.style.height = "0";
    const lineHeight = parseFloat(getComputedStyle(el).lineHeight) || 20;
    const maxHeight = lineHeight * maxRows + 16; // 16px for padding
    const scrollH = el.scrollHeight;
    el.style.height = Math.min(scrollH, maxHeight) + "px";
    el.style.overflowY = scrollH > maxHeight ? "auto" : "hidden";
  };

  useEffect(resize, [draft, maxRows]);

  if (readOnly) {
    return (
      <div className={cn("form-control-readonly w-full text-sm whitespace-pre-wrap min-h-14", className)}>
        {value || <span className="text-muted-foreground">{placeholder || "—"}</span>}
      </div>
    );
  }

  return (
    <textarea
      ref={taRef}
      value={draft}
      onChange={(e) => handleChange(e.target.value)}
      onBlur={handleBlur}
      onKeyDown={handleKeyDown}
      placeholder={placeholder}
      rows={1}
      className={cn("form-control form-control-textarea w-full min-h-14 resize-none text-sm", className)}
    />
  );
}

/* ═══════════════════════════════════════════════════════════════════
   AutoGrowInput — compact auto-growing textarea, debounced save

   Looks like a single-line input when empty, grows vertically as the
   user types. Same form-control styling & useAutoSave semantics as
   the rest of the design system.
   ═══════════════════════════════════════════════════════════════════ */

export function AutoGrowInput({
  value,
  onSave,
  placeholder,
  className,
  maxRows,
}: {
  value: string;
  onSave: (v: string) => void;
  placeholder?: string;
  className?: string;
  maxRows?: number;
}) {
  const readOnly = useReadOnly();
  const { draft, handleChange, handleBlur, handleKeyDown } = useAutoSave(value, onSave);
  const taRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize to content, capped at maxRows if provided
  const resize = () => {
    const el = taRef.current;
    if (!el) return;
    el.style.height = "0";
    if (maxRows) {
      const lineHeight = parseFloat(getComputedStyle(el).lineHeight) || 20;
      const maxHeight = lineHeight * maxRows;
      const scrollH = el.scrollHeight;
      el.style.height = Math.min(scrollH, maxHeight) + "px";
      el.style.overflowY = scrollH > maxHeight ? "auto" : "hidden";
    } else {
      el.style.height = el.scrollHeight + "px";
    }
  };

  // Resize on mount + whenever draft changes
  useEffect(resize, [draft, maxRows]);

  if (readOnly) {
    return (
      <div className={cn("form-control-readonly w-full text-sm whitespace-pre-wrap", className)}>
        {value || <span className="text-muted-foreground">{placeholder || "—"}</span>}
      </div>
    );
  }

  return (
    <textarea
      ref={taRef}
      value={draft}
      onChange={(e) => handleChange(e.target.value)}
      onBlur={handleBlur}
      onKeyDown={handleKeyDown}
      placeholder={placeholder}
      rows={1}
      className={cn(
        "form-control form-control-grow w-full text-sm resize-none",
        maxRows ? "" : "overflow-hidden",
        className,
      )}
    />
  );
}

/* ═══════════════════════════════════════════════════════════════════
   AutoTitle — large title input, debounced save
   ═══════════════════════════════════════════════════════════════════ */

export function AutoTitle({
  value,
  onSave,
}: {
  value: string;
  onSave: (v: string) => void;
}) {
  const readOnly = useReadOnly();
  const { draft, handleChange, handleBlur, handleKeyDown } = useAutoSave(value, onSave);

  if (readOnly) {
    return (
      <div className="form-control-readonly w-full text-2xl font-bold text-etex-charcoal h-auto py-1.5">
        {value || <span className="text-muted-foreground font-normal">Untitled project</span>}
      </div>
    );
  }

  return (
    <input
      value={draft}
      onChange={(e) => handleChange(e.target.value)}
      onBlur={handleBlur}
      onKeyDown={handleKeyDown}
      placeholder="Untitled project"
      className="form-control w-full text-2xl font-bold text-etex-charcoal h-auto py-1.5 placeholder:font-normal"
    />
  );
}

/* ═══════════════════════════════════════════════════════════════════
   AutoDateInput — date picker, saves on change (no debounce)
   ═══════════════════════════════════════════════════════════════════ */

function toInputDate(d: Date | string | null | undefined): string {
  if (!d) return "";
  const date = typeof d === "string" ? new Date(d) : d;
  // Use local-date components, not UTC. Dates entered via this picker are
  // stored as midnight local time (= non-midnight UTC for non-UTC users),
  // and `toISOString()` strips that local context. Using getFullYear/
  // getMonth/getDate keeps the picker showing the same day the rest of
  // the app shows via `formatDate`.
  const yyyy = date.getFullYear();
  const mm = String(date.getMonth() + 1).padStart(2, "0");
  const dd = String(date.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

export function AutoDateInput({
  value,
  onSave,
  className,
}: {
  value: Date | string | null | undefined;
  onSave: (v: string | null) => void;
  className?: string;
}) {
  const readOnly = useReadOnly();

  if (readOnly) {
    return (
      <div className={cn("form-control-readonly w-full text-sm font-mono tabular-nums", className)}>
        {value ? formatDate(value) : <span className="text-muted-foreground">—</span>}
      </div>
    );
  }

  return (
    <input
      type="date"
      value={toInputDate(value)}
      onChange={(e) => onSave(e.target.value || null)}
      className={cn("form-control w-full text-sm font-mono tabular-nums", className)}
    />
  );
}

/* ═══════════════════════════════════════════════════════════════════
   AutoAmount — numeric input with mask & unit suffix
   ═══════════════════════════════════════════════════════════════════ */

export function AutoAmount({
  value,
  onSave,
  unit = "k€",
  decimals = 1,
}: {
  value: number | null | undefined;
  onSave: (v: number) => void;
  unit?: string;
  decimals?: number;
}) {
  const readOnly = useReadOnly();
  const [draft, setDraft] = useState(String(roundTo(value ?? 0, decimals)));
  const [editing, setEditing] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!editing) setDraft(String(roundTo(value ?? 0, decimals)));
  }, [value, editing, decimals]);

  const commit = (raw: string) => {
    const stripped = raw.replace(/[^0-9.\-]/g, "");
    const n = stripped === "" ? 0 : roundTo(parseFloat(stripped), decimals);
    if (!isNaN(n) && n !== (value ?? 0)) onSave(n);
    setEditing(false);
  };

  const handleFocus = () => {
    setEditing(true);
    setDraft(String(roundTo(value ?? 0, decimals)));
    setTimeout(() => inputRef.current?.select(), 0);
  };

  const handleBlur = () => {
    commit(draft);
  };

  // Formatted display when not editing
  const display = editing ? draft : formatAmount(value ?? 0, decimals);

  // Calculate unit label width for proper padding
  const unitWidth = unit.length * 7 + 16; // approx char width + padding

  if (readOnly) {
    return (
      <div className="form-control-readonly w-full text-right font-mono text-sm tabular-nums">
        {display}
        <span className="ml-1 text-[10px] text-muted-foreground font-semibold tracking-wide">{unit}</span>
      </div>
    );
  }

  return (
    <div className="relative">
      <input
        ref={inputRef}
        type={editing ? "number" : "text"}
        inputMode="numeric"
        value={display}
        onChange={(e) => {
          setDraft(e.target.value);
          const v = e.target.value.trim();
          const n = v === "" ? 0 : roundTo(parseFloat(v), decimals);
          if (!isNaN(n) && n !== (value ?? 0)) onSave(n);
        }}
        onFocus={handleFocus}
        onBlur={handleBlur}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            commit(draft);
            inputRef.current?.blur();
          }
        }}
        className="form-control w-full text-right font-mono text-sm tabular-nums"
        style={{ paddingRight: unitWidth }}
      />
      <span
        className="absolute top-1/2 -translate-y-1/2 text-[10px] text-muted-foreground pointer-events-none font-semibold tracking-wide"
        style={{ right: 10 }}
      >
        {unit}
      </span>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   AutoMetric — nullable numeric input for KPIs (RIDs, variance, etc.)

   Similar to AutoAmount but supports null values (empty = null),
   has an integer mode, and shows "—" when empty.
   ═══════════════════════════════════════════════════════════════════ */

export const AutoMetric = memo(function AutoMetric({
  value,
  onSave,
  unit,
  integer,
  decimals: decimalsProp,
}: {
  value: number | null;
  onSave: (v: number | null) => void;
  unit: string;
  integer?: boolean;
  decimals?: number;
}) {
  const decimals = decimalsProp ?? (integer ? 0 : 1);
  const readOnly = useReadOnly();
  const [draft, setDraft] = useState(value !== null ? String(roundTo(value, decimals)) : "");
  const [editing, setEditing] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!editing) setDraft(value !== null ? String(roundTo(value, decimals)) : "");
  }, [value, editing, decimals]);

  const commit = (raw: string) => {
    if (raw.trim() === "") { if (value !== null) onSave(null); setEditing(false); return; }
    const n = integer ? parseInt(raw, 10) : roundTo(parseFloat(raw), decimals);
    if (!isNaN(n) && n !== value) onSave(n);
    setEditing(false);
  };

  const display = editing ? draft : (value !== null ? formatAmount(value, decimals) : "");
  const unitWidth = unit.length * 7 + 16;

  if (readOnly) {
    return (
      <div className="form-control-readonly w-full text-right font-mono text-sm tabular-nums">
        {value !== null ? formatAmount(value, decimals) : "—"}
        {unit && value !== null && (
          <span className="ml-1 text-[10px] text-gray-400 font-semibold">{unit}</span>
        )}
      </div>
    );
  }

  return (
    <div className="relative">
      <input
        ref={inputRef}
        type={editing ? "number" : "text"}
        inputMode="numeric"
        value={display}
        onChange={(e) => {
          const raw = e.target.value;
          setDraft(raw);
          if (raw.trim() === "") { if (value !== null) onSave(null); }
          else {
            const n = integer ? parseInt(raw, 10) : roundTo(parseFloat(raw), decimals);
            if (!isNaN(n) && n !== value) onSave(n);
          }
        }}
        onFocus={() => {
          setEditing(true);
          setDraft(value !== null ? String(roundTo(value, decimals)) : "");
          setTimeout(() => inputRef.current?.select(), 0);
        }}
        onBlur={() => commit(draft)}
        onKeyDown={(e) => {
          if (e.key === "Enter") { commit(draft); inputRef.current?.blur(); }
        }}
        placeholder="—"
        className="form-control w-full text-right font-mono text-sm tabular-nums"
        style={{ paddingRight: unitWidth }}
      />
      <span
        className="absolute top-1/2 -translate-y-1/2 text-[10px] text-gray-400 font-semibold pointer-events-none"
        style={{ right: 10 }}
      >
        {unit}
      </span>
    </div>
  );
});

/* ═══════════════════════════════════════════════════════════════════
   Layout primitives — shared labels
   ═══════════════════════════════════════════════════════════════════ */

export function Section({
  title,
  children,
  defaultOpen = true,
  headerExtra,
}: {
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
  headerExtra?: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="section-card">
      <div className="section-toggle" role="group">
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="flex items-center gap-2 flex-1 min-w-0 cursor-pointer bg-transparent border-0 p-0 text-left"
        >
          <span>{title}</span>
          {!headerExtra && (
            <svg
              width="16"
              height="16"
              viewBox="0 0 16 16"
              fill="none"
              className={cn(
                "section-chevron ml-auto",
                open && "section-chevron-open",
              )}
            >
              <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          )}
        </button>
        {headerExtra && (
          <div className="ml-auto mr-1">
            {headerExtra}
          </div>
        )}
        {headerExtra && (
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            className="flex items-center cursor-pointer bg-transparent border-0 p-0"
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 16 16"
              fill="none"
              className={cn(
                "section-chevron",
                open && "section-chevron-open",
              )}
            >
              <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        )}
      </div>
      <div className={cn("section-body", !open && "section-body-closed")}>
        <div className="section-body-inner">
          {children}
        </div>
      </div>
    </div>
  );
}

export function PropLabel({ children, hint, error }: { children: React.ReactNode; hint?: string; error?: boolean }) {
  return (
    <div className={cn(
      "text-[11px] font-medium uppercase tracking-wider mb-1 flex items-center gap-1",
      error ? "text-red-500" : "text-muted-foreground",
    )}>
      {children}
      {hint && <InfoHint label={typeof children === "string" ? children : undefined} text={hint} />}
    </div>
  );
}

export function RowLabel({ children, hint }: { children: React.ReactNode; hint?: string }) {
  return (
    <span className="text-[12px] text-muted-foreground leading-9 inline-flex items-center gap-1">
      <span className="truncate">{children}</span>
      {hint && <InfoHint label={typeof children === "string" ? children : undefined} text={hint} className="shrink-0" />}
    </span>
  );
}
