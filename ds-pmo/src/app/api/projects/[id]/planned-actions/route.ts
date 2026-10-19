import { withHandler, createAuditLog } from "@/lib/api-handler";
import {
  createPlannedActionSchema,
  type CreatePlannedActionInput,
} from "@/lib/validations";
import { RATE_LIMITS } from "@/lib/rate-limit";
import { getProjectBasic } from "@/lib/db/projects";
import { listPlannedActionsForProject, createPlannedAction } from "@/lib/db/planned-actions";
import { NextResponse } from "next/server";

export const GET = withHandler<undefined, { id: string }>(
  { projectAccess: true, rateLimit: RATE_LIMITS.read },
  async ({ params }) => {
    const actions = await listPlannedActionsForProject(params.id);
    // list is already ordered by sortOrder ASC; break ties by createdAt ASC
    const sorted = [...actions].sort((a, b) => {
      if (a.sortOrder !== b.sortOrder) return a.sortOrder - b.sortOrder;
      return a.createdAt.getTime() - b.createdAt.getTime();
    });
    return NextResponse.json(sorted);
  },
);

export const POST = withHandler<CreatePlannedActionInput, { id: string }>(
  {
    projectAccess: true,
    schema: createPlannedActionSchema,
    rateLimit: RATE_LIMITS.mutation,
  },
  async ({ user, params, body }) => {
    const project = await getProjectBasic(params.id);
    if (!project) {
      return NextResponse.json({ error: "Project not found" }, { status: 404 });
    }

    const existing = await listPlannedActionsForProject(params.id);
    const last = existing.reduce<{ sortOrder: number } | null>((max, a) => {
      return !max || a.sortOrder > max.sortOrder ? a : max;
    }, null);

    const created = await createPlannedAction({
      projectId: params.id,
      action: body.action,
      ownerLabel: body.ownerLabel ?? null,
      byDate: body.byDate ? new Date(body.byDate) : null,
      status: body.status,
      notes: body.notes ?? null,
      sortOrder: body.sortOrder ?? (last ? last.sortOrder + 1 : 0),
    });

    await createAuditLog({
      userId: user.id,
      projectId: params.id,
      action: "CREATE",
      entity: "PlannedAction",
      entityId: created.id,
      changes: {
        action: { old: null, new: body.action },
        status: { old: null, new: body.status },
      },
    });

    return NextResponse.json(created, { status: 201 });
  },
);
