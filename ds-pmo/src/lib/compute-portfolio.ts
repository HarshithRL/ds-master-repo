import { TIERS, isExecutionPhase } from "@/lib/constants";
import { computeProgress } from "@/lib/progress";
import { calcEAC, calcVariance } from "@/lib/calculations";
import type {
  LifecycleType,
  ProjectTier,
} from "@/lib/db/models";
import type { PortfolioSummary } from "@/types";

interface PortfolioGate {
  gate: string;
  status: string;
  plannedDate: Date | string | null;
  completedDate: Date | string | null;
}

/**
 * Minimal project shape needed to compute the portfolio summary.
 * Both the API route (`/api/portfolio`) and the dashboard's
 * client-side filtered recompute pass values of this shape.
 *
 * `ProjectListItem` from /types is a superset of this shape, so client
 * callers can pass it directly without any mapping.
 */
export interface PortfolioInput {
  currentPhase: string;
  currentGate: string | null;
  lifecycleType: LifecycleType;
  tier: ProjectTier;
  scheduleBuffer: number | null;
  // Risk summary inputs — stored on Project, autofilled by RIAC
  risksIssuesCount: number | null;
  risksHighCount: number | null;
  risksModerateCount: number | null;
  risksLowCount: number | null;
  // Budget components — EAC and VAC derived live via lib/utils.ts
  budget: {
    bac: number;
    actuals: number;
    committed: number;
    expected: number;
  } | null;
  factory: {
    name: string;
    division: { name: string } | null;
  } | null;
  gates: PortfolioGate[];
}

/**
 * Aggregate a portfolio summary from a list of projects.
 * Single source of truth — used by both the server `/api/portfolio` route
 * and the dashboard's client-side recompute after filter changes.
 */
export function computePortfolio(projects: PortfolioInput[]): PortfolioSummary {
  const eacOf = (p: PortfolioInput) => (p.budget ? calcEAC(p.budget) : 0);
  /** Sum of the four editable risk-summary counts — proxy for "active risks". */
  const activeRiskCount = (p: PortfolioInput) =>
    (p.risksIssuesCount ?? 0) +
    (p.risksHighCount ?? 0) +
    (p.risksModerateCount ?? 0) +
    (p.risksLowCount ?? 0);

  const totalProjects = projects.length;
  const totalEAC = projects.reduce((s, p) => s + eacOf(p), 0);
  const totalBAC = projects.reduce((s, p) => s + (p.budget?.bac ?? 0), 0);
  const totalActuals = projects.reduce((s, p) => s + (p.budget?.actuals ?? 0), 0);
  const totalCommitted = projects.reduce((s, p) => s + (p.budget?.committed ?? 0), 0);
  const totalVariance = totalBAC - totalEAC;

  const totalProgress = projects.reduce((s, p) => s + computeProgress(p.gates ?? []), 0);
  const avgProgress = totalProjects > 0 ? totalProgress / totalProjects : 0;

  const atRiskCount = projects.filter((p) => activeRiskCount(p) >= 3).length;
  const overBudgetCount = projects.filter(
    (p) => p.budget && p.budget.bac > 0 && calcVariance(p.budget) < 0,
  ).length;
  const inExecutionCount = projects.filter((p) =>
    isExecutionPhase(p.currentPhase, p.lifecycleType),
  ).length;

  const withSchedule = projects.filter((p) => p.scheduleBuffer != null);
  const onTimeCount = withSchedule.filter((p) => p.scheduleBuffer! >= 0).length;
  const delayedCount = withSchedule.filter((p) => p.scheduleBuffer! < 0).length;

  /** Group by a string key, accumulating count + total EAC per bucket. */
  function groupByEAC<K extends string>(
    keyOf: (p: PortfolioInput) => K,
    preinit?: K[],
  ): Array<{ key: K; count: number; eac: number }> {
    const map = new Map<K, { count: number; eac: number }>();
    if (preinit) for (const k of preinit) map.set(k, { count: 0, eac: 0 });
    for (const p of projects) {
      const k = keyOf(p);
      const entry = map.get(k) ?? { count: 0, eac: 0 };
      entry.count++;
      entry.eac += eacOf(p);
      map.set(k, entry);
    }
    return [...map.entries()].map(([key, v]) => ({ key, count: v.count, eac: v.eac }));
  }

  const byPhase = groupByEAC((p) => p.currentPhase).map(({ key, count, eac }) => ({
    phase: key, count, eac,
  }));
  const byGate = groupByEAC<string>((p) => p.currentGate ?? "_NONE")
    .filter(({ key }) => key !== "_NONE")
    .map(({ key, count, eac }) => ({ gate: key, count, eac }));
  const byTier = groupByEAC<string>((p) => p.tier, Object.keys(TIERS))
    .map(({ key, count, eac }) => ({ tier: key, count, eac }));
  const byFactory = groupByEAC((p) => p.factory?.name ?? "Unassigned")
    .map(({ key, count, eac }) => ({ factory: key, count, eac }));
  const byDivision = groupByEAC((p) => p.factory?.division?.name ?? "Unassigned")
    .map(({ key, count, eac }) => ({ division: key, count, eac }));

  const riskSummary = projects.reduce(
    (acc, p) => ({
      high: acc.high + (p.risksHighCount ?? 0),
      moderate: acc.moderate + (p.risksModerateCount ?? 0),
      low: acc.low + (p.risksLowCount ?? 0),
      issues: acc.issues + (p.risksIssuesCount ?? 0),
    }),
    { high: 0, moderate: 0, low: 0, issues: 0 },
  );

  return {
    totalProjects,
    totalEAC,
    totalBAC,
    totalActuals,
    totalCommitted,
    totalVariance,
    avgProgress,
    atRiskCount,
    overBudgetCount,
    inExecutionCount,
    onTimeCount,
    delayedCount,
    byPhase,
    byGate,
    byTier,
    byFactory,
    byDivision,
    riskSummary,
  };
}
