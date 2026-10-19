"use client";

import { memo } from "react";
import { cn } from "@/lib/utils";
import { AlertTriangle, CircleAlert, CheckCircle2 } from "lucide-react";
import { AutoInput } from "@/components/ui/auto-fields";
import { useReadOnly } from "@/components/ui/read-only-context";
import type { RAGStatus } from "@/lib/db/models";

type RAGValue = RAGStatus | null | undefined;

/* ── RAG dot definitions (mirror src/components/ui/rag-indicator.tsx) ─── */

const DOTS = [
  {
    key: "RED",
    Icon: CircleAlert,
    active: "bg-red-600 border-red-400",
    activeShadow: "shadow-[0_0_8px_rgba(220,38,38,0.6)]",
  },
  {
    key: "AMBER",
    Icon: AlertTriangle,
    active: "bg-amber-400 border-amber-300",
    activeShadow: "shadow-[0_0_8px_rgba(245,158,11,0.6)]",
  },
  {
    key: "GREEN",
    Icon: CheckCircle2,
    active: "bg-emerald-500 border-emerald-300",
    activeShadow: "shadow-[0_0_8px_rgba(34,197,94,0.6)]",
  },
] as const;

/* Dark-glass style that makes AutoInput blend into the orange section bar. */
const GLASS_INPUT_CLASS = cn(
  "h-9 w-40 sm:w-50 px-2.5 rounded-sm",
  "bg-white/10 text-white placeholder:text-white/40",
  "text-[12px] font-medium",
  "border border-white/20 hover:border-white/40",
  "focus:bg-white/20 focus:border-white/60 outline-none",
  "transition-colors duration-150",
);

/* ── Read-only display — small chip with status text ─────────────── */

function ReadOnlyDisplay({ value, label }: { value: RAGValue; label: string | null | undefined }) {
  const dot = DOTS.find((d) => d.key === value);
  return (
    <div className="inline-flex items-center gap-2 rounded-sm bg-black/15 backdrop-blur-sm px-2 py-1.5">
      {label && (
        <span className="text-[12px] font-medium text-white px-1 max-w-50 truncate">
          {label}
        </span>
      )}
      {dot ? (
        <div
          className={cn(
            "w-9 h-9 rounded-sm border-2 flex items-center justify-center",
            dot.active,
            dot.activeShadow,
          )}
        >
          <dot.Icon className="w-5 h-5 text-white drop-shadow-sm" strokeWidth={2.5} fill="none" />
        </div>
      ) : (
        <div className="w-9 h-9 rounded-sm border-2 border-white/20 bg-white/10 flex items-center justify-center">
          <span className="text-[10px] text-white/40">—</span>
        </div>
      )}
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════
   RagWithLabel — combined editor:
   ┌─────────────────────────────────────────────────────────────┐
   │ ┊ Status note (e.g. On Track) ┊  │ RED │ AMB │ GREEN │       │
   └─────────────────────────────────────────────────────────────┘
   Mirrors the one-pager status indicator layout. The label and the
   three RAG buttons share the same glass-backdrop container.
   ══════════════════════════════════════════════════════════════════ */

export const RagWithLabel = memo(function RagWithLabel({
  value,
  label,
  onChangeStatus,
  onChangeLabel,
  placeholder = "Status note (e.g. On Track)",
}: {
  value: RAGValue;
  label: string | null | undefined;
  onChangeStatus: (v: RAGValue) => void;
  onChangeLabel: (v: string | null) => void;
  placeholder?: string;
}) {
  const readOnly = useReadOnly();
  const isEmptyStatus = !value;

  if (readOnly) {
    return <ReadOnlyDisplay value={value} label={label} />;
  }

  return (
    <div
      className={cn(
        "inline-flex items-center gap-1.5 rounded-sm backdrop-blur-sm px-2 py-1.5 transition-all duration-200",
        isEmptyStatus
          ? "bg-black/10 ring-1 ring-gray-400/40"
          : "bg-black/15",
      )}
    >
      {/* Inline status-note input (collapses on narrow screens) */}
      <div className="hidden sm:block">
        <AutoInput
          value={label ?? ""}
          onSave={(v) => onChangeLabel(v ? v : null)}
          placeholder={placeholder}
          className={GLASS_INPUT_CLASS}
        />
      </div>

      {/* Vertical divider between the two regions */}
      <div className="hidden sm:block w-px self-stretch bg-white/15 mx-0.5" aria-hidden="true" />

      {/* 3-button RAG selector */}
      {isEmptyStatus && (
        <span className="text-[10px] font-semibold text-white/60 mr-0.5 select-none">
          Set status
        </span>
      )}
      {DOTS.map((dot) => {
        const isActive = value === dot.key;
        return (
          <button
            key={dot.key}
            type="button"
            title={`Set ${dot.key.toLowerCase()}`}
            onClick={() => onChangeStatus(isActive ? null : dot.key)}
            className={cn(
              "w-9 h-9 rounded-sm border-2 transition-all duration-200 ease-out cursor-pointer",
              "flex items-center justify-center hover:scale-110 focus:outline-none",
              isActive
                ? cn(dot.active, dot.activeShadow, "scale-105")
                : "border-white/30 bg-white/10 hover:bg-white/25",
            )}
            aria-label={`${dot.key} status${isActive ? " (active)" : ""}`}
          >
            <dot.Icon
              className={cn("w-5 h-5", isActive ? "text-white drop-shadow-sm" : "text-white/40")}
              strokeWidth={2.5}
              fill="none"
            />
          </button>
        );
      })}
    </div>
  );
});
