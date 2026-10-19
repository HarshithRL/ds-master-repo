"use client";

import { useState } from "react";
import { Filter } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { formatCurrency, cn } from "@/lib/utils";
import { EXECUTION_PHASES } from "@/lib/constants";
import { ExpandableWidget } from "./expandable-widget";
import type { DashboardFilters, PortfolioSummary, ProjectListItem } from "@/types";

/* ── Types ───────────────────────────────────────────────────────── */

type Sentiment = "positive" | "negative" | "neutral";

interface DonutSegment {
  key: string;
  value: number;
  color: string;
  label: string;
}

interface KpiCardProps {
  label: string;
  active?: boolean;
  onClick?: () => void;
  children: React.ReactNode;
}

interface HeroKPIStripProps {
  portfolio: PortfolioSummary | null;
  projects: ProjectListItem[];
  loading: boolean;
  filters?: DashboardFilters;
  onFiltersChange?: (next: DashboardFilters) => void;
}

/* ── Skeleton ────────────────────────────────────────────────────── */

function StripSkeleton() {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="card-compact">
          <div className="flex items-center justify-between px-5 py-3 border-b border-(--border)">
            <div className="flex items-center gap-2.5">
              <span className="w-1 h-4 rounded-full bg-etex-orange" />
              <Skeleton className="h-2.5 w-24" />
            </div>
          </div>
          <div className="px-4 py-7 flex items-center gap-5">
            <Skeleton className="h-29 w-29 rounded-full" />
            <div className="flex-1 space-y-2.5">
              <Skeleton className="h-3.5 w-24" />
              <Skeleton className="h-3.5 w-20" />
              <Skeleton className="h-3 w-16" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

/* ── Filter helpers ──────────────────────────────────────────────── */

function patchIsActive(filters: DashboardFilters | undefined, patch: Partial<DashboardFilters>): boolean {
  if (!filters) return false;
  for (const [k, v] of Object.entries(patch)) {
    const current = filters[k as keyof DashboardFilters];
    if (Array.isArray(v)) {
      if (
        !Array.isArray(current) ||
        v.length !== current.length ||
        !v.every((x) => (current as string[]).includes(x))
      )
        return false;
    } else if (current !== v) {
      return false;
    }
  }
  return true;
}

function togglePatch(filters: DashboardFilters, patch: Partial<DashboardFilters>): DashboardFilters {
  if (patchIsActive(filters, patch)) {
    const next: DashboardFilters = { ...filters };
    for (const k of Object.keys(patch)) {
      delete (next as Record<string, unknown>)[k];
    }
    return next;
  }
  return { ...filters, ...patch };
}

/* ── Donut chart — segment hover dims siblings ───────────────────── */

function Donut({
  segments,
  size = 84,
  thickness = 10,
  hovered: hoveredProp,
  onHoverChange,
  children,
}: {
  segments: DonutSegment[];
  size?: number;
  thickness?: number;
  hovered?: string | null;
  onHoverChange?: (key: string | null) => void;
  children?: React.ReactNode;
}) {
  const [internalHovered, setInternalHovered] = useState<string | null>(null);
  const hovered = hoveredProp !== undefined ? hoveredProp : internalHovered;
  const setHovered = (key: string | null) => {
    if (hoveredProp === undefined) setInternalHovered(key);
    onHoverChange?.(key);
  };
  const r = (size - thickness) / 2;
  const cx = size / 2;
  const cy = size / 2;
  const C = 2 * Math.PI * r;
  const total = segments.reduce((s, x) => s + Math.max(0, x.value), 0);
  const hasData = total > 0;
  let cumulative = 0;

  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90 overflow-visible">
        <circle
          cx={cx}
          cy={cy}
          r={r}
          fill="none"
          strokeWidth={thickness}
          className="stroke-etex-gray-100 dark:stroke-[#23262C]"
        />
        {hasData &&
          segments.map((s) => {
            const v = Math.max(0, s.value);
            if (v === 0) return null;
            const frac = v / total;
            const dash = frac * C;
            const gap = C - dash;
            const offset = -cumulative * C;
            cumulative += frac;
            const isHovered = hovered === s.key;
            const dimmed = hovered !== null && !isHovered;
            const stroke = isHovered ? thickness + 5 : thickness;
            return (
              <circle
                key={s.key}
                cx={cx}
                cy={cy}
                r={r}
                fill="none"
                strokeWidth={stroke}
                stroke={s.color}
                strokeDasharray={`${dash} ${gap}`}
                strokeDashoffset={offset}
                style={{
                  opacity: dimmed ? 0.3 : 1,
                  filter: isHovered ? `drop-shadow(0 0 6px ${s.color}66)` : undefined,
                  transition: "opacity 150ms ease, stroke-width 180ms ease, filter 180ms ease",
                  cursor: "pointer",
                }}
                onMouseEnter={() => setHovered(s.key)}
                onMouseLeave={() => setHovered(null)}
              >
                <title>{`${s.label}: ${s.value}`}</title>
              </circle>
            );
          })}
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center pointer-events-none leading-none">
        {children}
      </div>
    </div>
  );
}

/* ── KPI card wrapper ────────────────────────────────────────────── */

function KpiCard({ label, active, onClick, children }: KpiCardProps) {
  const interactive = Boolean(onClick);

  const headerRight = interactive ? (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      title={active ? "Remove filter" : "Filter the dashboard"}
      className={cn(
        "inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider cursor-pointer transition-colors focus:outline-none focus:ring-1 focus:ring-etex-orange/40",
        active
          ? "bg-etex-orange/10 text-etex-orange ring-1 ring-inset ring-etex-orange/40"
          : "text-etex-gray-400 hover:text-etex-orange hover:bg-etex-gray-100 dark:hover:bg-[#282C34]",
      )}
    >
      <Filter className="w-3 h-3" />
      {active ? "filtered" : "filter"}
    </button>
  ) : undefined;

  return (
    <ExpandableWidget
      title={label}
      headerRight={headerRight}
      className={cn(active && "border-etex-orange ring-1 ring-etex-orange/30")}
    >
      <div className="px-5 py-6">{children}</div>
    </ExpandableWidget>
  );
}

/* ── Tiny dot used in legends ────────────────────────────────────── */

function Dot({ color, size = 1.5, ring = false }: { color: string; size?: number; ring?: boolean }) {
  const px = size * 4; // tailwind w-1.5 = 6px, w-2 = 8px, w-2.5 = 10px
  return (
    <span
      className="inline-block rounded-full shrink-0 transition-shadow duration-150"
      style={{
        width: px,
        height: px,
        backgroundColor: color,
        boxShadow: ring ? `0 0 0 3px ${color}33` : undefined,
      }}
    />
  );
}

/* ── Legend row — synced with donut hover ─────────────────────────── */

function LegendRow({
  segKey,
  color,
  value,
  label,
  align = "left",
  hovered,
  onHover,
}: {
  segKey: string;
  color: string;
  value: React.ReactNode;
  label: string;
  /** "left" → dot + value + label; "split" → dot + label / value */
  align?: "left" | "split";
  hovered: string | null;
  onHover: (k: string | null) => void;
}) {
  const isHover = hovered === segKey;
  const isDimmed = hovered !== null && !isHover;
  const content =
    align === "split" ? (
      <>
        <span className="inline-flex items-center gap-2 min-w-0">
          <Dot color={color} size={2} ring={isHover} />
          <span className="text-etex-gray-700 dark:text-gray-300 truncate">{label}</span>
        </span>
        <strong className="tabular-nums text-(--foreground) shrink-0">{value}</strong>
      </>
    ) : (
      <>
        <Dot color={color} size={2} ring={isHover} />
        <strong className="text-base tabular-nums text-(--foreground)">{value}</strong>
        <span className="text-etex-gray-700 dark:text-gray-300 truncate">{label}</span>
      </>
    );
  return (
    <span
      className={cn(
        "rounded-sm px-1.5 py-0.5 -mx-1.5 transition-all duration-150",
        align === "split" ? "flex items-baseline justify-between gap-2" : "inline-flex items-center gap-2",
        isHover && "bg-etex-gray-100 dark:bg-[#282C34]",
        isDimmed && "opacity-45",
      )}
      onMouseEnter={() => onHover(segKey)}
      onMouseLeave={() => onHover(null)}
    >
      {content}
    </span>
  );
}

/* ── Palette ────────────────────────────────────────────────────── */

const COLOR = {
  execution: "#10B981",
  planning:  "#8B5CF6",
  actuals:   "#10B981",
  committed: "#F59E0B",
  remaining: "#9CA3AF",
  onTime:    "#10B981",
  delayed:   "#EF4444",
  undefined: "#D1D5DB", // gray-300 — unrated / no schedule
  success:   "#10B981",
  danger:    "#EF4444",
};

function sentimentClass(s: Sentiment): string {
  if (s === "positive") return "text-success";
  if (s === "negative") return "text-danger";
  return "text-(--foreground)";
}

function median(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0
    ? (sorted[mid - 1] + sorted[mid]) / 2
    : sorted[mid];
}

/* ── Strip ───────────────────────────────────────────────────────── */

export function HeroKPIStrip({ portfolio, projects, loading, filters, onFiltersChange }: HeroKPIStripProps) {
  if (loading) return <StripSkeleton />;
  if (!portfolio) {
    return (
      <div className="card-compact px-5 py-8 text-center text-xs text-etex-gray-600 dark:text-gray-400">
        No projects match the current filters
      </div>
    );
  }

  /* ── Derived metrics ────────────────────────────── */
  const planningCount = portfolio.totalProjects - portfolio.inExecutionCount;
  const executionPct = portfolio.totalProjects > 0
    ? Math.round((portfolio.inExecutionCount / portfolio.totalProjects) * 100)
    : 0;

  const remainingBac = Math.max(
    0,
    portfolio.totalBAC - portfolio.totalActuals - portfolio.totalCommitted,
  );
  const eacVsBacPct = portfolio.totalBAC > 0
    ? ((portfolio.totalEAC - portfolio.totalBAC) / portfolio.totalBAC) * 100
    : 0;
  const utilizationPct = portfolio.totalEAC > 0
    ? Math.round((portfolio.totalActuals / portfolio.totalEAC) * 100)
    : 0;

  const variancePct = portfolio.totalBAC > 0
    ? (portfolio.totalVariance / portfolio.totalBAC) * 100
    : 0;
  const varianceSentiment: Sentiment =
    portfolio.totalVariance > 0 ? "positive" : portfolio.totalVariance < 0 ? "negative" : "neutral";

  const scheduleTotal = portfolio.onTimeCount + portfolio.delayedCount;
  const onTimePct = scheduleTotal > 0
    ? Math.round((portfolio.onTimeCount / scheduleTotal) * 100)
    : 0;
  const onTimeSentiment: Sentiment =
    onTimePct >= 80 ? "positive" : onTimePct >= 60 ? "neutral" : "negative";

  const delayValues = projects
    .filter((p) => p.scheduleBuffer != null && p.scheduleBuffer < 0)
    .map((p) => Math.abs(p.scheduleBuffer!));
  const medianDelayDays = delayValues.length > 0 ? Math.round(median(delayValues)) : 0;

  const unratedCount = Math.max(0, portfolio.totalProjects - scheduleTotal);

  // Centered-zero variance bar — center = BAC (0% variance).
  // Right of center = positive variance (under budget), left = over.
  // Scale: ±max(|variance|, 5%) so small variances stay visible.
  const VARIANCE_SCALE = Math.max(Math.abs(variancePct), 5);
  const variancePosPct = Math.min(50, (Math.abs(variancePct) / VARIANCE_SCALE) * 50);

  /* ── Filter wiring ───────────────────────────────── */
  const executionPatch: Partial<DashboardFilters> = { phase: EXECUTION_PHASES };
  const canFilter = !!filters && !!onFiltersChange;
  const executionActive = patchIsActive(filters, executionPatch);
  const onExecutionClick = canFilter
    ? () => onFiltersChange!(togglePatch(filters!, executionPatch))
    : undefined;

  /* ── Format helpers ──────────────────────────────── */
  const fmt = (v: number, opts?: { signed?: boolean }) =>
    formatCurrency(v, { compact: true, signed: opts?.signed });
  const fmtMEUR = (v: number, opts?: { signed?: boolean }) => {
    const sign = opts?.signed ? (v >= 0 ? "+" : "−") : v < 0 ? "−" : "";
    return `${sign}${Math.round(Math.abs(v) / 1_000)}M€`;
  };
  const signedPct = (v: number, decimals = 1) =>
    `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(decimals)}%`;

  /* ── Render ──────────────────────────────────────── */
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">

        {/* ── 1. Portfolio ───────────────────────────────────────── */}
        <KpiCard
          label="Portfolio"
          active={executionActive}
          onClick={onExecutionClick}
        >
          <PortfolioCardBody
            totalProjects={portfolio.totalProjects}
            inExecutionCount={portfolio.inExecutionCount}
            planningCount={planningCount}
            executionPct={executionPct}
          />
        </KpiCard>

        {/* ── 2. Forecast (BAC) ─────────────────────────────────── */}
        <KpiCard label="Total Investment (Capex + Opex)">
          <InvestmentCardBody
            bac={portfolio.totalBAC}
            eac={portfolio.totalEAC}
            actuals={portfolio.totalActuals}
            committed={portfolio.totalCommitted}
            remaining={remainingBac}
            utilizationPct={utilizationPct}
            eacVsBacPct={eacVsBacPct}
            fmtMEUR={fmtMEUR}
            signedPct={signedPct}
          />
        </KpiCard>

        {/* ── 3. VAC (no donut, signed number) ──────────────────── */}
        <KpiCard label="VAC (Variance at Completion)">
          <div className="flex flex-col h-full justify-center gap-3">
            <div className="flex items-baseline gap-2">
              <span className={cn(
                "text-4xl sm:text-5xl font-bold leading-none tracking-tight tabular-nums",
                sentimentClass(varianceSentiment),
              )}>
                {fmt(portfolio.totalVariance, { signed: true })}
              </span>
              <span className={cn(
                "text-sm font-semibold tabular-nums",
                sentimentClass(varianceSentiment),
              )}>
                {signedPct(variancePct)}
              </span>
            </div>

            {/* Centered-zero variance bar — 0 at center, +%  right (green), −% left (red) */}
            <div className="space-y-1">
              <div className="relative h-2 bg-etex-gray-100 dark:bg-[#23262C] rounded-sm">
                {portfolio.totalVariance >= 0 ? (
                  <div
                    className="absolute top-0 h-full bg-success transition-[width] duration-500 rounded-r-sm"
                    style={{ left: "50%", width: `${variancePosPct}%` }}
                    title={`+${variancePct.toFixed(1)}% vs BAC`}
                  />
                ) : (
                  <div
                    className="absolute top-0 h-full bg-danger transition-[width] duration-500 rounded-l-sm"
                    style={{ right: "50%", width: `${variancePosPct}%` }}
                    title={`${variancePct.toFixed(1)}% vs BAC`}
                  />
                )}
                {/* BAC center tick (zero variance) */}
                <div className="absolute -top-1 -bottom-1 left-1/2 w-px bg-(--foreground)/85 -translate-x-1/2" />
              </div>
              <div className="grid grid-cols-3 text-[10px] text-etex-gray-600 dark:text-gray-400">
                <span className="text-left">over</span>
                <span className="text-center font-semibold text-(--foreground) tabular-nums">BAC</span>
                <span className="text-right">under</span>
              </div>
            </div>

            <span className={cn(
              "inline-flex items-center gap-2 text-[12.5px]",
              portfolio.overBudgetCount > 0 ? "text-danger font-semibold" : "text-success font-semibold",
            )}>
              <Dot color={portfolio.overBudgetCount > 0 ? COLOR.danger : COLOR.success} />
              <span className="tabular-nums">{portfolio.overBudgetCount}</span>
              <span>over budget</span>
            </span>
          </div>
        </KpiCard>

        {/* ── 4. On-Time Delivery ───────────────────────────────── */}
        <KpiCard label="On-Time Delivery">
          <OnTimeCardBody
            onTimeCount={portfolio.onTimeCount}
            delayedCount={portfolio.delayedCount}
            unratedCount={unratedCount}
            onTimePct={onTimePct}
            onTimeSentiment={onTimeSentiment}
            medianDelayDays={medianDelayDays}
          />
        </KpiCard>
    </div>
  );
}

/* ── Donut card bodies — each owns hover state ───────────────────── */

function PortfolioCardBody({
  totalProjects,
  inExecutionCount,
  planningCount,
  executionPct,
}: {
  totalProjects: number;
  inExecutionCount: number;
  planningCount: number;
  executionPct: number;
}) {
  const [hovered, setHovered] = useState<string | null>(null);
  return (
    <div className="flex items-center gap-5">
      <Donut
        size={116}
        thickness={13}
        hovered={hovered}
        onHoverChange={setHovered}
        segments={[
          { key: "execution", value: inExecutionCount, color: COLOR.execution, label: "Execution" },
          { key: "planning",  value: planningCount,    color: COLOR.planning,  label: "Planning"  },
        ]}
      >
        <span className="text-2xl font-bold text-(--foreground) tabular-nums leading-none">
          {totalProjects}
        </span>
        <span className="mt-1 text-[9px] uppercase tracking-wider text-etex-gray-600 dark:text-gray-400">
          total
        </span>
      </Donut>

      <div className="flex flex-col gap-1.5 min-w-0 flex-1 text-[12.5px]">
        <LegendRow
          segKey="execution"
          color={COLOR.execution}
          value={inExecutionCount}
          label="execution"
          hovered={hovered}
          onHover={setHovered}
        />
        <LegendRow
          segKey="planning"
          color={COLOR.planning}
          value={planningCount}
          label="planning"
          hovered={hovered}
          onHover={setHovered}
        />
        <span className="text-[11px] text-etex-gray-600 dark:text-gray-400 mt-0.5 px-1.5">
          {executionPct}% in execution
        </span>
      </div>
    </div>
  );
}

function InvestmentCardBody({
  bac,
  eac,
  actuals,
  committed,
  remaining,
  utilizationPct,
  eacVsBacPct,
  fmtMEUR,
  signedPct,
}: {
  bac: number;
  eac: number;
  actuals: number;
  committed: number;
  remaining: number;
  utilizationPct: number;
  eacVsBacPct: number;
  fmtMEUR: (v: number, opts?: { signed?: boolean }) => string;
  signedPct: (v: number, decimals?: number) => string;
}) {
  const [hovered, setHovered] = useState<string | null>(null);
  return (
    <div className="flex items-center gap-5">
      <Donut
        size={116}
        thickness={13}
        hovered={hovered}
        onHoverChange={setHovered}
        segments={[
          { key: "actuals",   value: actuals,   color: COLOR.actuals,   label: "Actuals"   },
          { key: "committed", value: committed, color: COLOR.committed, label: "Committed" },
          { key: "remaining", value: remaining, color: COLOR.remaining, label: "Remaining" },
        ]}
      >
        <span className="text-lg sm:text-xl font-bold tabular-nums leading-none tracking-tight text-(--foreground)">
          {fmtMEUR(bac)}
        </span>
        <span className="mt-1 text-[9px] uppercase tracking-wider text-etex-gray-600 dark:text-gray-400">
          BAC
        </span>
      </Donut>

      <div className="flex flex-col gap-1 min-w-0 flex-1 text-[12.5px]">
        <LegendRow
          segKey="actuals"
          color={COLOR.actuals}
          value={fmtMEUR(actuals)}
          label="Actuals"
          align="split"
          hovered={hovered}
          onHover={setHovered}
        />
        <LegendRow
          segKey="committed"
          color={COLOR.committed}
          value={fmtMEUR(committed)}
          label="Committed"
          align="split"
          hovered={hovered}
          onHover={setHovered}
        />
        <LegendRow
          segKey="remaining"
          color={COLOR.remaining}
          value={fmtMEUR(remaining)}
          label="Remaining"
          align="split"
          hovered={hovered}
          onHover={setHovered}
        />
        <span className="flex items-baseline justify-between gap-2 mt-1 pt-1.5 border-t border-(--border-subtle) px-1.5">
          <span className="text-[11px] text-etex-gray-600 dark:text-gray-400">
            EAC {fmtMEUR(eac)} · {utilizationPct}% spent
          </span>
          <span className={cn(
            "text-[11px] font-semibold",
            eacVsBacPct > 0.5 ? "text-danger" : eacVsBacPct < -0.5 ? "text-success" : "text-etex-gray-600 dark:text-gray-400",
          )}>
            {signedPct(eacVsBacPct)} vs BAC
          </span>
        </span>
      </div>
    </div>
  );
}

function OnTimeCardBody({
  onTimeCount,
  delayedCount,
  unratedCount,
  onTimePct,
  onTimeSentiment,
  medianDelayDays,
}: {
  onTimeCount: number;
  delayedCount: number;
  unratedCount: number;
  onTimePct: number;
  onTimeSentiment: Sentiment;
  medianDelayDays: number;
}) {
  const [hovered, setHovered] = useState<string | null>(null);
  return (
    <div className="flex items-center gap-5">
      <Donut
        size={116}
        thickness={13}
        hovered={hovered}
        onHoverChange={setHovered}
        segments={[
          { key: "onTime",    value: onTimeCount,  color: COLOR.onTime,    label: "On time"   },
          { key: "delayed",   value: delayedCount, color: COLOR.delayed,   label: "Delayed"   },
          { key: "undefined", value: unratedCount, color: COLOR.undefined, label: "Undefined" },
        ]}
      >
        <span className={cn(
          "text-2xl font-bold tabular-nums leading-none",
          sentimentClass(onTimeSentiment),
        )}>
          {onTimePct}%
        </span>
        <span className="mt-1 text-[9px] uppercase tracking-wider text-etex-gray-600 dark:text-gray-400">
          on time
        </span>
      </Donut>

      <div className="flex flex-col gap-1.5 min-w-0 flex-1 text-[12.5px]">
        <LegendRow
          segKey="onTime"
          color={COLOR.onTime}
          value={onTimeCount}
          label="on time"
          hovered={hovered}
          onHover={setHovered}
        />
        <LegendRow
          segKey="delayed"
          color={COLOR.delayed}
          value={delayedCount}
          label="delayed"
          hovered={hovered}
          onHover={setHovered}
        />
        <LegendRow
          segKey="undefined"
          color={COLOR.undefined}
          value={unratedCount}
          label="undefined"
          hovered={hovered}
          onHover={setHovered}
        />
        {medianDelayDays > 0 ? (
          <span className="text-[11px] text-danger font-semibold mt-0.5 px-1.5">
            ~{medianDelayDays}d median delay
          </span>
        ) : (
          <span className="text-[11px] text-etex-gray-600 dark:text-gray-400 mt-0.5 px-1.5">
            no delays
          </span>
        )}
      </div>
    </div>
  );
}
