import { withHandler, createAuditLog } from "@/lib/api-handler";
import {
  updatePlannedActionSchema,
  type UpdatePlannedActionInput,
} from "@/lib/validations";
import { RATE_LIMITS } from "@/lib/rate-limit";
import { getPlannedActionById, updatePlannedAction, deletePlannedAction } from "@/lib/db/planned-actions";
import { NextResponse } from "next/server";

type Params = { id: string; actionId: string };

export const PUT = withHandler<UpdatePlannedActionInput, Params>(
  {
    projectAccess: true,
    schema: updatePlannedActionSchema,
    rateLimit: RATE_LIMITS.mutation,
  },
  async ({ user, params, body }) => {
    const existing = await getPlannedActionById(params.actionId);
    if (!existing || existing.projectId !== params.id) {
      return NextResponse.json({ error: "Planned action not found" }, { status: 404 });
    }

    const updateData: Record<string, unknown> = {};
    if (body.action !== undefined) updateData.action = body.action;
    if (body.ownerLabel !== undefined) updateData.ownerLabel = body.ownerLabel;
    if (body.byDate !== undefined) updateData.byDate = body.byDate ? new Date(body.byDate) : null;
    if (body.status !== undefined) updateData.status = body.status;
    if (body.notes !== undefined) updateData.notes = body.notes;
    if (body.sortOrder !== undefined) updateData.sortOrder = body.sortOrder;

    await updatePlannedAction(params.actionId, updateData);

    const changes: Record<string, { old: unknown; new: unknown }> = {};
    for (const key of Object.keys(updateData)) {
      changes[key] = {
        old: (existing as unknown as Record<string, unknown>)[key],
        new: updateData[key],
      };
    }

    await createAuditLog({
      userId: user.id,
      projectId: params.id,
      action: "UPDATE",
      entity: "PlannedAction",
      entityId: params.actionId,
      changes,
    });

    const updated = await getPlannedActionById(params.actionId);
    return NextResponse.json(updated);
  },
);

export const DELETE = withHandler<undefined, Params>(
  { projectAccess: true, rateLimit: RATE_LIMITS.mutation },
  async ({ user, params }) => {
    const existing = await getPlannedActionById(params.actionId);
    if (!existing || existing.projectId !== params.id) {
      return NextResponse.json({ error: "Planned action not found" }, { status: 404 });
    }

    await deletePlannedAction(params.actionId);

    await createAuditLog({
      userId: user.id,
      projectId: params.id,
      action: "DELETE",
      entity: "PlannedAction",
      entityId: params.actionId,
      changes: { action: { old: existing.action, new: null } },
    });

    return NextResponse.json({ success: true });
  },
);
