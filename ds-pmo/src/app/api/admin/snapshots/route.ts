import { withHandler, createAuditLog } from "@/lib/api-handler";
import { RATE_LIMITS } from "@/lib/rate-limit";
import { NextResponse } from "next/server";
import { parsePagination } from "@/lib/utils";
import { calcEAC, calcVariance, calcScheduleBufferDays, withResolvedBac } from "@/lib/calculations";
import { computeProgress } from "@/lib/progress";
import { listSnapshots, getSnapshot, upsertSnapshot } from "@/lib/db/snapshots";
import { listProjectRows, getProjectsByIds } from "@/lib/db/projects";
import { getBudgetsWithLinesForProjects } from "@/lib/db/budgets";
import { listGatesForProjects } from "@/lib/db/gates";
import { listRisksNarrowForProjects } from "@/lib/db/risks";
import { getUsersByIds } from "@/lib/db/users";
import type { GateRecord, Risk } from "@/lib/db/models";

export const GET = withHandler(
  { requireAdmin: true, rateLimit: RATE_LIMITS.read },
  async ({ req }) => {
    const url = req.nextUrl;
    const { page, limit, skip } = parsePagination(url.searchParams);
    const search = url.searchParams.get("search") || "";

    // NOTE: `listSnapshots` filters by search across project reference/name/
    // period only — the old route's `projectId` param went unused by the UI
    // (see src/components/admin/snapshots-admin.tsx), so it's dropped here.
    const { snapshots, total } = await listSnapshots({
      search: search || undefined,
      limit,
      offset: skip,
    });

    const userIds = [...new Set(snapshots.map((s) => s.createdById).filter((x): x is string => !!x))];
    const projectIds = [...new Set(snapshots.map((s) => s.projectId))];
    const [users, projects] = await Promise.all([
      getUsersByIds(userIds),
      getProjectsByIds(projectIds, "id, is_active"),
    ]);
    const userById = new Map(users.map((u) => [u.id, u]));
    const projectById = new Map(projects.map((p) => [p.id as string, p]));

    const enriched = snapshots.map((s) => {
      const createdBy = s.createdById ? userById.get(s.createdById) : undefined;
      const project = projectById.get(s.projectId);
      return {
        ...s,
        createdBy: createdBy ? { id: createdBy.id, name: createdBy.name, email: createdBy.email } : null,
        project: project ? { id: project.id, isActive: project.isActive } : null,
      };
    });

    return NextResponse.json({ snapshots: enriched, total, page, pageSize: limit });
  },
);

export const POST = withHandler(
  { requireAdmin: true, rateLimit: RATE_LIMITS.mutation },
  async ({ req, user }) => {
    let periodLabel = new Date().toISOString().slice(0, 7);

    try {
      const body = await req.json();
      if (body?.periodLabel && /^\d{4}-(0[1-9]|1[0-2])$/.test(body.periodLabel)) {
        periodLabel = body.periodLabel;
      }
    } catch {
      // No body or invalid JSON — use default current month
    }

    // Fetch all active projects with budget and open risks
    // Admin-only route (requireAdmin gate) generating snapshots across the
    // whole portfolio — confidential projects are included in the snapshot
    // capture itself, same as it already sees every project regardless of
    // ordinary visibility.
    const projects = await listProjectRows({
      includeInactive: false,
      visibility: { unrestricted: true },
      confidentialAccess: "ALL",
    });
    const ids = projects.map((p) => p.id);
    const [budgets, gates, risksNarrow] = await Promise.all([
      getBudgetsWithLinesForProjects(ids),
      listGatesForProjects(ids),
      listRisksNarrowForProjects(ids),
    ]);

    const gatesByProject = new Map<string, GateRecord[]>();
    for (const g of gates) {
      const list = gatesByProject.get(g.projectId) ?? [];
      list.push(g);
      gatesByProject.set(g.projectId, list);
    }

    const openRisksByProject = new Map<string, Partial<Risk>[]>();
    for (const r of risksNarrow) {
      if (r.status !== "OPEN" && r.status !== "MITIGATING") continue;
      const pid = r.projectId as string;
      const list = openRisksByProject.get(pid) ?? [];
      list.push(r);
      openRisksByProject.set(pid, list);
    }

    let created = 0;
    let updated = 0;

    for (const project of projects) {
      const risks = openRisksByProject.get(project.id) ?? [];
      const openRiskCount = risks.filter((r) => r.type === "RISK").length;
      const openIssueCount = risks.filter((r) => r.type === "ISSUE").length;
      // totalCostAtRisk / totalTimeImpact are now sourced from the editable
      // aggregate inputs on Project (RIAC-autofilled) — the risks list only
      // holds the top-5 detail rows under the centralized model.
      const totalCostAtRisk = project.totalCostAtRisk ?? 0;
      const totalTimeImpact = project.totalTimeImpact ?? 0;

      const rawBudget = budgets.get(project.id) ?? null;
      const budget = rawBudget ? withResolvedBac(rawBudget) : null;

      // Check if snapshot already exists for this period
      const existing = await getSnapshot(project.id, periodLabel);

      await upsertSnapshot({
        projectId: project.id,
        projectReference: project.reference ?? "",
        projectName: project.name,
        periodLabel,
        notes: null,
        createdById: user.id,
        currentPhase: project.currentPhase,
        progress: computeProgress(gatesByProject.get(project.id) ?? []),
        currentBAC: budget?.bac ?? null,
        eac: budget ? calcEAC(budget) : null,
        actualCost: budget?.actuals ?? null,
        committed: budget?.committed ?? null,
        riskContingencyBudgeted: budget?.riskContingencyBudgeted ?? null,
        riskContingencyConsumed: budget?.riskContingencyConsumed ?? null,
        mgmtContingencyBudgeted: budget?.mgmtContingencyBudgeted ?? null,
        mgmtContingencyConsumed: budget?.mgmtContingencyConsumed ?? null,
        varianceAtCompletion: budget ? calcVariance(budget) : null,
        scheduleBuffer: calcScheduleBufferDays(
          project.plannedCompletionDate,
          project.expectedCompletionDate,
        ),
        ragProgress: project.ragProgress,
        ragSchedule: project.ragSchedule,
        ragCost: project.ragCost,
        ragRisk: project.ragRisk,
        ragScope: project.ragScope,
        ragResources: project.ragResources,
        ragProgressLabel: project.ragProgressLabel,
        ragScheduleLabel: project.ragScheduleLabel,
        ragCostLabel: project.ragCostLabel,
        ragRiskLabel: project.ragRiskLabel,
        ragScopeLabel: project.ragScopeLabel,
        ragResourcesLabel: project.ragResourcesLabel,
        ridsOpen: project.ridsOpen,
        redFlagsOpen: project.redFlagsOpen,
        totalFloatExclBuffer: project.totalFloatExclBuffer,
        totalFloatInclBuffer: project.totalFloatInclBuffer,
        resourceConsumptionPct: project.resourceConsumptionPct,
        openRiskCount,
        openIssueCount,
        totalCostAtRisk,
        totalTimeImpact,
        plannedCompletionDate: project.plannedCompletionDate,
        expectedCompletionDate: project.expectedCompletionDate,
      });

      if (existing) {
        updated++;
      } else {
        created++;
      }
    }

    await createAuditLog({
      userId: user.id,
      projectId: undefined,
      action: "CREATE",
      entity: "ProjectSnapshot",
      entityId: undefined,
      changes: {
        periodLabel: { old: null, new: periodLabel },
        projectCount: { old: null, new: projects.length },
      },
    });

    return NextResponse.json({
      periodLabel,
      total: projects.length,
      created,
      updated,
    }, { status: 201 });
  },
);
