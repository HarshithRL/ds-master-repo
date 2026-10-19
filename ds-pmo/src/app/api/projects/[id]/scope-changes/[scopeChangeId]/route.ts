import { withHandler, createAuditLog } from "@/lib/api-handler";
import { updateScopeChangeSchema, type UpdateScopeChangeInput } from "@/lib/validations";
import { RATE_LIMITS } from "@/lib/rate-limit";
import { getScopeChangeById, updateScopeChange, deleteScopeChange } from "@/lib/db/scope-changes";
import { NextResponse } from "next/server";

type Params = { id: string; scopeChangeId: string };

export const PUT = withHandler<UpdateScopeChangeInput, Params>(
  {
    projectAccess: true,
    schema: updateScopeChangeSchema,
    rateLimit: RATE_LIMITS.mutation,
  },
  async ({ user, params, body }) => {
    const scopeChange = await getScopeChangeById(params.scopeChangeId);
    if (!scopeChange || scopeChange.projectId !== params.id) {
      return NextResponse.json({ error: "Scope change not found" }, { status: 404 });
    }

    const updateData: Record<string, unknown> = {};
    if (body.description !== undefined) updateData.description = body.description;
    if (body.submittedDate !== undefined) updateData.submittedDate = body.submittedDate ? new Date(body.submittedDate) : null;
    if (body.impactCost !== undefined) updateData.impactCost = body.impactCost;
    if (body.impactSchedule !== undefined) updateData.impactSchedule = body.impactSchedule;
    if (body.impactCostValue !== undefined) updateData.impactCostValue = body.impactCostValue;
    if (body.impactScheduleValue !== undefined) updateData.impactScheduleValue = body.impactScheduleValue;
    if (body.status !== undefined) updateData.status = body.status;

    await updateScopeChange(params.scopeChangeId, updateData);

    const changes: Record<string, { old: unknown; new: unknown }> = {};
    for (const key of Object.keys(updateData)) {
      changes[key] = {
        old: (scopeChange as unknown as Record<string, unknown>)[key],
        new: updateData[key],
      };
    }

    await createAuditLog({
      userId: user.id,
      projectId: params.id,
      action: "UPDATE",
      entity: "ScopeChange",
      entityId: params.scopeChangeId,
      changes,
    });

    const updated = await getScopeChangeById(params.scopeChangeId);
    return NextResponse.json(updated);
  },
);

export const DELETE = withHandler<undefined, Params>(
  { projectAccess: true, rateLimit: RATE_LIMITS.mutation },
  async ({ user, params }) => {
    const scopeChange = await getScopeChangeById(params.scopeChangeId);
    if (!scopeChange || scopeChange.projectId !== params.id) {
      return NextResponse.json({ error: "Scope change not found" }, { status: 404 });
    }

    await deleteScopeChange(params.scopeChangeId);

    await createAuditLog({
      userId: user.id,
      projectId: params.id,
      action: "DELETE",
      entity: "ScopeChange",
      entityId: params.scopeChangeId,
      changes: { description: { old: scopeChange.description, new: null } },
    });

    return NextResponse.json({ success: true });
  },
);
