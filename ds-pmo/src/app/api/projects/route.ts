import { withHandler, createAuditLog } from "@/lib/api-handler";
import { createProjectSchema, type CreateProjectInput } from "@/lib/validations";
import { RATE_LIMITS } from "@/lib/rate-limit";
import { sendEmailAsync, projectAssignmentEmail } from "@/lib/email";
import { buildRiskSummary, fetchClosedRiskCounts } from "@/lib/risk-summary";
import { getDefaultPhase, isExecutionPhase, LIFECYCLE_TYPES, getPhasesForLifecycle } from "@/lib/constants";
import { normalizeLifecycleFilter } from "@/lib/lifecycle-filter";
import { visibleProjectsWhere, confidentialProjectAccess } from "@/lib/access-control";
import {
  listProjectRows,
  countProjects,
  attachListRelations,
  createProject,
  getProjectFull,
  type ProjectFilters,
} from "@/lib/db/projects";
import { createBudgetForProject } from "@/lib/db/budgets";
import { createDefaultGates } from "@/lib/db/gates";
import { replaceAssignmentsForProject } from "@/lib/db/assignments";
import type { OrderBy } from "@/lib/db/query-builder";
import {
  computeFinancials,
  computeSchedulePerf,
  computeRiskAggregates,
  computeIssueAggregates,
  computeScopeChangeAggregates,
  type Financials,
  type SchedulePerf,
  type RiskAggregates,
  type IssueAggregates,
  type ScopeChangeAggregates,
} from "@/lib/project-table-metrics";
import { withResolvedBac } from "@/lib/calculations";
import { withDerivedProjectFields, type ProjectShape } from "@/lib/project-derive";
import { computeUntilNextGate } from "@/lib/progress";
import { GATE_KEYS } from "@/lib/constants";
import { NextResponse } from "next/server";

/* ─── Pagination + sort constants ─────────────────────────────────────── */

const DEFAULT_PAGE_SIZE = 25;
const MAX_PAGE_SIZE = 200;

/**
 * `current_phase` is a free-text key ("IDEATION", "BENEFITS", ...) whose
 * alphabetical order has nothing to do with PLC stage order. Build a SQL
 * CASE expression mapping (lifecycle, phase key) → that lifecycle's
 * `phaseNumber` (from lib/constants.ts — Engineering and IT define
 * divergent numbers for some later phases, e.g. BENEFITS is 8 vs 7), so
 * `ORDER BY` follows Ideation → ... → Closed instead of A → Z. Values are
 * our own static constants, not user input — safe to inline directly.
 */
function buildPhaseOrderExpr(): string {
  const arms = LIFECYCLE_TYPES.flatMap((lc) =>
    getPhasesForLifecycle(lc.key).map(
      (phase) => `WHEN lifecycle_type = '${lc.key}' AND current_phase = '${phase.key}' THEN ${phase.phaseNumber}`,
    ),
  );
  return `(CASE ${arms.join(" ")} ELSE 999 END)`;
}

const PHASE_ORDER_EXPR = buildPhaseOrderExpr();

/** Sort fields the database can order by directly (project / budget columns). */
const SORTABLE_FIELDS: Record<string, { kind: "project" | "budget"; column: string }> = {
  name: { kind: "project", column: "name" },
  updatedAt: { kind: "project", column: "updated_at" },
  reference: { kind: "project", column: "reference" },
  phase: { kind: "project", column: PHASE_ORDER_EXPR },
  currentPhase: { kind: "project", column: PHASE_ORDER_EXPR },
  tier: { kind: "project", column: "tier" },
  progress: { kind: "project", column: "progress" },
  plannedCompletionDate: { kind: "project", column: "planned_completion_date" },
  floatIncl: { kind: "project", column: "total_float_incl_buffer" },
  bac: { kind: "budget", column: "bac" },
};

type SummaryRow = {
  currentPhase: string;
  lifecycleType: string | null;
  plannedCompletionDate: Date | null;
  expectedCompletionDate: Date | null;
  totalFloatExclBuffer: number | null;
  totalFloatInclBuffer: number | null;
  resourceConsumptionPct: number | null;
  budget: Parameters<typeof computeFinancials>[0];
  gates: { gate: string; status: string; plannedDate: Date | null; completedDate: Date | null }[];
  risks: Parameters<typeof computeRiskAggregates>[0];
  scopeChanges: Parameters<typeof computeScopeChangeAggregates>[0];
  snapshots: {
    varianceAtCompletion: number | null;
    scheduleBuffer: number | null;
    totalFloatInclBuffer: number | null;
  }[];
};

interface SummaryBucket {
  count: number;
  financials: Financials;
  schedulePerf: SchedulePerf;
  riskAggregates: RiskAggregates;
  issueAggregates: IssueAggregates;
  scopeAggregates: ScopeChangeAggregates;
  pctGate: number;
}

function emptyBucket(): SummaryBucket {
  return {
    count: 0,
    financials: { bac: 0, eac: 0, cont: 0, vac: 0, deltaVac: null, act: 0, comm: 0, actPlanned: 0 },
    schedulePerf: { floatExcl: null, floatIncl: null, svac: null, svacDelta: null, pctToNextGate: 0, resourceConsumptionPct: null },
    riskAggregates: { weightedCostImpact: 0, totalRiskCost: 0, weightedTimeImpact: 0, totalRiskDelay: 0 },
    issueAggregates: { open: 0 },
    scopeAggregates: { qtyImpactingCost: 0, underEvaluationEur: 0, approvedEur: 0 },
    pctGate: 0,
  };
}

/** Reduce a list of summary rows into a single bucket. */
function aggregateBucket(rows: SummaryRow[]): SummaryBucket {
  if (rows.length === 0) return emptyBucket();

  let bac = 0, eac = 0, cont = 0, act = 0, comm = 0;
  let weightedCost = 0, totalRiskCost = 0, weightedTime = 0, totalRiskDelay = 0;
  let openIssues = 0;
  let scopeQty = 0, scopeEval = 0, scopeAppr = 0;
  let pctGateSum = 0;
  let floatExclSum = 0, floatExclCount = 0;
  let floatInclSum = 0, floatInclCount = 0;
  let svacSum = 0, svacCount = 0;
  let svacDeltaSum = 0, svacDeltaCount = 0;
  let resSum = 0, resCount = 0;
  let deltaVacSum = 0, deltaVacCount = 0;

  for (const raw of rows) {
    // Attach derived fields so computeSchedulePerf can read totalFloatInclBufferPrev
    // (now sourced from the latest snapshot rather than a stored column).
    const r = withDerivedProjectFields(raw);
    const prevVac = r.snapshots[0]?.varianceAtCompletion ?? null;
    const f = computeFinancials(r.budget, prevVac);
    bac += f.bac; eac += f.eac; cont += f.cont; act += f.act; comm += f.comm;
    if (f.deltaVac != null) { deltaVacSum += f.deltaVac; deltaVacCount++; }

    const pctGate = computeUntilNextGate(r.gates);
    pctGateSum += pctGate;

    const sp = computeSchedulePerf(r, pctGate);
    if (sp.floatExcl != null) { floatExclSum += sp.floatExcl; floatExclCount++; }
    if (sp.floatIncl != null) { floatInclSum += sp.floatIncl; floatInclCount++; }
    if (sp.svac != null) { svacSum += sp.svac; svacCount++; }
    if (sp.svacDelta != null) { svacDeltaSum += sp.svacDelta; svacDeltaCount++; }
    if (sp.resourceConsumptionPct != null) { resSum += sp.resourceConsumptionPct; resCount++; }

    const ra = computeRiskAggregates(r.risks);
    weightedCost += ra.weightedCostImpact;
    totalRiskCost += ra.totalRiskCost;
    weightedTime += ra.weightedTimeImpact;
    totalRiskDelay += ra.totalRiskDelay;

    openIssues += computeIssueAggregates(r.risks).open;

    const sc = computeScopeChangeAggregates(r.scopeChanges);
    scopeQty += sc.qtyImpactingCost;
    scopeEval += sc.underEvaluationEur;
    scopeAppr += sc.approvedEur;
  }

  const count = rows.length;
  const vac = bac - eac;
  return {
    count,
    financials: {
      bac, eac, cont, vac,
      deltaVac: deltaVacCount ? deltaVacSum : null,
      act, comm,
      actPlanned: bac > 0 ? (act + comm) / bac : 0,
    },
    schedulePerf: {
      floatExcl: floatExclCount ? Math.round(floatExclSum / floatExclCount) : null,
      floatIncl: floatInclCount ? Math.round(floatInclSum / floatInclCount) : null,
      svac: svacCount ? svacSum / svacCount : null,
      svacDelta: svacDeltaCount ? svacDeltaSum / svacDeltaCount : null,
      pctToNextGate: Math.round(pctGateSum / count),
      resourceConsumptionPct: resCount ? resSum / resCount : null,
    },
    riskAggregates: {
      weightedCostImpact: weightedCost,
      totalRiskCost,
      weightedTimeImpact: weightedTime,
      totalRiskDelay,
    },
    issueAggregates: { open: openIssues },
    scopeAggregates: {
      qtyImpactingCost: scopeQty,
      underEvaluationEur: scopeEval,
      approvedEur: scopeAppr,
    },
    pctGate: Math.round(pctGateSum / count),
  };
}

/* ─── Filter + sort parsing ────────────────────────────────────────────── */

function parseFilters(
  sp: URLSearchParams,
  visibility: ProjectFilters["visibility"],
  confidentialAccess: ProjectFilters["confidentialAccess"],
): ProjectFilters {
  const csv = (k: string) => sp.get(k)?.split(",").filter(Boolean);
  return {
    includeInactive: sp.get("inactive") === "true",
    msrOnly: sp.get("msrOnly") === "true",
    excomOnly: sp.get("excomOnly") === "true",
    search: sp.get("search") || undefined,
    phase: csv("phase"),
    lifecycleType: normalizeLifecycleFilter(sp.get("lifecycle")),
    tier: csv("tier"),
    factoryNames: csv("factory"),
    divisionNames: csv("division"),
    categoryNames: csv("category"),
    pmoUserIds: csv("pmo"),
    pmUserIds: csv("pm"),
    ownerUserIds: csv("owner"),
    sponsorUserIds: csv("sponsor"),
    status: csv("status"),
    visibility,
    confidentialAccess,
  };
}

function buildOrderBy(sortByRaw: string | null, sortDirRaw: string | null): { orderBy: OrderBy[]; joinBudget: boolean } {
  const dir = sortDirRaw?.toLowerCase() === "desc" ? "DESC" : "ASC";
  const cfg = SORTABLE_FIELDS[sortByRaw ?? ""] ?? SORTABLE_FIELDS.name;
  if (cfg.kind === "budget") {
    return { orderBy: [{ column: `b.${cfg.column}`, direction: dir }], joinBudget: true };
  }
  return { orderBy: [{ column: cfg.column, direction: dir }], joinBudget: false };
}

/* ─── GET handler ─────────────────────────────────────────────────────── */

export const GET = withHandler(
  { rateLimit: RATE_LIMITS.read },
  async ({ req, user }) => {
    const { searchParams } = new URL(req.url);
    const [visibility, confidentialAccess] = await Promise.all([
      visibleProjectsWhere(user),
      confidentialProjectAccess(user),
    ]);
    const filters = parseFilters(searchParams, visibility, confidentialAccess);
    const { orderBy, joinBudget } = buildOrderBy(searchParams.get("sortBy"), searchParams.get("sortDir"));

    const pageParam = searchParams.get("page");
    const paginated = pageParam != null;

    // Backward-compatible path: caller didn't ask for pagination, return array.
    if (!paginated) {
      const rows = await listProjectRows(filters, { orderBy, joinBudgetForSort: joinBudget });
      const projects = await attachListRelations(rows);
      const closedCounts = await fetchClosedRiskCounts(rows.map((p) => p.id));
      const withSummary = projects.map((p) => ({
        ...withDerivedProjectFields(p as unknown as ProjectShape & Record<string, unknown>),
        budget: p.budget ? withResolvedBac(p.budget as Parameters<typeof withResolvedBac>[0]) : p.budget,
        riskSummary: buildRiskSummary(p as Parameters<typeof buildRiskSummary>[0], closedCounts.get(p.id as string) ?? 0),
      }));
      return NextResponse.json(withSummary);
    }

    const page = Math.max(1, Number.parseInt(pageParam ?? "1", 10) || 1);
    const pageSize = Math.min(
      MAX_PAGE_SIZE,
      Math.max(1, Number.parseInt(searchParams.get("pageSize") ?? `${DEFAULT_PAGE_SIZE}`, 10) || DEFAULT_PAGE_SIZE),
    );

    // NOTE: reuses the full attachListRelations fan-out for the summary set
    // rather than a narrower projection (the old SUMMARY_SELECT) — correct,
    // but fetches more than strictly needed; worth narrowing if this becomes
    // a hot path on large portfolios.
    const [rows, total, summaryRows] = await Promise.all([
      listProjectRows(filters, { orderBy, joinBudgetForSort: joinBudget, limit: pageSize, offset: (page - 1) * pageSize }),
      countProjects(filters),
      listProjectRows(filters).then(attachListRelations),
    ]);

    const items = await attachListRelations(rows);
    const closedCounts = await fetchClosedRiskCounts(rows.map((p) => p.id));
    const withRiskSummary = items.map((p) => ({
      ...withDerivedProjectFields(p as unknown as ProjectShape & Record<string, unknown>),
      budget: p.budget ? withResolvedBac(p.budget as Parameters<typeof withResolvedBac>[0]) : p.budget,
      riskSummary: buildRiskSummary(p as Parameters<typeof buildRiskSummary>[0], closedCounts.get(p.id as string) ?? 0),
    }));

    const normalizedSummary = (summaryRows as unknown as SummaryRow[]).map((r) => ({
      ...r,
      budget: r.budget ? withResolvedBac(r.budget) : r.budget,
    }));
    const execRows = normalizedSummary.filter((r) => isExecutionPhase(r.currentPhase, r.lifecycleType));
    const devRows = normalizedSummary.filter((r) => !isExecutionPhase(r.currentPhase, r.lifecycleType));

    return NextResponse.json({
      items: withRiskSummary,
      total,
      page,
      pageSize,
      summary: {
        execution: aggregateBucket(execRows),
        development: aggregateBucket(devRows),
      },
    });
  },
);

export const POST = withHandler<CreateProjectInput>(
  {
    // Project creation is an admin-only operation — PMOs and others request
    // projects through admins. Matches the existing org workflow at Etex.
    requireAdmin: true,
    schema: createProjectSchema,
    rateLimit: RATE_LIMITS.mutation,
  },
  async ({ user, body }) => {
    const project = await createProject({
      reference: body.reference,
      name: body.name,
      description: body.description,
      objective: body.objective,
      scope: body.scope,
      factoryId: body.factoryId,
      categoryId: body.categoryId,
      tier: body.tier,
      lifecycleType: body.lifecycleType,
      status: body.status,
      plannedCompletionDate: body.plannedCompletionDate,
      expectedCompletionDate: body.expectedCompletionDate,
      currentPhase: getDefaultPhase(body.lifecycleType),
      flags: body.flags,
      wbsCodes: body.wbsCodes,
      isConfidential: body.isConfidential,
    });

    await createBudgetForProject(project.id);
    await createDefaultGates(project.id, [...GATE_KEYS]);

    if (body.assignments.length > 0) {
      await replaceAssignmentsForProject(project.id, body.assignments);
    }

    await createAuditLog({
      userId: user.id,
      projectId: project.id,
      action: "CREATE",
      entity: "Project",
      entityId: project.id,
      changes: {
        reference: { old: null, new: body.reference },
        name: { old: null, new: body.name },
        tier: { old: null, new: body.tier },
      },
    });

    const fullProject = await getProjectFull(project.id);

    // Notify assigned users (fire-and-forget)
    const assignments = (fullProject?.assignments as { user: { email: string | null; name: string } | null; role: string }[]) ?? [];
    if (assignments.length) {
      const baseUrl = process.env.AUTH_URL || "http://localhost:3000";
      const assignerName = user.name || "A PMO administrator";

      for (const assignment of assignments) {
        if (assignment.user?.email) {
          const template = projectAssignmentEmail({
            recipientName: assignment.user.name,
            projectName: fullProject!.name as string,
            projectReference: (fullProject!.reference as string) ?? "",
            role: assignment.role as never,
            projectUrl: `${baseUrl}/projects/${fullProject!.id}`,
            assignedBy: assignerName,
          });
          sendEmailAsync({
            to: assignment.user.email,
            category: "notification",
            ...template,
          });
        }
      }
    }

    const normalized = fullProject
      ? {
          ...fullProject,
          budget: fullProject.budget ? withResolvedBac(fullProject.budget as Parameters<typeof withResolvedBac>[0]) : fullProject.budget,
        }
      : fullProject;
    return NextResponse.json(normalized, { status: 201 });
  },
);
