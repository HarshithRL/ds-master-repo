"use client";

import { getProjectStatus } from "@/lib/constants";
import { cn, contrastText } from "@/lib/utils";

/**
 * Renders a project's lifecycle status as a solid colored band — same
 * format as the Phase cell on the dashboard table. Single source of
 * truth for status rendering (table + edit form).
 */
export function ProjectStatusBadge({
  status,
  className,
}: {
  status: string | null | undefined;
  className?: string;
}) {
  const def = getProjectStatus(status);
  return (
    <div
      className={cn(
        "inline-flex items-center justify-center text-[10px] font-bold uppercase tracking-wide text-center py-1.5 px-2 rounded-sm",
        className,
      )}
      style={{ backgroundColor: def.color, color: contrastText(def.color) }}
    >
      {def.shortLabel}
    </div>
  );
}
