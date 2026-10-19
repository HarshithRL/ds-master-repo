import { withHandler, createAuditLog } from "@/lib/api-handler";
import { updateMilestoneSchema, type UpdateMilestoneInput } from "@/lib/validations";
import { RATE_LIMITS } from "@/lib/rate-limit";
import { getMilestoneById, updateMilestone, deleteMilestone } from "@/lib/db/milestones";
import { NextResponse } from "next/server";

type Params = { id: string; milestoneId: string };

export const PUT = withHandler<UpdateMilestoneInput, Params>(
  {
    projectAccess: true,
    schema: updateMilestoneSchema,
    rateLimit: RATE_LIMITS.mutation,
  },
  async ({ user, params, body }) => {
    const milestone = await getMilestoneById(params.milestoneId);
    if (!milestone || milestone.projectId !== params.id) {
      return NextResponse.json({ error: "Milestone not found" }, { status: 404 });
    }

    const updateData: Record<string, unknown> = {};
    if (body.name !== undefined) updateData.name = body.name;
    if (body.remarks !== undefined) updateData.remarks = body.remarks;
    if (body.targetDate !== undefined)
      updateData.targetDate = body.targetDate ? new Date(body.targetDate) : null;
    if (body.expectedDate !== undefined)
      updateData.expectedDate = body.expectedDate ? new Date(body.expectedDate) : null;
    if (body.sortOrder !== undefined) updateData.sortOrder = body.sortOrder;

    await updateMilestone(params.milestoneId, updateData);

    const changes: Record<string, { old: unknown; new: unknown }> = {};
    for (const key of Object.keys(updateData)) {
      changes[key] = {
        old: (milestone as unknown as Record<string, unknown>)[key],
        new: updateData[key],
      };
    }

    await createAuditLog({
      userId: user.id,
      projectId: params.id,
      action: "UPDATE",
      entity: "Milestone",
      entityId: params.milestoneId,
      changes,
    });

    const updated = await getMilestoneById(params.milestoneId);
    return NextResponse.json(updated);
  },
);

export const DELETE = withHandler<undefined, Params>(
  { projectAccess: true, rateLimit: RATE_LIMITS.mutation },
  async ({ user, params }) => {
    const milestone = await getMilestoneById(params.milestoneId);
    if (!milestone || milestone.projectId !== params.id) {
      return NextResponse.json({ error: "Milestone not found" }, { status: 404 });
    }

    await deleteMilestone(params.milestoneId);

    await createAuditLog({
      userId: user.id,
      projectId: params.id,
      action: "DELETE",
      entity: "Milestone",
      entityId: params.milestoneId,
      changes: { name: { old: milestone.name, new: null } },
    });

    return NextResponse.json({ success: true });
  },
);
