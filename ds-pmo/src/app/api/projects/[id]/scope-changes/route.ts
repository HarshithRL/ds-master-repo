import { withHandler, createAuditLog } from "@/lib/api-handler";
import { createScopeChangeSchema, type CreateScopeChangeInput } from "@/lib/validations";
import { RATE_LIMITS } from "@/lib/rate-limit";
import { getProjectBasic } from "@/lib/db/projects";
import { listScopeChangesForProject, createScopeChange } from "@/lib/db/scope-changes";
import { NextResponse } from "next/server";

export const GET = withHandler<undefined, { id: string }>(
  { projectAccess: true, rateLimit: RATE_LIMITS.read },
  async ({ params }) => {
    const project = await getProjectBasic(params.id);
    if (!project) {
      return NextResponse.json({ error: "Project not found" }, { status: 404 });
    }

    const scopeChanges = await listScopeChangesForProject(params.id);
    const sorted = [...scopeChanges].sort((a, b) => b.createdAt.getTime() - a.createdAt.getTime());
    return NextResponse.json(sorted);
  },
);

export const POST = withHandler<CreateScopeChangeInput, { id: string }>(
  {
    projectAccess: true,
    schema: createScopeChangeSchema,
    rateLimit: RATE_LIMITS.mutation,
  },
  async ({ user, params, body }) => {
    const project = await getProjectBasic(params.id);
    if (!project) {
      return NextResponse.json({ error: "Project not found" }, { status: 404 });
    }

    const scopeChange = await createScopeChange({
      projectId: params.id,
      description: body.description,
      submittedDate: body.submittedDate ? new Date(body.submittedDate) : null,
      impactCost: body.impactCost || null,
      impactSchedule: body.impactSchedule || null,
      impactCostValue: body.impactCostValue ?? null,
      impactScheduleValue: body.impactScheduleValue ?? null,
      status: body.status,
    });

    await createAuditLog({
      userId: user.id,
      projectId: params.id,
      action: "CREATE",
      entity: "ScopeChange",
      entityId: scopeChange.id,
      changes: {
        description: { old: null, new: body.description },
        status: { old: null, new: body.status },
      },
    });

    return NextResponse.json(scopeChange, { status: 201 });
  },
);
