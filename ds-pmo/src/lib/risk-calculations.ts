import type { RiskSummary } from "@/lib/risk-summary";
import { calcPlannedDuration } from "@/lib/calculations";

/* ── Computed risk metrics ─────────────────────────────────────── */

/**
 * Project-level exposure derived from the aggregate Risk Summary inputs.
 * The detail Risk register holds at most the top 5 — full-register aggregates
 * live as RIAC-autofilled fields on `Project`, so nothing here scans rows.
 *
 * Risk Level % (probability-weighted EMV/EAC) was removed because it required
 * iterating all risks; without the full register, the number would
 * underrepresent exposure and create a false sense of accuracy.
 */
export interface RiskMetrics {
  /** Worst-case cost exposure: totalCostAtRisk / EAC × 100. */
  costAtRiskPct: number;
  /** Total unweighted cost impact (k€) — mirrors riskSummary.totalCostAtRisk. */
  costAtRiskKeur: number;
  /** Max time impact as % of planned project duration. */
  timeAtRiskPct: number;
}

/* ── Core computation ──────────────────────────────────────────── */

/**
 * Compute project risk metrics from aggregate inputs + EAC + planned duration.
 *
 * - **Cost at Risk %** — totalCostAtRisk / EAC (worst-case, unweighted)
 * - **Cost at Risk k€** — totalCostAtRisk passthrough
 * - **Time at Risk %** — totalTimeImpact / planned duration, anchored at
 *   the project's actual start date
 */
export function computeRiskMetrics(
  riskSummary: RiskSummary,
  eac: number,
  /** Effective project start — pass `actualStartDate ?? createdAt`. */
  start: Date | string | null,
  plannedCompletionDate: Date | string | null,
): RiskMetrics {
  const costAtRiskPct = eac > 0 ? (riskSummary.totalCostAtRisk / eac) * 100 : 0;
  const plannedDays = calcPlannedDuration(start, plannedCompletionDate);
  const timeAtRiskPct = plannedDays > 0 ? (riskSummary.totalTimeImpact / plannedDays) * 100 : 0;

  return {
    costAtRiskPct: round1(costAtRiskPct),
    costAtRiskKeur: round1(riskSummary.totalCostAtRisk),
    timeAtRiskPct: round1(timeAtRiskPct),
  };
}

function round1(v: number): number {
  return Math.round(v * 10) / 10;
}
