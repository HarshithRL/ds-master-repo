/**
 * Pure compute helpers for the projects table and the one-pager view.
 * No React, no DOM — just deterministic transforms over Prisma shapes.
 */

import type {
  Budget,
  ProjectAssignment,
  RAGStatus,
  ScopeChangeStatus,
  User,
} from "@/lib/db/models";
import type { ProjectListItem, ScopeChangeListItem, SnapshotListItem } from "@/types";
import { calcEAC, calcVariance } from "@/lib/calculations";

/* ── Stakeholders ─────────────────────────────────────────────────── */

/**
 * Format a user name as "F. LASTNAME" — first initial of the given name
 * plus the remaining tokens uppercased. Falls back to whatever's available.
 */
export function formatStakeholderName(name: string | null | undefined): string {
  if (!name) return "";
  const tokens = name.trim().split(/\s+/).filter(Boolean);
  if (tokens.length === 0) return "";
  if (tokens.length === 1) return tokens[0].toUpperCase();
  const [first, ...rest] = tokens;
  return `${first[0].toUpperCase()}. ${rest.join(" ").toUpperCase()}`;
}

export interface Stakeholders {
  /** Comma-joined stakeholder names — supports multiple persons per role. */
  sponsor: string | null;
  owner: string | null;
  manager: string | null;
}

function joinRole(
  assignments: (ProjectAssignment & { user: User })[],
  role: ProjectAssignment["role"],
): string | null {
  const names = assignments
    .filter((a) => a.role === role)
    .map((a) => formatStakeholderName(a.user.name))
    .filter(Boolean);
  return names.length ? names.join(", ") : null;
}

export function computeStakeholders(
  assignments: (ProjectAssignment & { user: User })[],
): Stakeholders {
  const safe = assignments ?? [];
  return {
    sponsor: joinRole(safe, "SPONSOR"),
    owner: joinRole(safe, "OWNER"),
    manager: joinRole(safe, "PROJECT_MANAGER"),
  };
}

/* ── Financial performance ────────────────────────────────────────── */

export interface Financials {
  bac: number;
  eac: number;
  cont: number; // budgeted risk + management contingency
  vac: number; // BAC − EAC (positive = under budget — matches Project Details)
  deltaVac: number | null; // current VAC − previous-snapshot VAC (positive = improving)
  act: number; // actuals
  comm: number; // committed
  actPlanned: number; // (act + comm) / bac, 0–1 (UI multiplies ×100)
}

/**
 * Compute financials from live budget components. Always uses
 * `EAC = actuals + committed + etc` and `VAC = BAC − EAC` — see
 * `lib/utils.ts` for the canonical formulas. Stored `budget.eac` and
 * `project.varianceAtCompletion` are denormalized and not read here.
 *
 * `prevVac` is the previous-period VAC for the ΔVAC trend — pass the
 * most recent snapshot's `varianceAtCompletion`.
 */
export function computeFinancials(
  budget: Budget | null,
  prevVac: number | null,
): Financials {
  const bac = budget?.bac ?? 0;
  const eac = budget ? calcEAC(budget) : 0;
  const act = budget?.actuals ?? 0;
  const comm = budget?.committed ?? 0;
  const cont =
    (budget?.riskContingencyBudgeted ?? 0) + (budget?.mgmtContingencyBudgeted ?? 0);
  const vac = budget ? calcVariance(budget) : 0;
  const deltaVac = prevVac == null ? null : vac - prevVac;
  const actPlanned = bac > 0 ? (act + comm) / bac : 0;
  return { bac, eac, cont, vac, deltaVac, act, comm, actPlanned };
}

/* ── Schedule performance ─────────────────────────────────────────── */

export interface SchedulePerf {
  floatExcl: number | null;
  floatIncl: number | null;
  svac: number | null; // 0–1, fraction (UI ×100)
  svacDelta: number | null; // current SVAC − prev SVAC (in fraction points)
  pctToNextGate: number; // existing computeUntilNextGate result, 0–100
  resourceConsumptionPct: number | null;
}

export function computeSchedulePerf(
  project: Pick<
    ProjectListItem,
    | "totalFloatExclBuffer"
    | "totalFloatInclBuffer"
    | "totalFloatInclBufferPrev"
    | "daysGreenToWhite"
    | "resourceConsumptionPct"
  >,
  pctToNextGate: number,
): SchedulePerf {
  const denom = project.daysGreenToWhite ?? 0;
  const svac =
    project.totalFloatInclBuffer != null && denom > 0
      ? project.totalFloatInclBuffer / denom
      : null;
  const svacPrev =
    project.totalFloatInclBufferPrev != null && denom > 0
      ? project.totalFloatInclBufferPrev / denom
      : null;
  const svacDelta = svac != null && svacPrev != null ? svac - svacPrev : null;

  return {
    floatExcl: project.totalFloatExclBuffer ?? null,
    floatIncl: project.totalFloatInclBuffer ?? null,
    svac,
    svacDelta,
    pctToNextGate,
    resourceConsumptionPct: project.resourceConsumptionPct ?? null,
  };
}

/* ── Risk aggregates (RISK type only — excludes ISSUEs) ───────────── */

export interface RiskAggregates {
  /** Σ (probability × costImpact) for open RISK-type entries, in k€. */
  weightedCostImpact: number;
  /** Σ (costImpact) for open RISK-type entries, in k€. */
  totalRiskCost: number;
  /** Σ (probability × timeImpact) in days for open RISK-type entries. */
  weightedTimeImpact: number;
  /** Σ (timeImpact) in days for open RISK-type entries. */
  totalRiskDelay: number;
}

export function computeRiskAggregates(
  risks: ProjectListItem["risks"],
): RiskAggregates {
  let weightedCostImpact = 0;
  let totalRiskCost = 0;
  let weightedTimeImpact = 0;
  let totalRiskDelay = 0;

  for (const r of (risks ?? [])) {
    if (r.type !== "RISK") continue;
    if (r.status === "CLOSED") continue;
    const p = (r.probability ?? 0) / 100;
    const cost = r.costImpact ?? 0;
    const time = r.timeImpact ?? 0;
    weightedCostImpact += p * cost;
    totalRiskCost += cost;
    weightedTimeImpact += p * time;
    totalRiskDelay += time;
  }

  return { weightedCostImpact, totalRiskCost, weightedTimeImpact, totalRiskDelay };
}

/* ── Issue aggregates (ISSUE type only) ───────────────────────────── */

export interface IssueAggregates {
  open: number; // non-eliminated (status != CLOSED)
}

export function computeIssueAggregates(
  risks: ProjectListItem["risks"],
): IssueAggregates {
  let open = 0;
  for (const r of (risks ?? [])) {
    if (r.type !== "ISSUE") continue;
    if (r.status !== "CLOSED") open += 1;
  }
  return { open };
}

/* ── Scope change aggregates ──────────────────────────────────────── */

export interface ScopeChangeAggregates {
  /** Count of scope changes with a non-null impactCostValue. */
  qtyImpactingCost: number;
  /** Σ impactCostValue where status === OPEN (under evaluation), in k€. */
  underEvaluationEur: number;
  /** Σ impactCostValue where status === APPROVED, in k€. */
  approvedEur: number;
}

const SCOPE_OPEN: ScopeChangeStatus = "OPEN";
const SCOPE_APPROVED: ScopeChangeStatus = "APPROVED";

export function computeScopeChangeAggregates(
  scopeChanges: ScopeChangeListItem[],
): ScopeChangeAggregates {
  let qtyImpactingCost = 0;
  let underEvaluationEur = 0;
  let approvedEur = 0;
  for (const sc of (scopeChanges ?? [])) {
    const cost = sc.impactCostValue;
    if (cost == null) continue;
    qtyImpactingCost += 1;
    if (sc.status === SCOPE_OPEN) underEvaluationEur += cost;
    else if (sc.status === SCOPE_APPROVED) approvedEur += cost;
  }
  return { qtyImpactingCost, underEvaluationEur, approvedEur };
}

/* ── RAG trend ────────────────────────────────────────────────────── */

export type TrendDirection = "up" | "down" | "same" | "unknown";

/**
 * Compare two RAG values on the GREEN > AMBER > RED scale.
 * Up = improved (e.g. AMBER → GREEN). Down = worsened. Same = identical.
 */
const RAG_SCORE: Record<RAGStatus, number> = { RED: 1, AMBER: 2, GREEN: 3 };

export function ragTrend(
  current: RAGStatus | null | undefined,
  previous: RAGStatus | null | undefined,
): TrendDirection {
  if (!current || !previous) return "unknown";
  const c = RAG_SCORE[current];
  const p = RAG_SCORE[previous];
  if (c > p) return "up";
  if (c < p) return "down";
  return "same";
}

/** Six RAG dimensions shown in the table, in display order. */
export const RAG_DIMENSIONS = [
  { key: "ragProgress", label: "Overall" },
  { key: "ragCost", label: "Cost" },
  { key: "ragSchedule", label: "Schedule" },
  { key: "ragRisk", label: "Risk" },
  { key: "ragScope", label: "Scope" },
  { key: "ragResources", label: "Resources" },
] as const;

export type RagDimensionKey = (typeof RAG_DIMENSIONS)[number]["key"];

/** Field name on Project that stores the free-text label for a given RAG dimension. */
export const RAG_LABEL_FIELD: Record<RagDimensionKey, keyof ProjectListItem> = {
  ragProgress: "ragProgressLabel",
  ragCost: "ragCostLabel",
  ragSchedule: "ragScheduleLabel",
  ragRisk: "ragRiskLabel",
  ragScope: "ragScopeLabel",
  ragResources: "ragResourcesLabel",
};

/** Build per-dimension trend lookups using the most recent snapshot as baseline. */
export function computeRagTrends(
  project: Pick<
    ProjectListItem,
    "ragProgress" | "ragCost" | "ragSchedule" | "ragRisk" | "ragScope" | "ragResources"
  >,
  prevSnapshot: SnapshotListItem | undefined,
): Record<RagDimensionKey, TrendDirection> {
  return {
    ragProgress: ragTrend(project.ragProgress, prevSnapshot?.ragProgress),
    ragCost: ragTrend(project.ragCost, prevSnapshot?.ragCost),
    ragSchedule: ragTrend(project.ragSchedule, prevSnapshot?.ragSchedule),
    ragRisk: ragTrend(project.ragRisk, prevSnapshot?.ragRisk),
    ragScope: ragTrend(project.ragScope, prevSnapshot?.ragScope),
    ragResources: ragTrend(project.ragResources, prevSnapshot?.ragResources),
  };
}
