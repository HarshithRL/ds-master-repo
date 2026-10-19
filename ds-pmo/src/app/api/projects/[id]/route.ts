import { withHandler, createAuditLog, diffObjects, applyPartial } from "@/lib/api-handler";
import { updateProjectSchema, type UpdateProjectInput } from "@/lib/validations";
import { withResolvedBac } from "@/lib/calculations";
import { withDerivedProjectFields, type ProjectShape } from "@/lib/project-derive";
import {
  canViewProject,
  canEditProject,
  whyCantViewProject,
} from "@/lib/access-control";
import { RATE_LIMITS } from "@/lib/rate-limit";
import { buildRiskSummary, fetchClosedRiskCount } from "@/lib/risk-summary";
import { sanitizeRichText } from "@/lib/sanitize-html";
import {
  getProjectRaw,
  getProjectFull,
  getProjectWithDeleteRelations,
  updateProjectRow,
} from "@/lib/db/projects";
import { replaceAssignmentsForProject, listAssignmentsForProject } from "@/lib/db/assignments";
import { getUsersByIds } from "@/lib/db/users";
import { NextResponse } from "next/server";

export const GET = withHandler<undefined, { id: string }>(
  // View-level gate (wider than edit) — executives, sponsors, owners, and
  // users with a Division/Factory scope grant can read the one-pager without
  // being able to edit it. The `canEdit` flag in the response drives the UI.
  { rateLimit: RATE_LIMITS.read },
  async ({ user, params }) => {
    const canView = await canViewProject(user, params.id);
    if (!canView) {
      const reason = await whyCantViewProject(user, params.id);
      return NextResponse.json({ error: "Forbidden", reason }, { status: 403 });
    }

    const project = await getProjectFull(params.id);
    if (!project) {
      return NextResponse.json({ error: "Project not found" }, { status: 404 });
    }

    // Note: legacy projects without a Budget row return budget=null here.
    // The UI handles null (BudgetTab props accept Budget | null), and the
    // budget PUT endpoint upserts on first edit. GET must stay read-only —
    // mutating on a read also masked a race condition under concurrent loads.

    const [closedCount, canEdit] = await Promise.all([
      fetchClosedRiskCount(params.id),
      canEditProject(user, params.id),
    ]);
    const projectWithBac: Record<string, unknown> = {
      ...project,
      budget: project.budget ? withResolvedBac(project.budget as Parameters<typeof withResolvedBac>[0]) : project.budget,
    };
    const normalized = withDerivedProjectFields(projectWithBac as unknown as ProjectShape & Record<string, unknown>);
    return NextResponse.json({
      ...normalized,
      riskSummary: buildRiskSummary(project as Parameters<typeof buildRiskSummary>[0], closedCount),
      canEdit,
    });
  },
);

export const PUT = withHandler<UpdateProjectInput, { id: string }>(
  {
    projectAccess: true,
    schema: updateProjectSchema,
    rateLimit: RATE_LIMITS.mutation,
  },
  async ({ user, params, body }) => {
    const project = await getProjectRaw(params.id);
    if (!project) {
      return NextResponse.json({ error: "Project not found" }, { status: 404 });
    }

    // Most fields are simple "if defined → copy" passthroughs. List them once
    // and apply in a single sweep; fields needing transformation handled below.
    const SCALAR_FIELDS = [
      // Identity / text
      "reference", "name", "description", "objective", "scope", "scopeExclusions",
      // Classification
      "tier", "lifecycleType", "status",
      // Current state
      "currentPhase", "currentGate",
      // Flags
      "isActive", "flags", "isConfidential",
      // RAG indicators
      "ragProgress", "ragSchedule", "ragCost", "ragRisk", "ragScope", "ragResources",
      // Free-text status labels
      "ragProgressLabel", "ragScheduleLabel", "ragCostLabel",
      "ragRiskLabel", "ragScopeLabel", "ragResourcesLabel",
      // Schedule performance inputs (Prev fields removed — derived from snapshots)
      "totalFloatExclBuffer", "totalFloatInclBuffer", "resourceConsumptionPct",
      // Schedule maturity KPIs
      "ridsOpen", "redFlagsOpen",
      // Business case
      "totalCost", "expectedValue", "roi", "paybackYears",
      // Risk summary inputs (decoupled from Risk table — editable + autofilled by RIAC)
      "risksIssuesCount", "risksHighCount", "risksModerateCount", "risksLowCount",
      "risksIdentifiedCount", "risksQuantifiedCount",
      "totalCostAtRisk", "totalTimeImpact",
      // Document links (fixed)
      "scheduleDocUrl", "costDocUrl", "riacDocUrl",
      // SAP WBS codes
      "wbsCodes",
    ] as const;
    const updateData: Record<string, unknown> = {
      lastUpdatedById: user.id,
    };
    applyPartial(updateData, body, SCALAR_FIELDS);

    // Relations: plain FK columns now (no Prisma connect/disconnect)
    if (body.factoryId !== undefined) updateData.factoryId = body.factoryId || null;
    if (body.categoryId !== undefined) updateData.categoryId = body.categoryId || null;

    // Dates: parse from ISO string when present, preserve explicit null
    if (body.actualStartDate !== undefined) {
      updateData.actualStartDate = body.actualStartDate ? new Date(body.actualStartDate) : null;
    }
    if (body.plannedCompletionDate !== undefined) {
      updateData.plannedCompletionDate = body.plannedCompletionDate
        ? new Date(body.plannedCompletionDate)
        : null;
    }
    if (body.expectedCompletionDate !== undefined) {
      updateData.expectedCompletionDate = body.expectedCompletionDate
        ? new Date(body.expectedCompletionDate)
        : null;
    }

    // Rich text: must run through the server-side HTML sanitiser
    if (body.keyAchievements !== undefined) {
      updateData.keyAchievements =
        body.keyAchievements === null ? null : sanitizeRichText(body.keyAchievements);
    }

    if (body.assignments !== undefined) {
      await replaceAssignmentsForProject(params.id, body.assignments);
    }

    await updateProjectRow(params.id, updateData);

    // Run audit log in the background — don't block the response
    const diff = diffObjects(project as unknown as Record<string, unknown>, updateData);
    createAuditLog({
      userId: user.id,
      projectId: params.id,
      action: "UPDATE",
      entity: "Project",
      entityId: params.id,
      changes: diff || {},
    }).catch(() => {}); // fire-and-forget

    // Only use full data when assignments are being updated (patchPeople needs the response).
    // For simple field patches, use a lightweight response to avoid loading all relations.
    if (body.assignments !== undefined) {
      const full = await getProjectFull(params.id);
      const closedCount = await fetchClosedRiskCount(params.id);
      return NextResponse.json({
        ...full,
        budget: full?.budget ? withResolvedBac(full.budget as Parameters<typeof withResolvedBac>[0]) : (full?.budget ?? null),
        riskSummary: buildRiskSummary(full as Parameters<typeof buildRiskSummary>[0], closedCount),
      });
    }

    const assignments = await listAssignmentsForProject(params.id);
    const users = await getUsersByIds(assignments.map((a) => a.userId));
    const usersById = new Map(users.map((u) => [u.id, u]));
    const updated = await getProjectRaw(params.id);
    return NextResponse.json({
      ...updated,
      assignments: assignments.map((a) => ({ ...a, user: usersById.get(a.userId) ?? null })),
    });
  },
);

export const DELETE = withHandler<undefined, { id: string }>(
  { projectAccess: true, rateLimit: RATE_LIMITS.mutation },
  async ({ user, params }) => {
    const project = await getProjectRaw(params.id);
    if (!project) {
      return NextResponse.json({ error: "Project not found" }, { status: 404 });
    }

    await updateProjectRow(params.id, { isActive: false });
    const updated = await getProjectWithDeleteRelations(params.id);

    await createAuditLog({
      userId: user.id,
      projectId: params.id,
      action: "UPDATE",
      entity: "Project",
      entityId: params.id,
      changes: { isActive: { old: project.isActive, new: false } },
    });

    return NextResponse.json({
      ...updated,
      budget: updated?.budget ? withResolvedBac(updated.budget as Parameters<typeof withResolvedBac>[0]) : updated?.budget,
    });
  },
);
