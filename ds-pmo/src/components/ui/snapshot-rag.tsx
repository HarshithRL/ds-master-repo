"use client";

import { cn } from "@/lib/utils";

/**
 * Static RAG colors for the small dots shown in snapshot tables.
 * The interactive RAG editors (RAGIndicator / RagWithLabel) use richer
 * variants — these are intentionally simple, read-only swatches.
 */
export const SNAPSHOT_RAG_COLORS: Record<string, string> = {
  RED: "bg-red-600",
  AMBER: "bg-amber-400",
  GREEN: "bg-emerald-500",
};

/** Round 2.5×2.5 colored dot — used by snapshot tables. */
export function SnapshotRagDot({
  value,
  label,
  size = "md",
}: {
  value: string | null | undefined;
  label?: string;
  size?: "sm" | "md";
}) {
  const dot = (
    <span
      className={cn(
        "rounded-full inline-block",
        size === "sm" ? "w-2 h-2" : "w-2.5 h-2.5",
        value ? SNAPSHOT_RAG_COLORS[value] ?? "bg-gray-300" : "bg-gray-300",
      )}
      title={value ?? undefined}
    />
  );

  if (!value && !label) {
    return <span className="text-muted-foreground">—</span>;
  }
  if (!value) return null;

  if (!label) return dot;

  return (
    <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
      {dot}
      {label}
    </span>
  );
}
