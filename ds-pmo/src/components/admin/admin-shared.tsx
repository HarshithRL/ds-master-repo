"use client";

/* ═══════════════════════════════════════════════════════════════════
   Shared pieces for the admin DataTables.
   Keep this file tiny — only things used by 2+ admin tables.
   ═══════════════════════════════════════════════════════════════════ */

import * as React from "react";
import { useMemo, useState } from "react";
import { Pencil, Trash2, UserX, type LucideIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn, formatDateTime, formatRelativeTime } from "@/lib/utils";

/* ── Row actions ─────────────────────────────────────────────────── */

export function RowActions({
  onEdit,
  onRemove,
  onDeactivate,
  isActive,
}: {
  onEdit: () => void;
  onRemove: () => void;
  onDeactivate?: () => void;
  isActive?: boolean;
}) {
  const stop = (fn: () => void) => (e: React.MouseEvent) => {
    e.stopPropagation();
    fn();
  };
  return (
    <div className="flex items-center justify-end gap-0.5">
      <IconBtn icon={Pencil} label="Edit" onClick={stop(onEdit)} />
      {onDeactivate && isActive && (
        <IconBtn
          icon={UserX}
          label="Deactivate"
          onClick={stop(onDeactivate)}
          hoverClass="hover:text-amber-600 dark:hover:text-amber-400"
        />
      )}
      <IconBtn
        icon={Trash2}
        label="Remove"
        onClick={stop(onRemove)}
        hoverClass="hover:text-red-600 dark:hover:text-red-400"
      />
    </div>
  );
}

function IconBtn({
  icon: Icon,
  label,
  onClick,
  hoverClass,
}: {
  icon: LucideIcon;
  label: string;
  onClick: (e: React.MouseEvent) => void;
  hoverClass?: string;
}) {
  return (
    <Button
      size="sm"
      variant="ghost"
      onClick={onClick}
      title={label}
      aria-label={label}
      className={cn(
        "h-7 w-7 p-0 text-muted-foreground hover:text-foreground",
        hoverClass,
      )}
    >
      <Icon className="w-3.5 h-3.5" />
    </Button>
  );
}

/* ── Status badge — active / inactive / generic tones ────────────── */

export type StatusTone = "success" | "neutral" | "warning" | "danger" | "info";

const TONE_CLASS: Record<StatusTone, string> = {
  success:
    "bg-green-50 text-green-700 border-green-200 dark:bg-green-500/10 dark:text-green-400 dark:border-green-500/20",
  neutral:
    "bg-muted text-muted-foreground border-border",
  warning:
    "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-500/10 dark:text-amber-400 dark:border-amber-500/20",
  danger:
    "bg-red-50 text-red-700 border-red-200 dark:bg-red-500/10 dark:text-red-400 dark:border-red-500/20",
  info:
    "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-500/10 dark:text-blue-400 dark:border-blue-500/20",
};

export function StatusBadge({
  label,
  tone = "neutral",
  className,
}: {
  label: React.ReactNode;
  tone?: StatusTone;
  className?: string;
}) {
  return (
    <Badge
      variant="secondary"
      className={cn(
        "rounded-sm px-2 py-0.5 text-[11px] font-medium border",
        TONE_CLASS[tone],
        className,
      )}
    >
      {label}
    </Badge>
  );
}

/* ── Last-login cell ─────────────────────────────────────────────────
   Pulse dot when seen in the last hour, dim "Never" when null.
   Hover = exact timestamp.                                            */

export function LastLoginCell({ value }: { value: Date | string | null | undefined }) {
  // Capture "now" once at first render so the cell is pure and stable.
  const [now] = useState(() => Date.now());
  const computed = useMemo(() => {
    if (!value) return null;
    const ts = typeof value === "string" ? new Date(value).getTime() : value.getTime();
    return { ts, fresh: now - ts < 60 * 60_000 };
  }, [value, now]);

  if (!computed) {
    return (
      <span className="text-[11px] text-muted-foreground/60 italic">
        Never
      </span>
    );
  }
  const { fresh } = computed;
  return (
    <span
      title={formatDateTime(value)}
      className="inline-flex items-center gap-1.5 text-[12px] tabular-nums"
    >
      <span
        className={cn(
          "w-1.5 h-1.5 rounded-full",
          fresh
            ? "bg-green-500 shadow-[0_0_0_2px_rgba(34,197,94,0.18)] animate-pulse"
            : "bg-muted-foreground/40",
        )}
        aria-hidden
      />
      <span className="text-foreground/90">{formatRelativeTime(value)}</span>
    </span>
  );
}
