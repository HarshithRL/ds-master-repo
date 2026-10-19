"use client";

import { useMemo } from "react";
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from "lucide-react";
import { cn } from "@/lib/utils";

interface PaginationProps {
  page: number;
  pageSize: number;
  total: number;
  pageSizeOptions?: number[];
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
  className?: string;
  /** Override the label of the unit being paginated, e.g. "projects". */
  unit?: string;
  loading?: boolean;
}

const DEFAULT_PAGE_SIZE_OPTIONS = [10, 25, 50, 100];

/**
 * Build a compact, ellipsis-aware list of page tokens to render.
 * Always shows first + last; collapses the middle as needed.
 * Returns either a number (page index) or "…" (gap).
 */
function buildPageTokens(current: number, total: number): (number | "…")[] {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  const tokens: (number | "…")[] = [1];
  const start = Math.max(2, current - 1);
  const end = Math.min(total - 1, current + 1);
  if (start > 2) tokens.push("…");
  for (let p = start; p <= end; p++) tokens.push(p);
  if (end < total - 1) tokens.push("…");
  tokens.push(total);
  return tokens;
}

/**
 * Compact, accessible pagination control.
 * - Page-size selector + jump-to-first/last + prev/next + numbered pages.
 * - Mobile: hides numbered pages, keeps prev/next + page-size.
 */
export function Pagination({
  page,
  pageSize,
  total,
  pageSizeOptions = DEFAULT_PAGE_SIZE_OPTIONS,
  onPageChange,
  onPageSizeChange,
  className,
  unit = "items",
  loading = false,
}: PaginationProps) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const safePage = Math.min(Math.max(1, page), totalPages);
  const tokens = useMemo(() => buildPageTokens(safePage, totalPages), [safePage, totalPages]);

  const from = total === 0 ? 0 : (safePage - 1) * pageSize + 1;
  const to = Math.min(total, safePage * pageSize);

  const go = (p: number) => {
    if (loading) return;
    const next = Math.min(Math.max(1, p), totalPages);
    if (next !== safePage) onPageChange(next);
  };

  return (
    <div
      className={cn(
        "flex flex-col-reverse sm:flex-row items-stretch sm:items-center justify-between gap-3 text-xs",
        className,
      )}
    >
      {/* Range + page-size selector */}
      <div className="flex items-center gap-3 text-etex-gray-600 dark:text-etex-gray-400">
        <span className="tabular-nums">
          {total === 0 ? (
            <>No {unit}</>
          ) : (
            <>
              Showing <span className="font-medium text-etex-charcoal dark:text-etex-gray-200">{from.toLocaleString()}</span>
              {"–"}
              <span className="font-medium text-etex-charcoal dark:text-etex-gray-200">{to.toLocaleString()}</span> of{" "}
              <span className="font-medium text-etex-charcoal dark:text-etex-gray-200">{total.toLocaleString()}</span> {unit}
            </>
          )}
        </span>
        <label className="hidden sm:inline-flex items-center gap-1.5">
          <span>Rows</span>
          <select
            value={pageSize}
            onChange={(e) => onPageSizeChange(Number(e.target.value))}
            disabled={loading}
            className={cn(
              "h-7 px-2 rounded-sm border border-gray-200 bg-white text-xs text-gray-700",
              "dark:border-[#333842] dark:bg-[#21252B] dark:text-gray-300",
              "focus:outline-none focus:ring-2 focus:ring-etex-orange/40",
              "disabled:opacity-50 disabled:cursor-not-allowed",
            )}
          >
            {pageSizeOptions.map((opt) => (
              <option key={opt} value={opt}>
                {opt}
              </option>
            ))}
          </select>
        </label>
      </div>

      {/* Page nav */}
      <nav
        role="navigation"
        aria-label="Pagination"
        className="flex items-center gap-0.5 sm:gap-1 justify-center"
      >
        <PageBtn aria-label="First page" disabled={loading || safePage === 1} onClick={() => go(1)}>
          <ChevronsLeft size={14} />
        </PageBtn>
        <PageBtn aria-label="Previous page" disabled={loading || safePage === 1} onClick={() => go(safePage - 1)}>
          <ChevronLeft size={14} />
        </PageBtn>

        {/* Numbered pages — hidden on small screens to save space */}
        <ul className="hidden sm:flex items-center gap-0.5">
          {tokens.map((t, i) =>
            t === "…" ? (
              <li
                key={`gap-${i}`}
                aria-hidden="true"
                className="px-1.5 text-etex-gray-400 select-none"
              >
                …
              </li>
            ) : (
              <li key={t}>
                <PageBtn
                  active={t === safePage}
                  aria-label={`Page ${t}`}
                  aria-current={t === safePage ? "page" : undefined}
                  disabled={loading}
                  onClick={() => go(t)}
                >
                  {t}
                </PageBtn>
              </li>
            ),
          )}
        </ul>

        <span className="sm:hidden tabular-nums px-2 text-etex-gray-600 dark:text-etex-gray-400">
          {safePage} / {totalPages}
        </span>

        <PageBtn
          aria-label="Next page"
          disabled={loading || safePage === totalPages}
          onClick={() => go(safePage + 1)}
        >
          <ChevronRight size={14} />
        </PageBtn>
        <PageBtn
          aria-label="Last page"
          disabled={loading || safePage === totalPages}
          onClick={() => go(totalPages)}
        >
          <ChevronsRight size={14} />
        </PageBtn>
      </nav>
    </div>
  );
}

function PageBtn({
  children,
  active,
  disabled,
  onClick,
  ...rest
}: {
  children: React.ReactNode;
  active?: boolean;
  disabled?: boolean;
  onClick?: () => void;
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "inline-flex items-center justify-center h-7 min-w-7 px-2 rounded-sm",
        "text-xs font-medium tabular-nums select-none",
        "transition-colors duration-100",
        "focus:outline-none focus-visible:ring-2 focus-visible:ring-etex-orange/50 focus-visible:ring-offset-1",
        "disabled:opacity-40 disabled:pointer-events-none",
        active
          ? "bg-etex-orange text-white shadow-sm"
          : "text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-white/5",
      )}
      {...rest}
    >
      {children}
    </button>
  );
}
