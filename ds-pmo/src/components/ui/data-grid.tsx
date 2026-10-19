"use client";

import React from "react";
import { cn } from "@/lib/utils";
import { InfoHint } from "@/components/ui/info-hint";

/* ═══════════════════════════════════════════════════════════════════
   DataGrid — unified grid component for tabular data

   • editable=true  → renders `renderEdit` cells (inline editing)
   • editable=false → renders `render` cells (read-only display)
   ═══════════════════════════════════════════════════════════════════ */

/* ── Column definition ──────────────────────────────────────────── */

export interface DataGridColumn<T> {
  id: string;
  header: string;
  hint?: string;
  width: string;
  align?: "left" | "center" | "right";
  /** Extra classes applied to every cell in this column (header included). */
  cellClassName?: string;
  render: (row: T, index: number) => React.ReactNode;
  renderEdit?: (row: T, index: number) => React.ReactNode;
}

/* ── Props ───────────────────────────────────────────────────────── */

export interface DataGridProps<T> {
  columns: DataGridColumn<T>[];
  data: T[];
  editable?: boolean;
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  onRowHover?: (row: T | null) => void;
  rowClassName?: (row: T) => string;
  rowStyle?: (row: T) => React.CSSProperties | undefined;
  maxHeight?: string;
  minWidth?: number;
  footer?: React.ReactNode;
  emptyMessage?: string;
  className?: string;
  /** Custom header rendered inside the wrapper, above the column header row. */
  header?: React.ReactNode;
  /** When true, suppress the built-in column header row (use with a custom `header`). */
  hideHeader?: boolean;
}

/* ── Component ──────────────────────────────────────────────────── */

export function DataGrid<T>({
  columns,
  data,
  editable = false,
  rowKey,
  onRowClick,
  onRowHover,
  rowClassName,
  rowStyle,
  maxHeight,
  minWidth,
  footer,
  emptyMessage = "No data to display.",
  className,
  header,
  hideHeader = false,
}: DataGridProps<T>) {
  const safeData = data ?? [];
  const gridTemplate = columns.map((c) => c.width).join(" ");

  return (
    <div className={cn("dg-wrapper", className)}>
      <div className="overflow-x-auto">
        <div style={minWidth ? { minWidth } : undefined}>
          {header}
          {!hideHeader && (
            <div
              className="dg-header"
              style={{ gridTemplateColumns: gridTemplate }}
            >
              {columns.map((col) => (
                <span
                  key={col.id}
                  className={cn(
                    "dg-th",
                    col.align === "right" && "justify-end",
                    col.align === "center" && "justify-center",
                  )}
                >
                  {col.header}
                  {col.hint && <InfoHint label={col.header} text={col.hint} />}
                </span>
              ))}
            </div>
          )}

          {/* Body */}
          <div
            className={cn(maxHeight && "overflow-y-auto")}
            style={maxHeight ? { maxHeight } : undefined}
          >
            {safeData.length === 0 && (
              <div className="dg-empty">{emptyMessage}</div>
            )}

            {safeData.map((row, idx) => (
              <div
                key={rowKey(row)}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                onMouseEnter={onRowHover ? () => onRowHover(row) : undefined}
                onMouseLeave={onRowHover ? () => onRowHover(null) : undefined}
                className={cn(
                  "dg-row group",
                  onRowClick && "cursor-pointer",
                  rowClassName?.(row),
                )}
                style={{
                  gridTemplateColumns: gridTemplate,
                  ...rowStyle?.(row),
                }}
              >
                {columns.map((col) => (
                  <div
                    key={col.id}
                    className={cn(
                      "min-w-0 wrap-break-word",
                      col.align === "right" && "text-right",
                      col.align === "center" && "text-center",
                      col.cellClassName,
                    )}
                  >
                    {editable && col.renderEdit
                      ? col.renderEdit(row, idx)
                      : col.render(row, idx)}
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      </div>

      {footer}
    </div>
  );
}
