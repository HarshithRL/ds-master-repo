"use client";

/* ═══════════════════════════════════════════════════════════════════════
   DataTable — unified, SAP Fiori-flavored admin table.

   Drop-in for any list view that needs:
   • Sticky header with subtle accent
   • Optional column sorting (client-side by default)
   • Integrated toolbar (search + actions + count)
   • Pagination
   • Empty + loading states
   • Optional row expansion (audit log style)
   • Theme-aware (uses CSS vars defined in globals.css)

   Server pagination/sort: pass `pagination` / `sort` controlled state
   and `manualSort` to skip the client-side compare.
   ═══════════════════════════════════════════════════════════════════════ */

import * as React from "react";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  Search,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

/* ── Column ───────────────────────────────────────────────────────────── */

export type DataTableAlign = "left" | "center" | "right";

export interface DataTableColumn<T> {
  /** Stable identifier; also used as sort key fallback. */
  key: string;
  header: React.ReactNode;
  /** Pixel/percent/minmax-style width applied to the <th>. */
  width?: string;
  align?: DataTableAlign;
  sortable?: boolean;
  /** Pull a sortable primitive from the row. Falls back to row[key]. */
  sortValue?: (row: T) => string | number | Date | null | undefined;
  render: (row: T, index: number) => React.ReactNode;
  /** Add a tabular-nums + mono treatment to cells in this column. */
  numeric?: boolean;
  /** Hide on small screens. */
  hideBelowSm?: boolean;
  /** Custom td class merged in. */
  className?: string;
  /** Custom th class merged in. */
  headerClassName?: string;
}

/* ── Pagination ───────────────────────────────────────────────────────── */

export interface DataTablePagination {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
}

/* ── Sort state ───────────────────────────────────────────────────────── */

export interface DataTableSort {
  key: string;
  dir: "asc" | "desc";
}

/* ── Toolbar ──────────────────────────────────────────────────────────── */

export interface DataTableToolbar {
  search?: {
    value: string;
    onChange: (v: string) => void;
    placeholder?: string;
  };
  /** Right-aligned button(s) — e.g. "Add user". */
  actions?: React.ReactNode;
  /** Optional left-side content (filter chips, category pills, etc). */
  leading?: React.ReactNode;
  /** Optional row of secondary controls below the main bar. */
  extra?: React.ReactNode;
}

/* ── Props ────────────────────────────────────────────────────────────── */

export interface DataTableProps<T> {
  columns: DataTableColumn<T>[];
  data: T[];
  rowKey: (row: T) => string;
  loading?: boolean;
  /** Replaces the body with skeleton rows of this height. */
  skeletonRows?: number;
  emptyTitle?: string;
  emptyMessage?: string;
  emptyIcon?: React.ReactNode;
  toolbar?: DataTableToolbar;
  pagination?: DataTablePagination;
  onRowClick?: (row: T) => void;
  /** Render an expanded sub-row beneath a clicked row. */
  expandedRowRender?: (row: T) => React.ReactNode;
  /** Which row is currently expanded (by rowKey). */
  expandedRowKey?: string | null;
  /** Controlled sort state. Omit to let the table own it. */
  sort?: DataTableSort | null;
  onSortChange?: (sort: DataTableSort | null) => void;
  /** Skip client-side sorting (server already sorted). */
  manualSort?: boolean;
  /** Match-the-row-height (default 36px). */
  density?: "compact" | "comfortable";
  /** Append a footer row (e.g., totals). */
  footer?: React.ReactNode;
  /** Override the table min-width for horizontal scroll. */
  minWidth?: number;
  className?: string;
}

/* ─────────────────────────────────────────────────────────────────────── */

export function DataTable<T>({
  columns,
  data,
  rowKey,
  loading,
  skeletonRows = 8,
  emptyTitle = "No records",
  emptyMessage = "Nothing to show here yet.",
  emptyIcon,
  toolbar,
  pagination,
  onRowClick,
  expandedRowRender,
  expandedRowKey,
  sort: controlledSort,
  onSortChange,
  manualSort,
  density = "compact",
  footer,
  minWidth,
  className,
}: DataTableProps<T>) {
  // ── Sort state (uncontrolled fallback)
  const [internalSort, setInternalSort] = React.useState<DataTableSort | null>(null);
  const sort = controlledSort ?? internalSort;

  const handleSort = (col: DataTableColumn<T>) => {
    if (!col.sortable) return;
    const next: DataTableSort | null =
      !sort || sort.key !== col.key
        ? { key: col.key, dir: "asc" }
        : sort.dir === "asc"
          ? { key: col.key, dir: "desc" }
          : null;
    if (onSortChange) onSortChange(next);
    else setInternalSort(next);
  };

  // ── Client-side sort (skipped if `manualSort`)
  const sortedData = React.useMemo(() => {
    if (manualSort || !sort) return data;
    const col = columns.find((c) => c.key === sort.key);
    if (!col) return data;
    const accessor: (r: T) => unknown =
      col.sortValue ?? ((r) => (r as Record<string, unknown>)[sort.key]);
    const dir = sort.dir === "asc" ? 1 : -1;
    return [...data].sort((a, b) => {
      const av = accessor(a);
      const bv = accessor(b);
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      if (av instanceof Date && bv instanceof Date) return (av.getTime() - bv.getTime()) * dir;
      if (typeof av === "number" && typeof bv === "number") return (av - bv) * dir;
      return String(av).localeCompare(String(bv), undefined, { numeric: true }) * dir;
    });
  }, [data, sort, columns, manualSort]);

  const rowH = density === "compact" ? "h-9" : "h-11";
  const cellPad = density === "compact" ? "py-2 px-3" : "py-2.5 px-4";

  const colSpan = columns.length;

  return (
    <div className={cn("dt-wrapper", className)}>
      {toolbar && <Toolbar toolbar={toolbar} />}

      <div className="dt-scroll">
        <table
          className="w-full border-separate border-spacing-0"
          style={minWidth ? { minWidth } : undefined}
        >
          <colgroup>
            {columns.map((c) => (
              <col
                key={c.key}
                style={c.width ? { width: c.width } : undefined}
                className={cn(c.hideBelowSm && "hidden sm:table-column")}
              />
            ))}
          </colgroup>

          <thead className="dt-thead">
            <tr>
              {columns.map((col) => {
                const active = sort?.key === col.key;
                const Icon = !col.sortable
                  ? null
                  : !active
                    ? ArrowUpDown
                    : sort.dir === "asc"
                      ? ArrowUp
                      : ArrowDown;
                return (
                  <th
                    key={col.key}
                    onClick={col.sortable ? () => handleSort(col) : undefined}
                    className={cn(
                      "dt-th",
                      cellPad,
                      col.align === "right" && "text-right",
                      col.align === "center" && "text-center",
                      col.sortable && "cursor-pointer select-none hover:text-white",
                      col.hideBelowSm && "hidden sm:table-cell",
                      col.headerClassName,
                    )}
                  >
                    <span
                      className={cn(
                        "inline-flex items-center gap-1",
                        col.align === "right" && "justify-end w-full",
                        col.align === "center" && "justify-center w-full",
                      )}
                    >
                      {col.header}
                      {Icon && (
                        <Icon
                          className={cn(
                            "w-3 h-3 transition-opacity",
                            active ? "opacity-100 text-etex-orange-light" : "opacity-40",
                          )}
                        />
                      )}
                    </span>
                  </th>
                );
              })}
            </tr>
          </thead>

          <tbody>
            {loading ? (
              Array.from({ length: skeletonRows }).map((_, i) => (
                <tr key={i} className={cn("dt-row", rowH)}>
                  {columns.map((c) => (
                    <td
                      key={c.key}
                      className={cn("dt-td", cellPad, c.hideBelowSm && "hidden sm:table-cell")}
                    >
                      <Skeleton className="h-3.5 w-full max-w-32" />
                    </td>
                  ))}
                </tr>
              ))
            ) : sortedData.length === 0 ? (
              <tr>
                <td colSpan={colSpan} className="p-0">
                  <EmptyState title={emptyTitle} message={emptyMessage} icon={emptyIcon} />
                </td>
              </tr>
            ) : (
              sortedData.map((row, i) => {
                const key = rowKey(row);
                const isExpanded = expandedRowKey === key;
                return (
                  <React.Fragment key={key}>
                    <tr
                      onClick={onRowClick ? () => onRowClick(row) : undefined}
                      className={cn(
                        "dt-row",
                        rowH,
                        onRowClick && "cursor-pointer",
                        isExpanded && "dt-row-expanded",
                      )}
                    >
                      {columns.map((col) => (
                        <td
                          key={col.key}
                          className={cn(
                            "dt-td",
                            cellPad,
                            col.align === "right" && "text-right",
                            col.align === "center" && "text-center",
                            col.numeric && "font-mono tabular-nums",
                            col.hideBelowSm && "hidden sm:table-cell",
                            col.className,
                          )}
                        >
                          {col.render(row, i)}
                        </td>
                      ))}
                    </tr>
                    {isExpanded && expandedRowRender && (
                      <tr className="dt-row-detail">
                        <td colSpan={colSpan} className="p-0">
                          {expandedRowRender(row)}
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })
            )}
          </tbody>

          {footer && <tfoot className="dt-tfoot">{footer}</tfoot>}
        </table>
      </div>

      {pagination && pagination.total > pagination.pageSize && (
        <Pagination pagination={pagination} />
      )}
    </div>
  );
}

/* ── Toolbar ─────────────────────────────────────────────────────────── */

function Toolbar({ toolbar }: { toolbar: DataTableToolbar }) {
  return (
    <div className="dt-toolbar">
      <div className="flex items-center gap-2 flex-wrap">
        {toolbar.leading}
        {toolbar.search && (
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground pointer-events-none" />
            <Input
              value={toolbar.search.value}
              onChange={(e) => toolbar.search!.onChange(e.target.value)}
              placeholder={toolbar.search.placeholder ?? "Search..."}
              className="pl-8 h-8 w-56 text-xs"
            />
            {toolbar.search.value && (
              <button
                type="button"
                onClick={() => toolbar.search!.onChange("")}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                aria-label="Clear search"
              >
                <X className="w-3 h-3" />
              </button>
            )}
          </div>
        )}
        <div className="flex-1" />
        {toolbar.actions}
      </div>
      {toolbar.extra && <div className="mt-2">{toolbar.extra}</div>}
    </div>
  );
}

/* ── Pagination ──────────────────────────────────────────────────────── */

function Pagination({ pagination }: { pagination: DataTablePagination }) {
  const { page, pageSize, total, onPageChange } = pagination;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const from = (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);

  return (
    <div className="dt-pagination">
      <span className="text-[11px] text-muted-foreground tabular-nums">
        {total === 0 ? "0 of 0" : `${from}–${to} of ${total.toLocaleString()}`}
      </span>
      <div className="flex items-center gap-0.5">
        <Button
          variant="ghost"
          size="sm"
          className="h-7 w-7 p-0"
          disabled={page <= 1}
          onClick={() => onPageChange(1)}
          aria-label="First page"
        >
          <ChevronsLeft className="w-3.5 h-3.5" />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="h-7 w-7 p-0"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
          aria-label="Previous page"
        >
          <ChevronLeft className="w-3.5 h-3.5" />
        </Button>
        <span className="px-2 text-[11px] font-medium tabular-nums">
          {page} / {totalPages}
        </span>
        <Button
          variant="ghost"
          size="sm"
          className="h-7 w-7 p-0"
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
          aria-label="Next page"
        >
          <ChevronRight className="w-3.5 h-3.5" />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="h-7 w-7 p-0"
          disabled={page >= totalPages}
          onClick={() => onPageChange(totalPages)}
          aria-label="Last page"
        >
          <ChevronsRight className="w-3.5 h-3.5" />
        </Button>
      </div>
    </div>
  );
}

/* ── Empty state ─────────────────────────────────────────────────────── */

function EmptyState({
  title,
  message,
  icon,
}: {
  title: string;
  message: string;
  icon?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
      <div className="w-10 h-10 rounded-full bg-muted/60 flex items-center justify-center mb-3 text-muted-foreground">
        {icon ?? <Search className="w-4 h-4" />}
      </div>
      <h3 className="text-xs font-semibold text-foreground mb-1">{title}</h3>
      <p className="text-[11px] text-muted-foreground max-w-xs">{message}</p>
    </div>
  );
}
