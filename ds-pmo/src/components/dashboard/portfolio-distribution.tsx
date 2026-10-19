"use client";

import { useMemo, memo, useState, useCallback } from "react";
import { getPhaseByKey, getTierByKey, getGateByKey, GATES } from "@/lib/constants";
import { formatCurrency, cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { ExpandableWidget } from "./expandable-widget";
import type { DashboardFilters } from "@/types";

type Variant = "phase" | "gate" | "tier" | "division";

interface DistributionItem {
  phase?: string;
  gate?: string;
  tier?: string;
  factory?: string;
  division?: string;
  label?: string;
  count: number;
  eac: number;
}

interface PortfolioDistributionProps {
  variant: Variant;
  data: DistributionItem[];
  title: string;
  totalProjects?: number;
  loading?: boolean;
  filters?: DashboardFilters;
  onFiltersChange?: (next: DashboardFilters) => void;
}

const TIER_COLORS: Record<string, string> = {
  TIER_1: "#E8713A",
  TIER_2: "#3B82F6",
  TIER_3: "#6B7280",
};

const DIVISION_COLORS = [
  "#E8713A", "#3B82F6", "#22C55E", "#8B5CF6", "#EAB308", "#14B8A6",
];

const GATE_ORDER: Record<string, number> = Object.fromEntries(
  GATES.map((g, i) => [g.key, i]),
);

function getItemKey(variant: Variant, item: DistributionItem): string {
  if (variant === "phase") return item.phase ?? "";
  if (variant === "gate") return item.gate ?? "";
  if (variant === "tier") return item.tier ?? "";
  return item.division ?? item.label ?? "";
}

function getItemLabel(variant: Variant, item: DistributionItem): string {
  if (variant === "phase") {
    const phase = getPhaseByKey(item.phase ?? "");
    return phase?.shortLabel ?? item.phase ?? "—";
  }
  if (variant === "gate") {
    const gate = getGateByKey(item.gate ?? "");
    return gate?.label ?? item.gate ?? "—";
  }
  if (variant === "tier") {
    const tier = getTierByKey(item.tier ?? "");
    return tier?.label ?? item.tier ?? "—";
  }
  return item.division ?? item.label ?? "—";
}

function getItemColor(variant: Variant, item: DistributionItem, index: number): string {
  if (variant === "phase") {
    const phase = getPhaseByKey(item.phase ?? "");
    return phase?.color ?? "#6B7280";
  }
  if (variant === "gate") {
    const gate = getGateByKey(item.gate ?? "");
    return gate?.color ?? "#6B7280";
  }
  if (variant === "tier") {
    return TIER_COLORS[item.tier ?? ""] ?? "#6B7280";
  }
  return DIVISION_COLORS[index % DIVISION_COLORS.length];
}

function getPhaseOrder(phaseKey: string): number {
  const phase = getPhaseByKey(phaseKey);
  return phase?.phaseNumber ?? 999;
}

/**
 * Some palette entries (notably the WHITE gate, #F9FAFB) are essentially
 * invisible against the card background. Detect those so we can paint a
 * subtle border around the dot, the stacked segment, and the bar.
 */
function needsBorder(hex: string): boolean {
  const m = hex.trim().match(/^#?([0-9a-f]{6})$/i);
  if (!m) return false;
  const v = parseInt(m[1], 16);
  const r = (v >> 16) & 0xff;
  const g = (v >> 8) & 0xff;
  const b = v & 0xff;
  // Perceived luminance (Rec. 709). > ~0.92 ≈ needs a border on white bg.
  const lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
  return lum > 0.92;
}

type ChartItem = DistributionItem & {
  key: string;
  displayLabel: string;
  fill: string;
  light: boolean;
};

function DistributionSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="px-5 pt-3 pb-4 space-y-3">
      <Skeleton className="h-2 w-full rounded-full" />
      <div className="space-y-2.5 pt-1">
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i}>
            <div className="flex items-center justify-between mb-1.5">
              <div className="flex items-center gap-2">
                <Skeleton className="w-2.5 h-2.5 rounded-full" />
                <Skeleton className="h-3 w-20" />
              </div>
              <Skeleton className="h-3 w-14" />
            </div>
            <Skeleton className="h-2 rounded-full" style={{ width: `${85 - i * 10}%` }} />
          </div>
        ))}
      </div>
    </div>
  );
}

export const PortfolioDistribution = memo(function PortfolioDistribution({
  variant,
  data,
  title,
  totalProjects,
  loading,
  filters,
  onFiltersChange,
}: PortfolioDistributionProps) {
  const [hoveredKey, setHoveredKey] = useState<string | null>(null);

  const chartData = useMemo<ChartItem[]>(() => {
    let items: DistributionItem[];
    if (variant === "phase") {
      items = [...data].sort(
        (a, b) => getPhaseOrder(a.phase ?? "") - getPhaseOrder(b.phase ?? ""),
      );
    } else if (variant === "gate") {
      items = [...data].sort(
        (a, b) =>
          (GATE_ORDER[a.gate ?? ""] ?? 999) - (GATE_ORDER[b.gate ?? ""] ?? 999),
      );
    } else if (variant === "division") {
      items = [...data]
        .filter((d) => d.count > 0)
        .sort((a, b) => b.eac - a.eac)
        .slice(0, 6);
    } else {
      items = data;
    }
    return items.map((item, i) => {
      const fill = getItemColor(variant, item, i);
      return {
        ...item,
        key: getItemKey(variant, item),
        displayLabel: getItemLabel(variant, item),
        fill,
        light: needsBorder(fill),
      };
    });
  }, [data, variant]);

  const totals = useMemo(() => {
    const count = chartData.reduce((s, d) => s + d.count, 0);
    const eac = chartData.reduce((s, d) => s + d.eac, 0);
    return { count, eac };
  }, [chartData]);

  // Only phase/tier/division have a corresponding URL filter; gate is
  // display-only for now.
  const filterKey: "phase" | "tier" | "division" | null =
    variant === "gate" ? null : (variant as "phase" | "tier" | "division");
  const activeFilters = useMemo(
    () => (filterKey ? ((filters?.[filterKey] as string[] | undefined) ?? []) : []),
    [filters, filterKey],
  );

  const handleToggle = useCallback(
    (key: string) => {
      if (!filterKey || !onFiltersChange || !filters || !key) return;
      const isActive = activeFilters.includes(key);
      const nextValues = isActive
        ? activeFilters.filter((v) => v !== key)
        : [...activeFilters, key];
      const next: DashboardFilters = { ...filters };
      if (nextValues.length === 0) {
        delete (next as Record<string, unknown>)[filterKey];
      } else {
        (next as Record<string, string[]>)[filterKey] = nextValues;
      }
      onFiltersChange(next);
    },
    [activeFilters, filterKey, filters, onFiltersChange],
  );

  if (loading) {
    return (
      <ExpandableWidget title={title}>
        <DistributionSkeleton rows={variant === "phase" ? 6 : 3} />
      </ExpandableWidget>
    );
  }

  // Bar-width denominator: phase & gate scale by count vs total portfolio
  // (so bars are comparable); tier/division scale by their own max EAC.
  const denom =
    variant === "phase" || variant === "gate"
      ? totalProjects ?? Math.max(totals.count, 1)
      : Math.max(...chartData.map((d) => d.eac), 1);

  const isCountPrimary = variant === "phase" || variant === "gate";

  return (
    <ExpandableWidget title={title}>
      {chartData.length === 0 ? (
        <div className="px-4 pt-4 pb-4 text-xs text-etex-gray-400 text-center">
          No data
        </div>
      ) : (
        <div className="px-5 pt-3.5 pb-4">
          <StackedOverview
            data={chartData}
            total={totals.count}
            hoveredKey={hoveredKey}
            activeKeys={activeFilters}
            onHover={setHoveredKey}
            onToggle={handleToggle}
            canToggle={!!filterKey && !!onFiltersChange}
          />

          <div className="mt-3 pt-3 border-t border-(--border-subtle) space-y-0.5">
            {chartData.map((d) => {
              const value = isCountPrimary ? d.count : d.eac;
              const width = denom > 0 ? (value / denom) * 100 : 0;
              const sharePct =
                totals.count > 0 ? (d.count / totals.count) * 100 : 0;
              const isActive = activeFilters.includes(d.key);
              const isHovered = hoveredKey === d.key;
              const dimmed = hoveredKey !== null && !isHovered;
              const interactive =
                !!filterKey && !!onFiltersChange && !!d.key;
              return (
                <DistributionRow
                  key={d.key || d.displayLabel}
                  item={d}
                  width={width}
                  sharePct={sharePct}
                  isCountPrimary={isCountPrimary}
                  isActive={isActive}
                  isHovered={isHovered}
                  dimmed={dimmed}
                  interactive={interactive}
                  onToggle={handleToggle}
                  onHover={setHoveredKey}
                />
              );
            })}
          </div>

          {activeFilters.length > 0 && onFiltersChange && filterKey && (
            <div className="mt-3 flex items-center justify-between pt-1 border-t border-(--border-subtle)">
              <span className="text-[10px] text-etex-gray-500 dark:text-gray-400">
                {activeFilters.length} filter
                {activeFilters.length > 1 ? "s" : ""} active
              </span>
              <button
                type="button"
                onClick={() => {
                  const next: DashboardFilters = { ...filters };
                  delete (next as Record<string, unknown>)[filterKey];
                  onFiltersChange(next);
                }}
                className="text-[10px] font-medium text-etex-orange hover:underline cursor-pointer"
              >
                Clear
              </button>
            </div>
          )}
        </div>
      )}
    </ExpandableWidget>
  );
});

/* ── Stacked overview bar ─────────────────────────────────────── */

function StackedOverview({
  data,
  total,
  hoveredKey,
  activeKeys,
  onHover,
  onToggle,
  canToggle,
}: {
  data: ChartItem[];
  total: number;
  hoveredKey: string | null;
  activeKeys: string[];
  onHover: (key: string | null) => void;
  onToggle: (key: string) => void;
  canToggle: boolean;
}) {
  if (total === 0) return null;
  const hasActive = activeKeys.length > 0;
  return (
    <div className="flex w-full h-5 rounded-sm overflow-hidden bg-etex-gray-100 dark:bg-[#282C34] ring-1 ring-inset ring-black/5 dark:ring-white/5">
      {data.map((d) => {
        const width = (d.count / total) * 100;
        if (width === 0) return null;
        const isHovered = hoveredKey === d.key;
        const isActive = activeKeys.includes(d.key);
        const dimmed =
          (hoveredKey !== null && !isHovered) || (hasActive && !isActive && !isHovered);
        return (
          <button
            type="button"
            key={d.key || d.displayLabel}
            className={cn(
              "h-full transition-all duration-200 first:rounded-l-sm last:rounded-r-sm",
              canToggle ? "cursor-pointer" : "cursor-default",
              d.light && "ring-1 ring-inset ring-etex-gray-300 dark:ring-gray-500",
            )}
            style={{
              width: `${width}%`,
              backgroundColor: d.fill,
              opacity: dimmed ? 0.35 : 1,
              transform: isHovered ? "scaleY(1.15)" : undefined,
              transformOrigin: "center",
            }}
            title={`${d.displayLabel}: ${d.count} proj (${width.toFixed(1)}%)`}
            onMouseEnter={() => onHover(d.key)}
            onMouseLeave={() => onHover(null)}
            onClick={canToggle ? () => onToggle(d.key) : undefined}
          />
        );
      })}
    </div>
  );
}

/* ── Per-item row ─────────────────────────────────────────────── */

function DistributionRow({
  item,
  width,
  sharePct,
  isCountPrimary,
  isActive,
  isHovered,
  dimmed,
  interactive,
  onToggle,
  onHover,
}: {
  item: ChartItem;
  width: number;
  sharePct: number;
  isCountPrimary: boolean;
  isActive: boolean;
  isHovered: boolean;
  dimmed: boolean;
  interactive: boolean;
  onToggle: (key: string) => void;
  onHover: (key: string | null) => void;
}) {
  // Always label counts with "proj" for clarity. Primary is right-aligned
  // and bold: count for phase/gate, EAC for tier/division. Secondary is the
  // other measure shown a tone down.
  const projLabel = `${item.count} proj`;
  const eacLabel = formatCurrency(item.eac, { compact: true });
  const primaryNumber = isCountPrimary ? String(item.count) : eacLabel;
  const primarySuffix = isCountPrimary ? "proj" : null;
  const secondary = isCountPrimary ? eacLabel : projLabel;

  const lightFill = item.light;
  const dotStyle: React.CSSProperties = {
    backgroundColor: item.fill,
    boxShadow:
      isHovered || isActive ? `0 0 0 3px ${item.fill}33` : undefined,
  };

  const barFillStyle: React.CSSProperties = {
    width: `${Math.max(width, 1.5)}%`,
    backgroundColor: item.fill,
    filter: isHovered ? "saturate(1.15)" : undefined,
    boxShadow:
      isHovered || isActive ? `0 0 8px ${item.fill}55` : undefined,
  };

  const content = (
    <>
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2 min-w-0">
          <span
            className={cn(
              "w-2.5 h-2.5 rounded-full shrink-0 transition-shadow duration-150",
              lightFill && "ring-1 ring-inset ring-etex-gray-300 dark:ring-gray-500",
            )}
            style={dotStyle}
          />
          <span
            className={cn(
              "text-xs truncate transition-colors",
              isActive
                ? "font-semibold text-(--foreground)"
                : "text-etex-gray-600 dark:text-gray-400",
              !isActive &&
                isHovered &&
                "text-etex-gray-800 dark:text-gray-200",
            )}
          >
            {item.displayLabel}
          </span>
        </div>
        <div className="flex items-baseline gap-2 shrink-0 tabular-nums">
          <span
            className={cn(
              "text-[10px] transition-opacity",
              isHovered || isActive
                ? "text-etex-gray-500 dark:text-gray-400 opacity-100"
                : "text-etex-gray-400 opacity-80",
            )}
          >
            {secondary}
          </span>
          <span
            className={cn(
              "inline-flex items-baseline gap-1 text-xs font-semibold tabular-nums",
              isActive
                ? "text-(--foreground)"
                : "text-etex-gray-700 dark:text-gray-300",
            )}
          >
            <span>{primaryNumber}</span>
            {primarySuffix && (
              <span className="text-[9px] font-medium uppercase tracking-wider text-etex-gray-400 dark:text-gray-500">
                {primarySuffix}
              </span>
            )}
          </span>
          <span
            className={cn(
              "text-[10px] tabular-nums w-10 text-right transition-opacity duration-150",
              isHovered || isActive
                ? "opacity-100 text-etex-gray-600 dark:text-gray-300"
                : "opacity-0",
            )}
            aria-hidden={!isHovered && !isActive}
          >
            {sharePct.toFixed(1)}%
          </span>
        </div>
      </div>
      <div
        className={cn(
          "relative h-2 bg-etex-gray-100 dark:bg-[#282C34] rounded-full overflow-hidden",
          lightFill && "ring-1 ring-inset ring-etex-gray-300 dark:ring-gray-500",
        )}
      >
        <div
          className="h-full rounded-full transition-[width,filter] duration-700 ease-out"
          style={barFillStyle}
        />
      </div>
    </>
  );

  const baseClass = cn(
    "block w-full text-left rounded-md px-2 py-1.5 -mx-2 transition-all duration-150",
    isActive
      ? "bg-etex-gray-100/70 dark:bg-[#282C34]/70 ring-1 ring-inset ring-etex-orange/40"
      : isHovered
        ? "bg-etex-gray-50 dark:bg-[#23262C]"
        : "bg-transparent",
    dimmed && !isActive && "opacity-55",
  );

  if (!interactive) {
    return (
      <div
        className={baseClass}
        onMouseEnter={() => onHover(item.key)}
        onMouseLeave={() => onHover(null)}
      >
        {content}
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={() => onToggle(item.key)}
      onMouseEnter={() => onHover(item.key)}
      onMouseLeave={() => onHover(null)}
      className={cn(baseClass, "cursor-pointer focus:outline-none focus:ring-1 focus:ring-etex-orange/40")}
      aria-pressed={isActive}
      title={isActive ? `Remove ${item.displayLabel} filter` : `Filter by ${item.displayLabel}`}
    >
      {content}
    </button>
  );
}
