import { countRows } from "./db/query-builder";
import { countClosedRisksForProjects } from "./db/risks";
import { getProjectRaw } from "./db/projects";

export interface RiskSummary {
  /** From Project.risksIssuesCount — editable input, autofilled by RIAC */
  risksIssues: number;
  /** From Project.risksHighCount — editable input, autofilled by RIAC */
  risksHigh: number;
  /** From Project.risksModerateCount — editable input, autofilled by RIAC */
  risksModerate: number;
  /** From Project.risksLowCount — editable input, autofilled by RIAC */
  risksLow: number;
  /** Computed from Risk table (rows with status='CLOSED') */
  risksClosed: number;
  /** From Project.risksIdentifiedCount — editable input, autofilled by RIAC */
  risksIdentified: number;
  /** From Project.risksQuantifiedCount — editable input, autofilled by RIAC */
  risksQuantified: number;
  /** From Project.totalCostAtRisk (k€) — editable input, autofilled by RIAC */
  totalCostAtRisk: number;
  /** From Project.totalTimeImpact (days) — editable input, autofilled by RIAC */
  totalTimeImpact: number;
}

/** Shape needed to build RiskSummary without re-fetching the project row. */
export type ProjectRiskInputFields = {
  risksIssuesCount: number | null;
  risksHighCount: number | null;
  risksModerateCount: number | null;
  risksLowCount: number | null;
  risksIdentifiedCount: number | null;
  risksQuantifiedCount: number | null;
  totalCostAtRisk: number | null;
  totalTimeImpact: number | null;
};

/**
 * Pure builder: assemble the RiskSummary from a project row + its closed-risk
 * count. No DB. Use this when you already have the project loaded.
 */
export function buildRiskSummary(
  project: ProjectRiskInputFields,
  closedCount: number,
): RiskSummary {
  return {
    risksIssues: project.risksIssuesCount ?? 0,
    risksHigh: project.risksHighCount ?? 0,
    risksModerate: project.risksModerateCount ?? 0,
    risksLow: project.risksLowCount ?? 0,
    risksClosed: closedCount,
    risksIdentified: project.risksIdentifiedCount ?? 0,
    risksQuantified: project.risksQuantifiedCount ?? 0,
    totalCostAtRisk: project.totalCostAtRisk ?? 0,
    totalTimeImpact: project.totalTimeImpact ?? 0,
  };
}

/** Closed-risk count for ONE project. */
export async function fetchClosedRiskCount(projectId: string): Promise<number> {
  return countRows("risks", [
    { type: "eq", column: "project_id", value: projectId },
    { type: "eq", column: "status", value: "CLOSED" },
  ]);
}

/**
 * Closed-risk counts for MANY projects, batched (one query, not N).
 * Replaces N round trips with 1 when building the projects list.
 */
export async function fetchClosedRiskCounts(projectIds: string[]): Promise<Map<string, number>> {
  if (projectIds.length === 0) return new Map();
  return countClosedRisksForProjects(projectIds);
}

/**
 * Convenience wrapper for callers that don't already have the project row.
 * Two queries (project select + closed count). Prefer the pure
 * `buildRiskSummary` helper when the project is already loaded.
 */
export async function computeRiskSummary(projectId: string): Promise<RiskSummary> {
  const [project, closedCount] = await Promise.all([
    getProjectRaw(projectId),
    fetchClosedRiskCount(projectId),
  ]);
  return buildRiskSummary(
    project ?? {
      risksIssuesCount: null,
      risksHighCount: null,
      risksModerateCount: null,
      risksLowCount: null,
      risksIdentifiedCount: null,
      risksQuantifiedCount: null,
      totalCostAtRisk: null,
      totalTimeImpact: null,
    },
    closedCount,
  );
}
