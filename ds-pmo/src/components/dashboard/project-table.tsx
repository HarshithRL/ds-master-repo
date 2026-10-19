"use client";

import { useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import { cn, contrastText } from "@/lib/utils";
import { formatCurrency, formatAmount, formatDateShort, formatVariance } from "@/lib/utils";
import { GATE_KEYS, getPhaseByKey, isExecutionPhase } from "@/lib/constants";
import { computeUntilNextGate } from "@/lib/progress";
import { computeRiskMetrics, type RiskMetrics } from "@/lib/risk-calculations";
import {
  computeStakeholders,
  computeFinancials,
  computeSchedulePerf,
  computeRiskAggregates,
  computeIssueAggregates,
  computeScopeChangeAggregates,
  computeRagTrends,
  RAG_DIMENSIONS,
  RAG_LABEL_FIELD,
  type Financials,
  type SchedulePerf,
  type RiskAggregates,
  type IssueAggregates,
  type ScopeChangeAggregates,
  type Stakeholders,
  type TrendDirection,
  type RagDimensionKey,
} from "@/lib/project-table-metrics";
import { InfoHint } from "@/components/ui/info-hint";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import {
  ArrowUp,
  ArrowDown,
  Minus,
  ChevronUp,
  ChevronDown,
  FolderOpen,
  Check,
  Clock,
  Target,
  Euro,
  AlertTriangle,
  LayoutGrid,
  Users,
  TrendingUp,
  TrendingDown,
  Equal,
  Lock,
  type LucideIcon,
} from "lucide-react";
import { ProjectTableLoading } from "@/components/ui/page-state";
import { EmptyState } from "@/components/ui/empty-state";
import { ProjectStatusBadge } from "@/components/project/project-status-badge";
import { CountryFlag } from "@/components/ui/country-flag";
import type { ProjectListItem } from "@/types";
import type { RAGStatus } from "@/lib/db/models";
import type { ProjectsSummary } from "@/hooks/use-projects";

/* ─── Types ─────────────────────────────────────────────────────────── */

interface ProjectTableProps {
  projects: ProjectListItem[];
  loading?: boolean;
  /** When provided (paginated mode), overrides client-side aggregation so the
   *  summary rows reflect the full filtered portfolio rather than the current page. */
  summary?: ProjectsSummary | null;
  /**
   * Current server-side sort (mirrors the `sortBy`/`sortDir` URL filters).
   * Only meaningful together with `onSortChange` — see SERVER_SORTABLE below.
   */
  sortBy?: string;
  sortDir?: "asc" | "desc";
  /**
   * Wire this up (paginated mode) so clicking a SERVER_SORTABLE column header
   * re-sorts the whole filtered portfolio via a refetch, not just the rows on
   * the current page. Fields outside SERVER_SORTABLE (aggregates computed
   * from child rows — risks, scope changes, budget/snapshot math — have no
   * backing DB column to sort by yet) still fall back to re-sorting the
   * current page only, same as before.
   */
  onSortChange?: (sortBy: string, sortDir: "asc" | "desc") => void;
}

type SortField =
  | "updatedAt"
  | "name"
  | "phase"
  | "bac"
  | "eac"
  | "vac"
  | "actPlanned"
  | "floatIncl"
  | "pctGate"
  | "openIssues"
  | "scopeQty";

interface SortState {
  field: SortField;
  direction: "asc" | "desc";
}

/** Fields `/api/projects?sortBy=` can order the full result set by — see SORTABLE_FIELDS in the route. */
const SERVER_SORTABLE = new Set<SortField>(["name", "updatedAt", "phase", "bac", "floatIncl"]);

/* ─── Gate helpers ──────────────────────────────────────────────────── */

/** Hex color shown for each gate. */
const GATE_COLOR: Record<(typeof GATE_KEYS)[number], string> = {
  RED: "#EF4444",
  AMBER: "#F59E0B",
  GREEN: "#10B981",
  GREY: "#9CA3AF",
  GOLD: "#D4A017",
  BLUE: "#3B82F6",
  PURPLE: "#8B5CF6",
  WHITE: "#E5E7EB",
};

/* ─── Computed row data ─────────────────────────────────────────────── */

interface ComputedRow {
  project: ProjectListItem;
  stakeholders: Stakeholders;
  financials: Financials;
  schedulePerf: SchedulePerf;
  riskAggregates: RiskAggregates;
  riskMetrics: RiskMetrics; // legacy — kept for summary row backwards-compat
  issueAggregates: IssueAggregates;
  scopeAggregates: ScopeChangeAggregates;
  ragTrends: Record<RagDimensionKey, TrendDirection>;
  passedGates: Set<string>;
  pctGate: number;
  isExecution: boolean;
}

function computeRow(p: ProjectListItem): ComputedRow {
  const gates = p.gates || [];
  const pctGate = computeUntilNextGate(gates);
  const passedGates = new Set(
    gates.filter((g) => g.status === "PASSED").map((g) => g.gate),
  );

  const stakeholders = computeStakeholders(p.assignments ?? []);
  const financials = computeFinancials(p.budget, p.snapshots?.[0]?.varianceAtCompletion ?? null);
  const schedulePerf = computeSchedulePerf(p, pctGate);
  const riskAggregates = computeRiskAggregates(p.risks ?? []);
  const issueAggregates = computeIssueAggregates(p.risks ?? []);
  const scopeAggregates = computeScopeChangeAggregates(p.scopeChanges ?? []);

  const prevSnapshot = p.snapshots?.[0];
  const ragTrends = computeRagTrends(p, prevSnapshot);

  const riskMetrics = computeRiskMetrics(
    p.riskSummary,
    financials.eac,
    p.actualStartDate ?? p.createdAt,
    p.plannedCompletionDate,
  );

  const isExecution = isExecutionPhase(p.currentPhase, p.lifecycleType);

  return {
    project: p,
    stakeholders,
    financials,
    schedulePerf,
    riskAggregates,
    riskMetrics,
    issueAggregates,
    scopeAggregates,
    ragTrends,
    passedGates,
    pctGate,
    isExecution,
  };
}

/* ─── Summary aggregation across rows ───────────────────────────────── */

interface SummaryData {
  label: string;
  count: number;
  financials: Financials;
  schedulePerf: SchedulePerf;
  riskAggregates: RiskAggregates;
  issueAggregates: IssueAggregates;
  scopeAggregates: ScopeChangeAggregates;
  pctGate: number;
}

function computeSummary(rows: ComputedRow[], label: string): SummaryData {
  const count = rows.length;
  if (count === 0) {
    return {
      label,
      count,
      financials: { bac: 0, eac: 0, cont: 0, vac: 0, deltaVac: null, act: 0, comm: 0, actPlanned: 0 },
      schedulePerf: { floatExcl: null, floatIncl: null, svac: null, svacDelta: null, pctToNextGate: 0, resourceConsumptionPct: null },
      riskAggregates: { weightedCostImpact: 0, totalRiskCost: 0, weightedTimeImpact: 0, totalRiskDelay: 0 },
      issueAggregates: { open: 0 },
      scopeAggregates: { qtyImpactingCost: 0, underEvaluationEur: 0, approvedEur: 0 },
      pctGate: 0,
    };
  }

  const sum = (pick: (r: ComputedRow) => number) =>
    rows.reduce((s, r) => s + pick(r), 0);
  const avg = (pick: (r: ComputedRow) => number) => sum(pick) / count;

  const bac = sum((r) => r.financials.bac);
  const eac = sum((r) => r.financials.eac);
  const cont = sum((r) => r.financials.cont);
  const act = sum((r) => r.financials.act);
  const comm = sum((r) => r.financials.comm);
  const vac = bac - eac;
  const deltaVacRows = rows.filter((r) => r.financials.deltaVac != null);
  const deltaVac = deltaVacRows.length
    ? deltaVacRows.reduce((s, r) => s + (r.financials.deltaVac ?? 0), 0)
    : null;
  const actPlanned = bac > 0 ? (act + comm) / bac : 0;

  const floatInclRows = rows.filter((r) => r.schedulePerf.floatIncl != null);
  const floatExclRows = rows.filter((r) => r.schedulePerf.floatExcl != null);
  const svacRows = rows.filter((r) => r.schedulePerf.svac != null);
  const svacDeltaRows = rows.filter((r) => r.schedulePerf.svacDelta != null);
  const resRows = rows.filter((r) => r.schedulePerf.resourceConsumptionPct != null);

  return {
    label,
    count,
    financials: { bac, eac, cont, vac, deltaVac, act, comm, actPlanned },
    schedulePerf: {
      floatExcl: floatExclRows.length
        ? Math.round(
            floatExclRows.reduce((s, r) => s + (r.schedulePerf.floatExcl ?? 0), 0) /
              floatExclRows.length,
          )
        : null,
      floatIncl: floatInclRows.length
        ? Math.round(
            floatInclRows.reduce((s, r) => s + (r.schedulePerf.floatIncl ?? 0), 0) /
              floatInclRows.length,
          )
        : null,
      svac: svacRows.length
        ? svacRows.reduce((s, r) => s + (r.schedulePerf.svac ?? 0), 0) / svacRows.length
        : null,
      svacDelta: svacDeltaRows.length
        ? svacDeltaRows.reduce((s, r) => s + (r.schedulePerf.svacDelta ?? 0), 0) /
          svacDeltaRows.length
        : null,
      pctToNextGate: Math.round(avg((r) => r.pctGate)),
      resourceConsumptionPct: resRows.length
        ? resRows.reduce((s, r) => s + (r.schedulePerf.resourceConsumptionPct ?? 0), 0) /
          resRows.length
        : null,
    },
    riskAggregates: {
      weightedCostImpact: sum((r) => r.riskAggregates.weightedCostImpact),
      totalRiskCost: sum((r) => r.riskAggregates.totalRiskCost),
      weightedTimeImpact: sum((r) => r.riskAggregates.weightedTimeImpact),
      totalRiskDelay: sum((r) => r.riskAggregates.totalRiskDelay),
    },
    issueAggregates: {
      open: sum((r) => r.issueAggregates.open),
    },
    scopeAggregates: {
      qtyImpactingCost: sum((r) => r.scopeAggregates.qtyImpactingCost),
      underEvaluationEur: sum((r) => r.scopeAggregates.underEvaluationEur),
      approvedEur: sum((r) => r.scopeAggregates.approvedEur),
    },
    pctGate: Math.round(avg((r) => r.pctGate)),
  };
}

/* ─── RAG dot + trend arrow ─────────────────────────────────────────── */

/** Icon shown inside each status chip. */
const STATUS_ICON: Record<RagDimensionKey, LucideIcon> = {
  ragProgress: Target,
  ragCost: Euro,
  ragSchedule: Clock,
  ragRisk: AlertTriangle,
  ragScope: LayoutGrid,
  ragResources: Users,
};

/** Foreground + background per RAG status — readable text inside the chip. */
const STATUS_CHIP: Record<string, string> = {
  RED: "bg-gradient-to-br from-red-400 to-red-600 text-white",
  AMBER: "bg-gradient-to-br from-amber-300 to-amber-500 text-amber-950",
  GREEN: "bg-gradient-to-br from-emerald-400 to-emerald-600 text-white",
};

/** Compact textual trend description vs the most recent snapshot. */
function trendDescription(direction: TrendDirection): {
  text: string;
  cls: string;
  Icon: LucideIcon | null;
} {
  switch (direction) {
    case "up":
      return {
        text: "Improved since last snapshot",
        cls: "text-emerald-600 dark:text-emerald-400",
        Icon: ArrowUp,
      };
    case "down":
      return {
        text: "Worsened since last snapshot",
        cls: "text-red-600 dark:text-red-400",
        Icon: ArrowDown,
      };
    case "same":
      return {
        text: "Unchanged since last snapshot",
        cls: "text-etex-gray-500 dark:text-etex-gray-400",
        Icon: Minus,
      };
    default:
      return {
        text: "No prior snapshot to compare",
        cls: "text-etex-gray-400 dark:text-etex-gray-500 italic",
        Icon: null,
      };
  }
}

/** Tiny trend marker shown beneath each status chip. */
/**
 * Tiny "ticker pill" trend indicator, shown beneath each status segment.
 * Inspired by stock-ticker UI: rounded chip with a sloped icon + tinted bg.
 * Direction "unknown" (no prior snapshot) is rendered as "same" per spec.
 */
function MiniTrend({ direction }: { direction: TrendDirection }) {
  const effective = direction === "unknown" ? "same" : direction;
  const styles = {
    up: {
      cls: "bg-emerald-50 text-emerald-600 ring-emerald-200 dark:bg-emerald-500/15 dark:text-emerald-400 dark:ring-emerald-500/25",
      Icon: TrendingUp,
    },
    down: {
      cls: "bg-red-50 text-red-600 ring-red-200 dark:bg-red-500/15 dark:text-red-400 dark:ring-red-500/25",
      Icon: TrendingDown,
    },
    same: {
      cls: "bg-gray-100 text-gray-400 ring-gray-200 dark:bg-white/5 dark:text-gray-500 dark:ring-white/10",
      Icon: Equal,
    },
  } as const;
  const { cls, Icon } = styles[effective];
  return (
    <span
      className={cn(
        "inline-flex items-center justify-center w-3.5 h-3 rounded-[2px] ring-1 ring-inset",
        "transition-transform duration-150 will-change-transform",
        "hover:scale-110",
        cls,
      )}
      aria-label={`Trend: ${effective}`}
    >
      <Icon size={8} strokeWidth={3} />
    </span>
  );
}

/**
 * Six iconic chips (Target, €, ⏱, ⚠, ▦, 👥) with a trend marker beneath each.
 * RED chips pulse. Per-chip hover opens a Portal'd popover with full label,
 * free-text comment, and an explicit trend description vs the last snapshot.
 */
function RagStatusCell({
  project,
  ragTrends,
}: {
  project: ProjectListItem;
  ragTrends: Record<RagDimensionKey, TrendDirection>;
}) {
  return (
    <TooltipPrimitive.Provider delayDuration={50} skipDelayDuration={400} disableHoverableContent>
      <div className="inline-flex flex-col items-center py-0.5">
        {/* Fused horizontal status bar — segments share borders, no gap */}
        <div className="inline-flex items-stretch rounded-sm overflow-hidden ring-1 ring-black/10 dark:ring-white/15 shadow-sm">
          {RAG_DIMENSIONS.map((d, i) => {
            const status = project[d.key] as RAGStatus | null;
            const text = (project[RAG_LABEL_FIELD[d.key]] as string | null) ?? null;
            return (
              <RagStatusSegment
                key={d.key}
                Icon={STATUS_ICON[d.key]}
                label={d.label}
                status={status}
                text={text}
                trend={ragTrends[d.key]}
                isFirst={i === 0}
              />
            );
          })}
        </div>
        {/* Trend ticker — one pill beneath each segment, always shown. */}
        <div className="inline-flex items-center mt-0.5">
          {RAG_DIMENSIONS.map((d) => (
            <span
              key={d.key}
              className="inline-flex justify-center items-center w-6 h-3.5"
            >
              <MiniTrend direction={ragTrends[d.key]} />
            </span>
          ))}
        </div>
      </div>
    </TooltipPrimitive.Provider>
  );
}

function RagStatusSegment({
  Icon,
  label,
  status,
  text,
  trend,
  isFirst,
}: {
  Icon: LucideIcon;
  label: string;
  status: RAGStatus | null;
  text: string | null;
  trend: TrendDirection;
  isFirst: boolean;
}) {
  const trendInfo = trendDescription(trend);
  return (
    <TooltipPrimitive.Root>
      <TooltipPrimitive.Trigger asChild>
        <span
          aria-label={`${label}: ${status ?? "not set"}`}
          className={cn(
            "relative inline-flex items-center justify-center w-6 h-5 cursor-default",
            "transition-all duration-150 ease-out",
            "hover:brightness-110 hover:saturate-150 hover:z-10",
            !isFirst && "border-l border-white/40 dark:border-black/30",
            status
              ? STATUS_CHIP[status]
              : "bg-etex-gray-100 dark:bg-etex-gray-800 text-etex-gray-400 dark:text-etex-gray-500",
            status === "RED" && "animate-pulse",
          )}
        >
          <Icon
            size={13}
            strokeWidth={2.5}
            className={cn("drop-shadow-sm", !status && "opacity-50")}
          />
        </span>
      </TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content
          side="bottom"
          sideOffset={6}
          className={cn(
            "z-100 max-w-64 rounded-md",
            "bg-white dark:bg-[#21252B]",
            "shadow-lg shadow-black/10 ring-1 ring-gray-200 dark:ring-[#333842]",
            "select-none",
            "animate-in fade-in-0 zoom-in-95 duration-150",
            "data-[state=closed]:hidden",
          )}
        >
          <div className="px-3 py-2">
            <div className="flex items-center gap-2 mb-1">
              <span
                className={cn(
                  "inline-flex items-center justify-center w-5 h-5 rounded-md",
                  status
                    ? STATUS_CHIP[status]
                    : "bg-etex-gray-200 text-etex-gray-500 dark:bg-etex-gray-700",
                )}
              >
                <Icon size={11} strokeWidth={2.5} />
              </span>
              <span className="text-[12px] font-semibold text-gray-900 dark:text-gray-100">
                {label}
              </span>
              {status && (
                <span
                  className={cn(
                    "ml-auto text-[9px] font-semibold uppercase tracking-wide px-1.5 py-px rounded-sm",
                    status === "RED" && "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300",
                    status === "AMBER" && "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300",
                    status === "GREEN" && "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300",
                  )}
                >
                  {status}
                </span>
              )}
            </div>
            <p
              className={cn(
                "text-[11px] leading-snug pl-7 mb-1.5",
                text ? "text-gray-600 dark:text-gray-300" : "text-gray-400 dark:text-gray-500 italic",
              )}
            >
              {text ?? "No status note"}
            </p>
            <div
              className={cn(
                "flex items-center gap-1 pl-7 text-[10.5px]",
                trendInfo.cls,
              )}
            >
              {trendInfo.Icon ? (
                <trendInfo.Icon size={10} strokeWidth={3} />
              ) : (
                <span className="inline-block w-2.5 h-2.5" />
              )}
              <span>{trendInfo.text}</span>
            </div>
          </div>
          <TooltipPrimitive.Arrow className="fill-white dark:fill-[#21252B]" width={10} height={5} />
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  );
}

/* ─── Gate progression strip ────────────────────────────────────────── */

const GATE_STATUS_LABEL: Record<string, string> = {
  PLANNED: "Planned",
  IN_REVIEW: "In review",
  PASSED: "Passed",
  DEFERRED: "Deferred",
};

function titleCase(s: string) {
  return s.charAt(0) + s.slice(1).toLowerCase();
}

function GateProgression({
  gates,
}: {
  gates: { gate: string; status: string; completedDate?: Date | string | null; plannedDate?: Date | string | null }[];
}) {
  const safeGates = gates ?? [];
  const gateMap = new Map(safeGates.map((g) => [g.gate, g]));
  return (
    <TooltipPrimitive.Provider delayDuration={50} skipDelayDuration={400} disableHoverableContent>
      <div className="flex items-center justify-center gap-0.5">
        {GATE_KEYS.map((gate) => {
          const record = gateMap.get(gate);
          const passed = record?.status === "PASSED";
          return (
            <GateChip
              key={gate}
              gate={gate}
              passed={passed}
              status={record?.status ?? "PLANNED"}
              completedDate={record?.completedDate ?? null}
              plannedDate={record?.plannedDate ?? null}
            />
          );
        })}
      </div>
    </TooltipPrimitive.Provider>
  );
}

function GateChip({
  gate,
  passed,
  status,
  completedDate,
  plannedDate,
}: {
  gate: string;
  passed: boolean;
  status: string;
  completedDate: Date | string | null;
  plannedDate: Date | string | null;
}) {
  const color = GATE_COLOR[gate as keyof typeof GATE_COLOR];
  const fg = contrastText(color);
  const statusLabel = GATE_STATUS_LABEL[status] ?? status;
  const dateInfo: { label: string; value: string } | null = completedDate
    ? { label: "Completed", value: formatDateShort(completedDate) }
    : plannedDate
      ? { label: "Planned", value: formatDateShort(plannedDate) }
      : null;
  return (
    <TooltipPrimitive.Root>
      <TooltipPrimitive.Trigger asChild>
        <span
          className={cn(
            "relative inline-flex items-center justify-center w-3.5 h-3.5 rounded-sm shrink-0 cursor-default",
            "transition-all duration-150 ease-out",
            "hover:scale-150 hover:-translate-y-px hover:z-10 hover:shadow-md hover:ring-1 hover:ring-black/15 dark:hover:ring-white/25",
            passed ? "shadow-sm" : "opacity-30 saturate-50 hover:opacity-100 hover:saturate-100",
          )}
          style={{ backgroundColor: color, color: fg }}
          aria-label={`${gate} gate ${statusLabel}`}
        >
          {passed ? (
            <Check size={9} strokeWidth={3.5} />
          ) : (
            <Clock size={8} strokeWidth={2.5} />
          )}
        </span>
      </TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content
          side="bottom"
          sideOffset={6}
          className={cn(
            "z-100 max-w-60 rounded-md",
            "bg-white dark:bg-[#21252B]",
            "shadow-lg shadow-black/10 ring-1 ring-gray-200 dark:ring-[#333842]",
            "select-none",
            "animate-in fade-in-0 zoom-in-95 duration-150",
            "data-[state=closed]:hidden",
          )}
        >
          <div className="px-3 py-2">
            <div className="flex items-center gap-2 mb-1">
              <span
                className="inline-block w-3 h-3 rounded-sm ring-1 ring-black/10 dark:ring-white/10 shrink-0"
                style={{ backgroundColor: color }}
              />
              <span className="text-[12px] font-semibold text-gray-900 dark:text-gray-100">
                {titleCase(gate)} Gate
              </span>
            </div>
            <div className="flex items-center gap-1.5 pl-5 mb-0.5">
              <span
                className={cn(
                  "inline-flex items-center justify-center w-3.5 h-3.5 rounded-full",
                  passed
                    ? "bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-400"
                    : "bg-gray-100 dark:bg-gray-700/50 text-gray-500 dark:text-gray-400",
                )}
              >
                {passed ? <Check size={8} strokeWidth={3.5} /> : <Clock size={8} strokeWidth={2.5} />}
              </span>
              <span className="text-[11px] font-medium text-gray-700 dark:text-gray-300">
                {statusLabel}
              </span>
            </div>
            <p className="text-[10.5px] text-gray-500 dark:text-gray-400 pl-5">
              {dateInfo ? (
                <>
                  <span className="text-gray-400 dark:text-gray-500">{dateInfo.label}:</span>{" "}
                  <span className="font-mono tabular-nums">{dateInfo.value}</span>
                </>
              ) : (
                <span className="italic text-gray-400">No date set</span>
              )}
            </p>
          </div>
          <TooltipPrimitive.Arrow className="fill-white dark:fill-[#21252B]" width={10} height={5} />
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  );
}

/* ─── Flags cell ────────────────────────────────────────────────────── */

const FLAG_LABEL: Record<string, string> = {
  MSR: "MSR",
  EXCOM_PRESENTING: "ExCom",
};

function FlagsCell({ flags }: { flags: string[] }) {
  if (!flags.length) {
    return <span className="text-etex-gray-300 dark:text-etex-gray-600">—</span>;
  }
  return (
    <div className="flex items-center justify-center flex-wrap gap-1">
      {flags.map((f) => (
        <span
          key={f}
          className="inline-flex items-center h-5 px-1.5 rounded-sm text-[10px] font-semibold bg-etex-orange/15 text-etex-orange border border-etex-orange/30 dark:bg-etex-orange/20 dark:text-orange-300 dark:border-etex-orange/40"
          title={FLAG_LABEL[f] ?? f}
        >
          {FLAG_LABEL[f] ?? f}
        </span>
      ))}
    </div>
  );
}

/* ─── Column help hint ──────────────────────────────────────────────── */

function ColHint({ label, text }: { label: string; text: string }) {
  return (
    <InfoHint
      label={label}
      text={text}
      className="text-white/40 hover:text-white/80"
      side="bottom"
    />
  );
}

/* ─── Sort header button ────────────────────────────────────────────── */

function SortBtn({
  field,
  sort,
  onSort,
  children,
  className,
}: {
  field: SortField;
  sort: SortState;
  onSort: (f: SortField) => void;
  children: React.ReactNode;
  className?: string;
}) {
  const active = sort.field === field;
  return (
    <button
      type="button"
      onClick={() => onSort(field)}
      className={cn("exec-sort-btn", className)}
    >
      {children}
      {active && (
        <span className="ml-0.5 opacity-90">
          {sort.direction === "asc" ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
        </span>
      )}
    </button>
  );
}

/* ─── Cell colour helpers ───────────────────────────────────────────── */

function getVarianceCellClass(v: number, decimals = 0): string {
  // VAC = BAC − EAC: positive (incl. rounded-to-zero) means under budget (good).
  // Round first so tiny negatives (-0.04) don't paint the cell red.
  const s = formatVariance(v, { decimals, suffix: "" }).sentiment;
  if (s === "positive") return "exec-cell-green";
  if (s === "negative") return "exec-cell-red";
  return "";
}

function getDaysCellClass(days: number | null): string {
  if (days == null) return "";
  if (days >= 0) return "exec-cell-green";
  if (days >= -30) return "exec-cell-yellow";
  return "exec-cell-red";
}

/* ─── Stakeholders cell ─────────────────────────────────────────────── */

function StakeholdersCell({ s }: { s: Stakeholders }) {
  const row = (label: string, value: string | null) => (
    <div className="flex items-baseline gap-1.5 text-[10px] leading-tight">
      <span className="text-etex-gray-400 dark:text-etex-gray-500 font-semibold uppercase tracking-wide w-12 shrink-0">
        {label}
      </span>
      <span
        className={cn(
          "font-mono tabular-nums truncate",
          value ? "text-etex-charcoal dark:text-etex-gray-200" : "text-etex-gray-400",
        )}
      >
        {value ?? "—"}
      </span>
    </div>
  );
  return (
    <div
      className="space-y-0.5"
      title={`PM: ${s.manager ?? "—"}\nSponsor: ${s.sponsor ?? "—"}\nOwner: ${s.owner ?? "—"}`}
    >
      {row("PM", s.manager)}
      {row("Sponsor", s.sponsor)}
      {row("Owner", s.owner)}
    </div>
  );
}

/* ─── Cell formatters ───────────────────────────────────────────────── */

const fmtK = (v: number | null | undefined, signed = false) =>
  v == null ? "—" : formatCurrency(v, { decimals: 0, suffix: "", signed });
const fmtDays = (v: number | null | undefined) =>
  v == null ? "—" : `${v}`;
const fmtPct = (v: number | null | undefined, signed = false) => {
  if (v == null) return "—";
  const pct = Math.round(v * 100);
  if (signed) return `${pct >= 0 ? "+" : ""}${pct}%`;
  return `${pct}%`;
};
const fmtCount = (v: number) => (v === 0 ? "0" : formatAmount(v, 0));

/* ─── Main component ────────────────────────────────────────────────── */

export function ProjectTable({ projects, loading, summary, sortBy, sortDir, onSortChange }: ProjectTableProps) {
  const router = useRouter();
  // Client-only fallback for fields with no server-side sort support yet
  // (aggregates — see SERVER_SORTABLE). Sorting one of THOSE always re-sorts
  // just the current page, since there's no column to ask the server to
  // order the full result set by.
  const [localSort, setLocalSort] = useState<SortState>({ field: "name", direction: "asc" });

  const serverDriven = !!onSortChange && !!sortBy && SERVER_SORTABLE.has(sortBy as SortField);
  // What the column-header arrows should reflect: the URL/filters-backed
  // server sort when active, otherwise the local page-only sort.
  const effectiveSort: SortState = serverDriven
    ? { field: sortBy as SortField, direction: sortDir ?? "asc" }
    : localSort;

  const handleSort = (field: SortField) => {
    if (onSortChange && SERVER_SORTABLE.has(field)) {
      const nextDir = effectiveSort.field === field && effectiveSort.direction === "asc" ? "desc" : "asc";
      onSortChange(field, nextDir);
      return;
    }
    setLocalSort((prev) =>
      prev.field === field ? { field, direction: prev.direction === "asc" ? "desc" : "asc" } : { field, direction: "asc" },
    );
  };

  const rows = useMemo(() => projects.map(computeRow), [projects]);

  const sortedRows = useMemo(() => {
    // Server already returned this page in the requested global order —
    // re-sorting it client-side here would only reorder within the page.
    if (serverDriven) return rows;

    const sorted = [...rows];
    sorted.sort((a, b) => {
      let aVal: string | number;
      let bVal: string | number;

      switch (localSort.field) {
        case "updatedAt":
          aVal = new Date(a.project.updatedAt).getTime();
          bVal = new Date(b.project.updatedAt).getTime();
          break;
        case "name":
          aVal = a.project.name;
          bVal = b.project.name;
          break;
        case "phase":
          // Sort by PLC stage order (Ideation → ... → Closed), not the raw
          // phase-key string — alphabetical would put e.g. "BENEFITS" before
          // "IDEATION". Each lifecycle (Engineering/IT) defines its own
          // phaseNumber sequence in lib/constants.ts.
          aVal = getPhaseByKey(a.project.currentPhase, a.project.lifecycleType)?.phaseNumber ?? 999;
          bVal = getPhaseByKey(b.project.currentPhase, b.project.lifecycleType)?.phaseNumber ?? 999;
          break;
        case "bac":
          aVal = a.financials.bac;
          bVal = b.financials.bac;
          break;
        case "eac":
          aVal = a.financials.eac;
          bVal = b.financials.eac;
          break;
        case "vac":
          aVal = a.financials.vac;
          bVal = b.financials.vac;
          break;
        case "actPlanned":
          aVal = a.financials.actPlanned;
          bVal = b.financials.actPlanned;
          break;
        case "floatIncl":
          aVal = a.schedulePerf.floatIncl ?? Number.NEGATIVE_INFINITY;
          bVal = b.schedulePerf.floatIncl ?? Number.NEGATIVE_INFINITY;
          break;
        case "pctGate":
          aVal = a.pctGate;
          bVal = b.pctGate;
          break;
        case "openIssues":
          aVal = a.issueAggregates.open;
          bVal = b.issueAggregates.open;
          break;
        case "scopeQty":
          aVal = a.scopeAggregates.qtyImpactingCost;
          bVal = b.scopeAggregates.qtyImpactingCost;
          break;
        default:
          aVal = a.project.name;
          bVal = b.project.name;
      }

      if (typeof aVal === "string" && typeof bVal === "string") {
        return localSort.direction === "asc" ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
      }
      return localSort.direction === "asc"
        ? (aVal as number) - (bVal as number)
        : (bVal as number) - (aVal as number);
    });
    return sorted;
  }, [rows, localSort, serverDriven]);

  // Server-provided summary (paginated mode) is portfolio-wide and authoritative;
  // client-side fallback aggregates the loaded rows (non-paginated callers).
  const execSummary = useMemo<SummaryData>(() => {
    if (summary) return { label: "Overall (Projects in Execution)", ...summary.execution };
    return computeSummary(rows.filter((r) => r.isExecution), "Overall (Projects in Execution)");
  }, [summary, rows]);
  const devSummary = useMemo<SummaryData>(() => {
    if (summary) return { label: "Overall (Projects in Development)", ...summary.development };
    return computeSummary(rows.filter((r) => !r.isExecution), "Overall (Projects in Development)");
  }, [summary, rows]);

  if (loading) return <ProjectTableLoading />;

  if (projects.length === 0 && !loading) {
    return (
      <div className="card-compact">
        <EmptyState
          icon={FolderOpen}
          title="No projects to show"
          description="Adjust your filters above, or create a new project to start tracking."
        />
      </div>
    );
  }

  return (
    <div className="exec-table-wrapper flex-1 min-h-0">
      <table className="exec-table table-sticky-first" style={{ minWidth: 2800 }}>
          <thead>
            {/* ── Row 1: group headers ────────────────────────────── */}
            <tr className="pmt-header-row">
              <th rowSpan={2} style={{ width: 100 }} className="pmt-th">
                <SortBtn field="updatedAt" sort={effectiveSort} onSort={handleSort} className="justify-center w-full">
                  Updated
                </SortBtn>
                <ColHint
                  label="Updated"
                  text="Date the project data was last updated, by whom."
                />
              </th>
              <th rowSpan={2} style={{ width: 220 }} className="pmt-th">
                <SortBtn field="name" sort={effectiveSort} onSort={handleSort} className="justify-center w-full">
                  Project
                </SortBtn>
              </th>
              <th rowSpan={2} style={{ width: 120 }} className="pmt-th">
                Status
                <ColHint
                  label="Project Status"
                  text="Lifecycle state — Active, On Hold, Closed / Complete, or Cancelled."
                />
              </th>
              <th rowSpan={2} style={{ width: 100 }} className="pmt-th">
                Flags
                <ColHint
                  label="Flags"
                  text="Project visibility flags — MSR (Monthly Status Report) and ExCom Presenting."
                />
              </th>
              <th rowSpan={2} style={{ width: 130 }} className="pmt-th">
                <SortBtn field="phase" sort={effectiveSort} onSort={handleSort} className="justify-center w-full">
                  Phase
                </SortBtn>
                <ColHint
                  label="Phase & Gate Progression"
                  text="ADEJE lifecycle phase (colored band) with the gate progression strip below — Red, Amber, Green, Grey, Gold, Blue, Purple, White. Hover any gate for status and date."
                />
              </th>
              <th rowSpan={2} style={{ width: 170 }} className="pmt-th">
                Stakeholders
                <ColHint
                  label="Stakeholders"
                  text="Sponsor / Owner / Manager. Format: first initial + family name (e.g. Y. SALTAN). Manager taken from the project assignment with the PROJECT_MANAGER role."
                />
              </th>
              <th rowSpan={2} style={{ width: 165 }} className="pmt-th">
                RAG
                <ColHint
                  label="RAG Indicators"
                  text="RAG status across six dimensions, each with a trend marker beneath. ◎ Overall · € Cost · ⏱ Schedule · ⚠ Risk · ▦ Scope · 👥 Resources. Hover any chip for its comment and trend vs the last snapshot."
                />
              </th>
              <th colSpan={8} className="pmt-th pmt-th-section-cost">
                Financial Performance <span className="opacity-70">(k€)</span>
                <ColHint
                  label="Financial Performance"
                  text="All values in k€ (thousands of euros). BAC (budget at completion), EAC = actuals + committed + ETC, CONT (budgeted contingencies), VAC = BAC − EAC (positive = under budget), ΔVAC (month-on-month, positive = improving), ACT (actuals), COMM (committed), A+C/BAC (consumption rate)."
                />
              </th>
              <th colSpan={6} className="pmt-th pmt-th-section-schedule">
                Schedule Performance
                <ColHint
                  label="Schedule Performance"
                  text="Manual schedule inputs. SVAC = total float incl. buffer ÷ days between green & white gate. ΔSVAC = current SVAC − previous month SVAC."
                />
              </th>
              <th colSpan={4} className="pmt-th pmt-th-section-risk">
                Risks
                <ColHint
                  label="Risks"
                  text="Aggregates over open risks (excludes issues & closed). Weighted = Σ(probability × impact). Total = Σ(impact)."
                />
              </th>
              <th colSpan={1} className="pmt-th pmt-th-section-risk">
                Issues
                <ColHint
                  label="Issues"
                  text="Non-eliminated issues (status ≠ CLOSED)."
                />
              </th>
              <th colSpan={3} className="pmt-th pmt-th-section-cost">
                Scope Changes
                <ColHint
                  label="Scope Changes"
                  text="Qty = count of scope changes with a numeric cost impact. Eval = sum of OPEN entries (€). Approved = sum of APPROVED entries (€)."
                />
              </th>
            </tr>

            {/* ── Row 2: sub-headers ──────────────────────────────── */}
            <tr className="pmt-subheader-row">
              {/* Financial — all values in k€ */}
              <th style={{ width: 96 }} className="pmt-th-sub pmt-th-section-cost">
                <SortBtn field="bac" sort={effectiveSort} onSort={handleSort} className="justify-center w-full">BAC</SortBtn>
                <ColHint label="BAC" text="Budget at Completion (k€)" />
              </th>
              <th style={{ width: 96 }} className="pmt-th-sub pmt-th-section-cost">
                <SortBtn field="eac" sort={effectiveSort} onSort={handleSort} className="justify-center w-full">EAC</SortBtn>
                <ColHint label="EAC" text="Estimate at Completion = actuals + committed + ETC (k€)" />
              </th>
              <th style={{ width: 82 }} className="pmt-th-sub pmt-th-section-cost">
                CONT
                <ColHint label="CONT" text="Budgeted risk + management contingency (k€)" />
              </th>
              <th style={{ width: 104 }} className="pmt-th-sub pmt-th-section-cost">
                <SortBtn field="vac" sort={effectiveSort} onSort={handleSort} className="justify-center w-full">VAC</SortBtn>
                <ColHint label="VAC" text="Variance at Completion = BAC − EAC (k€, positive = under budget)" />
              </th>
              <th style={{ width: 94 }} className="pmt-th-sub pmt-th-section-cost">
                ΔVAC
                <ColHint label="ΔVAC" text="Month-on-month VAC variance (k€)" />
              </th>
              <th style={{ width: 96 }} className="pmt-th-sub pmt-th-section-cost">
                ACT
                <ColHint label="ACT" text="Actuals (k€)" />
              </th>
              <th style={{ width: 96 }} className="pmt-th-sub pmt-th-section-cost">
                COMM
                <ColHint label="COMM" text="Committed (k€)" />
              </th>
              <th style={{ width: 88 }} className="pmt-th-sub pmt-th-section-cost">
                <SortBtn field="actPlanned" sort={effectiveSort} onSort={handleSort} className="justify-center w-full">A+C/BAC</SortBtn>
                <ColHint label="A+C/BAC" text="(Actuals + Committed) ÷ BAC" />
              </th>
              {/* Schedule */}
              <th style={{ width: 70 }} className="pmt-th-sub pmt-th-section-schedule">
                Float excl
                <ColHint label="Float excl." text="Total float excluding buffer (days). Manual input." />
              </th>
              <th style={{ width: 72 }} className="pmt-th-sub pmt-th-section-schedule">
                <SortBtn field="floatIncl" sort={effectiveSort} onSort={handleSort} className="justify-center w-full">Float incl</SortBtn>
                <ColHint label="Float incl." text="Total float including buffer (days). Manual input." />
              </th>
              <th style={{ width: 64 }} className="pmt-th-sub pmt-th-section-schedule">
                SVAC
                <ColHint
                  label="SVAC"
                  text="Schedule Variance = total float incl. buffer ÷ total days between green & white gate"
                />
              </th>
              <th style={{ width: 72 }} className="pmt-th-sub pmt-th-section-schedule">
                ΔSVAC
                <ColHint label="ΔSVAC" text="Month-on-month SVAC variance (% points)" />
              </th>
              <th style={{ width: 64 }} className="pmt-th-sub pmt-th-section-schedule">
                % Gate
                <ColHint label="% to next gate" text="Progress through lifecycle gates up to the next upcoming gate" />
              </th>
              <th style={{ width: 64 }} className="pmt-th-sub pmt-th-section-schedule">
                Res %
                <ColHint label="Resource consumption" text="Percentage of allocated resources consumed (manual input)" />
              </th>
              {/* Risks */}
              <th style={{ width: 80 }} className="pmt-th-sub pmt-th-section-risk">
                ΣP×C (k€)
                <ColHint label="Risk cost impact" text="Σ(probability × cost impact) over open risks. ‘Contingencies advised’." />
              </th>
              <th style={{ width: 80 }} className="pmt-th-sub pmt-th-section-risk">
                Σ Cost (k€)
                <ColHint label="Total risk cost" text="Σ(cost impact) over open risks — unweighted worst case." />
              </th>
              <th style={{ width: 78 }} className="pmt-th-sub pmt-th-section-risk">
                ΣP×T (d)
                <ColHint
                  label="Buffer advised"
                  text="Σ(probability × time impact) over open risks. Days of buffer recommended."
                />
              </th>
              <th style={{ width: 78 }} className="pmt-th-sub pmt-th-section-risk">
                Σ Days
                <ColHint label="Max risk delay" text="Σ(time impact) over open risks — unweighted." />
              </th>
              {/* Issues */}
              <th style={{ width: 56 }} className="pmt-th-sub pmt-th-section-risk">
                <SortBtn field="openIssues" sort={effectiveSort} onSort={handleSort} className="justify-center w-full">Open</SortBtn>
                <ColHint label="Open issues" text="Count of non-eliminated issues (status ≠ CLOSED)." />
              </th>
              {/* Scope */}
              <th style={{ width: 56 }} className="pmt-th-sub pmt-th-section-cost">
                <SortBtn field="scopeQty" sort={effectiveSort} onSort={handleSort} className="justify-center w-full">Qty</SortBtn>
                <ColHint label="Scope changes Qty" text="Number of scope changes with a numeric cost impact." />
              </th>
              <th style={{ width: 80 }} className="pmt-th-sub pmt-th-section-cost">
                Eval (k€)
                <ColHint label="Changes under evaluation" text="Σ impactCostValue where status = OPEN." />
              </th>
              <th style={{ width: 80 }} className="pmt-th-sub pmt-th-section-cost">
                Appr (k€)
                <ColHint label="Changes approved" text="Σ impactCostValue where status = APPROVED." />
              </th>
            </tr>
          </thead>

          <tbody>
            {execSummary.count > 0 && <SummaryRow summary={execSummary} variant="execution" />}
            {devSummary.count > 0 && <SummaryRow summary={devSummary} variant="development" />}

            {sortedRows.map((row) => (
              <DataRow
                key={row.project.id}
                row={row}
                onClick={() => router.push(`/projects/${row.project.id}`)}
              />
            ))}
          </tbody>
        </table>
    </div>
  );
}

/* ─── Data row ──────────────────────────────────────────────────────── */

function DataRow({ row, onClick }: { row: ComputedRow; onClick: () => void }) {
  const { project, financials, schedulePerf, riskAggregates, issueAggregates, scopeAggregates, ragTrends } = row;
  const phase = getPhaseByKey(project.currentPhase, project.lifecycleType);

  return (
    <tr className="exec-row cursor-pointer" onClick={onClick}>
      <td className="exec-td text-xs text-etex-gray-500 dark:text-etex-gray-400">
        <span className="font-mono tabular-nums">{formatDateShort(project.updatedAt)}</span>
      </td>
      <td className="exec-td exec-td-name">
        <span className="exec-project-link inline-flex items-center gap-1.5" title={project.name}>
          {project.isConfidential && (
            <Lock
              size={11}
              className="shrink-0 text-etex-gray-400 dark:text-gray-500"
              aria-label="Confidential project"
            />
          )}
          {project.name}
        </span>
        {project.factory && (
          <span className="exec-project-location">
            <CountryFlag code={project.factory.country} size={14} className="exec-project-flag" />
            <span className="exec-project-location-text">
              {project.factory.name}
              {project.factory.division?.name && (
                <span className="exec-project-division"> ({project.factory.division.name})</span>
              )}
            </span>
          </span>
        )}
      </td>
      {/* Lifecycle status — colored band, same format as Phase */}
      <td className="exec-td text-center">
        <ProjectStatusBadge status={project.status} />
      </td>
      {/* Flags — MSR, ExCom Presenting */}
      <td className="exec-td text-center">
        <FlagsCell flags={project.flags ?? []} />
      </td>
      {/* Phase + gate progression stacked */}
      <td className="exec-td p-0! overflow-hidden">
        <div className="flex flex-col">
          <div
            className="text-[10px] font-bold uppercase tracking-wide text-center py-1.5 px-2"
            style={phase ? { backgroundColor: phase.color, color: contrastText(phase.color) } : undefined}
          >
            {phase?.shortLabel ?? "—"}
          </div>
          <div className="flex items-center justify-center py-1 bg-gray-50/60 dark:bg-white/2">
            <GateProgression gates={project.gates ?? []} />
          </div>
        </div>
      </td>
      <td className="exec-td">
        <StakeholdersCell s={row.stakeholders} />
      </td>

      {/* RAG indicators — premium chip rack */}
      <td className="exec-td text-center px-0!">
        <RagStatusCell project={project} ragTrends={ragTrends} />
      </td>

      {/* Financial */}
      <td className="exec-td exec-td-section-start text-right font-mono tabular-nums text-xs">
        {fmtK(financials.bac)}
      </td>
      <td className="exec-td text-right font-mono tabular-nums text-xs">
        {fmtK(financials.eac)}
      </td>
      <td className="exec-td text-right font-mono tabular-nums text-xs text-etex-gray-600 dark:text-etex-gray-400">
        {fmtK(financials.cont)}
      </td>
      <td
        className={cn(
          "exec-td text-right font-mono tabular-nums text-xs font-semibold",
          getVarianceCellClass(financials.vac),
        )}
      >
        {fmtK(financials.vac, true)}
      </td>
      <td className="exec-td text-center text-xs">
        {financials.deltaVac == null ? (
          <span className="text-etex-gray-400">—</span>
        ) : (() => {
          const d = formatVariance(financials.deltaVac, { decimals: 0, suffix: "" });
          return (
            <span
              className={cn(
                "font-mono tabular-nums font-semibold",
                d.sentiment === "positive" ? "text-green-600" : "text-red-600",
              )}
            >
              {d.display}
            </span>
          );
        })()}
      </td>
      <td className="exec-td text-right font-mono tabular-nums text-xs">{fmtK(financials.act)}</td>
      <td className="exec-td text-right font-mono tabular-nums text-xs">{fmtK(financials.comm)}</td>
      <td className="exec-td text-center font-mono tabular-nums text-xs font-medium">
        {fmtPct(financials.actPlanned)}
      </td>

      {/* Schedule */}
      <td
        className={cn(
          "exec-td exec-td-section-start text-center font-mono tabular-nums text-xs",
          getDaysCellClass(schedulePerf.floatExcl),
        )}
      >
        {fmtDays(schedulePerf.floatExcl)}
      </td>
      <td
        className={cn(
          "exec-td text-center font-mono tabular-nums text-xs",
          getDaysCellClass(schedulePerf.floatIncl),
        )}
      >
        {fmtDays(schedulePerf.floatIncl)}
      </td>
      <td className="exec-td text-center font-mono tabular-nums text-xs font-medium">
        {fmtPct(schedulePerf.svac)}
      </td>
      <td className="exec-td text-center text-xs">
        {schedulePerf.svacDelta == null ? (
          <span className="text-etex-gray-400">—</span>
        ) : (
          <span
            className={cn(
              "font-mono tabular-nums font-semibold",
              schedulePerf.svacDelta > 0 ? "text-green-600" : schedulePerf.svacDelta < 0 ? "text-red-600" : "text-etex-gray-500",
            )}
          >
            {fmtPct(schedulePerf.svacDelta, true)}
          </span>
        )}
      </td>
      <td className="exec-td text-center font-mono tabular-nums text-xs">{schedulePerf.pctToNextGate}%</td>
      <td className="exec-td text-center font-mono tabular-nums text-xs">
        {schedulePerf.resourceConsumptionPct == null
          ? "—"
          : `${Math.round(schedulePerf.resourceConsumptionPct)}%`}
      </td>

      {/* Risks */}
      <td className="exec-td exec-td-section-start text-right font-mono tabular-nums text-xs">
        {fmtK(riskAggregates.weightedCostImpact)}
      </td>
      <td
        className={cn(
          "exec-td text-right font-mono tabular-nums text-xs",
          riskAggregates.totalRiskCost > 0 ? "text-red-600 dark:text-red-400" : "text-etex-gray-600 dark:text-etex-gray-400",
        )}
      >
        {fmtK(riskAggregates.totalRiskCost)}
      </td>
      <td className="exec-td text-right font-mono tabular-nums text-xs">
        {fmtDays(Math.round(riskAggregates.weightedTimeImpact))}
      </td>
      <td className="exec-td text-right font-mono tabular-nums text-xs text-amber-700 dark:text-amber-400">
        {fmtDays(Math.round(riskAggregates.totalRiskDelay))}
      </td>

      {/* Issues */}
      <td
        className={cn(
          "exec-td text-center font-mono tabular-nums text-xs font-semibold",
          issueAggregates.open > 0 ? "text-red-600 dark:text-red-400" : "text-etex-gray-500",
        )}
      >
        {fmtCount(issueAggregates.open)}
      </td>

      {/* Scope Changes */}
      <td className="exec-td exec-td-section-start text-center font-mono tabular-nums text-xs">
        {fmtCount(scopeAggregates.qtyImpactingCost)}
      </td>
      <td className="exec-td text-right font-mono tabular-nums text-xs">
        {fmtK(scopeAggregates.underEvaluationEur)}
      </td>
      <td className="exec-td text-right font-mono tabular-nums text-xs">
        {fmtK(scopeAggregates.approvedEur)}
      </td>
    </tr>
  );
}

/* ─── Summary Row ───────────────────────────────────────────────────── */

function SummaryRow({ summary, variant }: { summary: SummaryData; variant: "execution" | "development" }) {
  const { financials, schedulePerf, riskAggregates, issueAggregates, scopeAggregates } = summary;
  return (
    <tr
      className={cn(
        "exec-summary-row",
        variant === "execution" ? "exec-summary-execution" : "exec-summary-development",
      )}
    >
      {/* Updated (now merged with MSR) */}
      <td />
      {/* Project */}
      <td className="font-bold text-xs text-etex-charcoal dark:text-etex-gray-100 whitespace-nowrap">
        {summary.label}
      </td>
      {/* Lifecycle status */}
      <td />
      {/* Flags */}
      <td />
      {/* Phase */}
      <td />
      {/* Stakeholders */}
      <td />
      {/* RAG (compact one-column) */}
      <td />
      {/* Financial */}
      <td className="exec-td-section-start text-right font-mono tabular-nums text-xs font-bold">
        {fmtK(financials.bac)}
      </td>
      <td className="text-right font-mono tabular-nums text-xs font-bold">{fmtK(financials.eac)}</td>
      <td className="text-right font-mono tabular-nums text-xs font-bold">{fmtK(financials.cont)}</td>
      <td className={cn("text-right font-mono tabular-nums text-xs font-bold", getVarianceCellClass(financials.vac))}>
        {fmtK(financials.vac, true)}
      </td>
      <td className="text-center font-mono tabular-nums text-xs font-bold">
        {financials.deltaVac == null ? "—" : fmtK(financials.deltaVac, true)}
      </td>
      <td className="text-right font-mono tabular-nums text-xs font-bold">{fmtK(financials.act)}</td>
      <td className="text-right font-mono tabular-nums text-xs font-bold">{fmtK(financials.comm)}</td>
      <td className="text-center font-mono tabular-nums text-xs font-bold">{fmtPct(financials.actPlanned)}</td>
      {/* Schedule */}
      <td className="exec-td-section-start text-center font-mono tabular-nums text-xs font-bold">
        {fmtDays(schedulePerf.floatExcl)}
      </td>
      <td className="text-center font-mono tabular-nums text-xs font-bold">{fmtDays(schedulePerf.floatIncl)}</td>
      <td className="text-center font-mono tabular-nums text-xs font-bold">{fmtPct(schedulePerf.svac)}</td>
      <td className="text-center font-mono tabular-nums text-xs font-bold">
        {schedulePerf.svacDelta == null ? "—" : fmtPct(schedulePerf.svacDelta, true)}
      </td>
      <td className="text-center font-mono tabular-nums text-xs font-bold">{schedulePerf.pctToNextGate}%</td>
      <td className="text-center font-mono tabular-nums text-xs font-bold">
        {schedulePerf.resourceConsumptionPct == null
          ? "—"
          : `${Math.round(schedulePerf.resourceConsumptionPct)}%`}
      </td>
      {/* Risks */}
      <td className="exec-td-section-start text-right font-mono tabular-nums text-xs font-bold">
        {fmtK(riskAggregates.weightedCostImpact)}
      </td>
      <td className="text-right font-mono tabular-nums text-xs font-bold">
        {fmtK(riskAggregates.totalRiskCost)}
      </td>
      <td className="text-right font-mono tabular-nums text-xs font-bold">
        {fmtDays(Math.round(riskAggregates.weightedTimeImpact))}
      </td>
      <td className="text-right font-mono tabular-nums text-xs font-bold">
        {fmtDays(Math.round(riskAggregates.totalRiskDelay))}
      </td>
      {/* Issues */}
      <td className="text-center font-mono tabular-nums text-xs font-bold">{fmtCount(issueAggregates.open)}</td>
      {/* Scope */}
      <td className="exec-td-section-start text-center font-mono tabular-nums text-xs font-bold">
        {fmtCount(scopeAggregates.qtyImpactingCost)}
      </td>
      <td className="text-right font-mono tabular-nums text-xs font-bold">{fmtK(scopeAggregates.underEvaluationEur)}</td>
      <td className="text-right font-mono tabular-nums text-xs font-bold">{fmtK(scopeAggregates.approvedEur)}</td>
    </tr>
  );
}
