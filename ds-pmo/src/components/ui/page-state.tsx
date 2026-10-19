/**
 * Standardized full-page loading and error states.
 * Use these instead of ad-hoc "Loading..." text.
 */

import { AlertCircle } from "lucide-react";
import { Skeleton } from "./skeleton";

interface PageLoadingProps {
  rows?: number;
}

/** Full-page skeleton loader for table-heavy pages */
export function PageLoading({ rows = 6 }: PageLoadingProps) {
  return (
    <div className="space-y-4">
      {/* Header skeleton */}
      <div className="flex items-center justify-between">
        <div className="space-y-2">
          <Skeleton className="h-5 w-40 rounded-sm" />
          <Skeleton className="h-3 w-24 rounded-sm" />
        </div>
        <Skeleton className="h-8 w-28 rounded-sm" />
      </div>

      {/* Table skeleton */}
      <div className="border border-gray-200 dark:border-[#333842] rounded-sm overflow-hidden">
        <div className="bg-gray-50 dark:bg-[#1E2128] border-b border-gray-200 dark:border-[#333842] px-4 py-3 flex gap-6">
          {[120, 200, 80, 80, 100].map((w, i) => (
            <Skeleton key={i} className="h-3 rounded-sm" style={{ width: w }} />
          ))}
        </div>
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="px-4 py-3 flex gap-6 border-b border-gray-100 dark:border-[#333842]">
            {[80, 180, 60, 70, 90].map((w, j) => (
              <Skeleton key={j} className="h-3 rounded-sm" style={{ width: w }} />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

interface InlineLoadingProps {
  message?: string;
}

/** Inline spinner text — for smaller sections */
export function InlineLoading({ message = "Loading…" }: InlineLoadingProps) {
  return (
    <div className="flex items-center gap-2 py-8 justify-center text-sm text-muted-foreground">
      <span className="inline-block w-4 h-4 border-2 border-border border-t-etex-orange rounded-full animate-spin" />
      {message}
    </div>
  );
}

/* ── Etex-branded animated logo spinner ─────────────────────────────
   Two concentric rings rotating in opposite directions with the
   Etex orange gradient, a subtle pulsing glow, and a skeleton
   preview of the page layout underneath.
   ─────────────��───────────────────────────────────────────────────── */

export function ProjectLoading() {
  return (
    <div className="space-y-6">
      {/* Hero: title + reference + badges */}
      <div className="flex flex-col lg:flex-row lg:items-center gap-3">
        <div className="flex-1 min-w-0 space-y-2">
          <Skeleton className="h-3 w-12 rounded-sm" />
          <Skeleton className="h-12 w-[70%] rounded-sm" />
        </div>
        <div className="w-[20%] shrink-0 space-y-2">
          <Skeleton className="h-3 w-16 rounded-sm" />
          <Skeleton className="h-10 w-full rounded-sm" />
        </div>
        <div className="flex items-center gap-3 lg:shrink-0">
          <Skeleton className="h-7 w-24 rounded-sm" />
          <Skeleton className="h-7 w-20 rounded-sm" />
        </div>
      </div>

      {/* Separator */}
      <Skeleton className="h-px w-full" />

      {/* Metadata grid (5 cols) */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-x-5 gap-y-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="space-y-2">
            <Skeleton className="h-3 w-16 rounded-sm" />
            <Skeleton className="h-9 w-full rounded-sm" />
          </div>
        ))}
      </div>

      {/* People row (4 selectors) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-x-5 gap-y-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="space-y-2">
            <Skeleton className="h-3 w-20 rounded-sm" />
            <Skeleton className="h-9 w-full rounded-sm" />
          </div>
        ))}
      </div>

      {/* Objective */}
      <div className="space-y-2">
        <Skeleton className="h-3 w-16 rounded-sm" />
        <Skeleton className="h-16 w-full rounded-sm" />
      </div>

      {/* Section cards */}
      {["Scope", "Overall", "Time", "Cost"].map((title) => (
        <div key={title} className="section-card">
          <div className="section-toggle">
            <div className="flex items-center gap-2 flex-1">
              <Skeleton className="h-4 w-20 rounded-sm" />
              <Skeleton className="h-5 w-5 rounded-full ml-auto" />
            </div>
          </div>
          <div className="section-body">
            <div className="section-body-inner space-y-3">
              {Array.from({ length: 3 }).map((_, j) => (
                <Skeleton key={j} className="h-8 w-full rounded-sm" />
              ))}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

/* ── Project table skeleton ─────────────────────────────────────────
   Matches the project-table layout: coloured left bar, columns
   with staggered widths so it looks like real data.
   ─────────────────────────────────────────────────────────────────── */

const TABLE_COL_WIDTHS = [28, 140, 64, 52, 52, 52, 52, 56, 40, 56, 36, 48, 48, 48];

export function ProjectTableLoading({ rows = 8 }: { rows?: number }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-xs">
        {/* Header */}
        <thead>
          <tr>
            {TABLE_COL_WIDTHS.map((w, i) => (
              <th key={i} className="exec-th" style={{ width: w }}>
                <Skeleton className="h-2.5 w-full rounded-sm bg-etex-gray-200 dark:bg-[#333842]" />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: rows }).map((_, row) => (
            <tr key={row} className="border-b border-gray-100 dark:border-[#333842]">
              {/* Phase bar */}
              <td className="px-0 py-2.5">
                <Skeleton
                  className="h-8 w-1.5 rounded-full mx-auto"
                  style={{ opacity: 0.3 + (row % 3) * 0.2 }}
                />
              </td>
              {/* Data cells with staggered widths */}
              {TABLE_COL_WIDTHS.slice(1).map((w, col) => (
                <td key={col} className="px-2 py-2.5">
                  <Skeleton
                    className="h-3 rounded-sm"
                    style={{ width: `${55 + ((row + col) % 4) * 15}%` }}
                  />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

interface PageErrorProps {
  message?: string;
  onRetry?: () => void;
}

/** Full-page error state */
export function PageError({
  message = "Something went wrong. Please try again.",
  onRetry,
}: PageErrorProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-3 text-center">
      <AlertCircle className="w-8 h-8 text-red-400" />
      <p className="text-sm text-gray-600 dark:text-gray-400 max-w-xs">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-1 text-xs font-medium text-etex-orange hover:underline"
        >
          Try again
        </button>
      )}
    </div>
  );
}

interface InlineErrorProps {
  message: string;
}

/** Inline error banner — sits above a form or section */
export function InlineError({ message }: InlineErrorProps) {
  return (
    <div className="flex items-start gap-2 p-3 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 rounded-sm text-sm text-red-700 dark:text-red-400">
      <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
      {message}
    </div>
  );
}
