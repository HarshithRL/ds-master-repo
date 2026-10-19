import { withHandler, createAuditLog } from "@/lib/api-handler";
import {
  createMilestoneSchema,
  reorderMilestonesSchema,
  type CreateMilestoneInput,
  type ReorderMilestonesInput,
} from "@/lib/validations";
import { RATE_LIMITS } from "@/lib/rate-limit";
import { getProjectBasic } from "@/lib/db/projects";
import { listMilestonesForProject, createMilestone, updateMilestone, getMilestoneById } from "@/lib/db/milestones";
import { NextResponse } from "next/server";

export const GET = withHandler<undefined, { id: string }>(
  { projectAccess: true, rateLimit: RATE_LIMITS.read },
  async ({ params }) => {
    const project = await getProjectBasic(params.id);
    if (!project) {
      return NextResponse.json({ error: "Project not found" }, { status: 404 });
    }

    const milestones = await listMilestonesForProject(params.id);
    return NextResponse.json(milestones);
  },
);

export const POST = withHandler<CreateMilestoneInput, { id: string }>(
  {
    projectAccess: true,
    schema: createMilestoneSchema,
    rateLimit: RATE_LIMITS.mutation,
  },
  async ({ user, params, body }) => {
    const project = await getProjectBasic(params.id);
    if (!project) {
      return NextResponse.json({ error: "Project not found" }, { status: 404 });
    }

    const existing = await listMilestonesForProject(params.id);
    const last = existing.reduce<{ sortOrder: number } | null>((max, m) => {
      return !max || m.sortOrder > max.sortOrder ? m : max;
    }, null);

    const milestone = await createMilestone({
      projectId: params.id,
      name: body.name,
      targetDate: body.targetDate ? new Date(body.targetDate) : undefined,
      expectedDate: body.expectedDate ? new Date(body.expectedDate) : undefined,
      sortOrder: (last?.sortOrder || 0) + 1,
    });

    await createAuditLog({
      userId: user.id,
      projectId: params.id,
      action: "CREATE",
      entity: "Milestone",
      entityId: milestone.id,
      changes: {
        name: { old: null, new: body.name },
        targetDate: { old: null, new: body.targetDate },
      },
    });

    return NextResponse.json(milestone, { status: 201 });
  },
);

// PUT = reorder milestones
export const PUT = withHandler<ReorderMilestonesInput, { id: string }>(
  {
    projectAccess: true,
    schema: reorderMilestonesSchema,
    rateLimit: RATE_LIMITS.mutation,
  },
  async ({ user, params, body }) => {
    const project = await getProjectBasic(params.id);
    if (!project) {
      return NextResponse.json({ error: "Project not found" }, { status: 404 });
    }

    const updated = [];
    for (let i = 0; i < body.milestones.length; i++) {
      const id = body.milestones[i].id;
      await updateMilestone(id, { sortOrder: i + 1 });
      const m = await getMilestoneById(id);
      updated.push(m);
    }

    await createAuditLog({
      userId: user.id,
      projectId: params.id,
      action: "UPDATE",
      entity: "Milestone",
      entityId: params.id,
      changes: { reordered: { old: null, new: true } },
    });

    return NextResponse.json(updated);
  },
);
