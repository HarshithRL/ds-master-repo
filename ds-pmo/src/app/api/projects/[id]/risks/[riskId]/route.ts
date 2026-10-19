import { withHandler, createAuditLog } from "@/lib/api-handler";
import { updateRiskSchema, type UpdateRiskInput } from "@/lib/validations";
import { RATE_LIMITS } from "@/lib/rate-limit";
import { getRiskById, updateRisk, deleteRisk } from "@/lib/db/risks";
import { NextResponse } from "next/server";

type Params = { id: string; riskId: string };

export const PUT = withHandler<UpdateRiskInput, Params>(
  {
    projectAccess: true,
    schema: updateRiskSchema,
    rateLimit: RATE_LIMITS.mutation,
  },
  async ({ user, params, body }) => {
    const risk = await getRiskById(params.riskId);
    if (!risk || risk.projectId !== params.id) {
      return NextResponse.json({ error: "Risk not found" }, { status: 404 });
    }

    const updateData: Record<string, unknown> = {};
    if (body.riskStatement !== undefined) updateData.riskStatement = body.riskStatement;
    if (body.ifClause !== undefined) updateData.ifClause = body.ifClause;
    if (body.dueToClause !== undefined) updateData.dueToClause = body.dueToClause;
    if (body.thenClause !== undefined) updateData.thenClause = body.thenClause;
    if (body.type !== undefined) updateData.type = body.type;
    if (body.impact !== undefined) updateData.impact = body.impact;
    if (body.category !== undefined) updateData.category = body.category;
    if (body.probability !== undefined) updateData.probability = body.probability;
    if (body.costImpact !== undefined) updateData.costImpact = body.costImpact;
    if (body.timeImpact !== undefined) updateData.timeImpact = body.timeImpact;
    if (body.weight !== undefined) updateData.weight = body.weight;
    if (body.counterMeasures !== undefined) updateData.counterMeasures = body.counterMeasures;
    if (body.responseStrategy !== undefined) updateData.responseStrategy = body.responseStrategy;
    if (body.completionDate !== undefined)
      updateData.completionDate = body.completionDate ? new Date(body.completionDate) : null;
    if (body.ownerName !== undefined) updateData.ownerName = body.ownerName;
    if (body.status !== undefined) updateData.status = body.status;
    if (body.comments !== undefined) updateData.comments = body.comments;

    await updateRisk(params.riskId, updateData);
    const updated = await getRiskById(params.riskId);

    const changes: Record<string, { old: unknown; new: unknown }> = {};
    for (const key of Object.keys(updateData)) {
      changes[key] = {
        old: (risk as unknown as Record<string, unknown>)[key],
        new: updateData[key],
      };
    }

    await createAuditLog({
      userId: user.id,
      projectId: params.id,
      action: "UPDATE",
      entity: "Risk",
      entityId: params.riskId,
      changes,
    });

    return NextResponse.json(updated);
  },
);

export const DELETE = withHandler<undefined, Params>(
  { projectAccess: true, rateLimit: RATE_LIMITS.mutation },
  async ({ user, params }) => {
    const risk = await getRiskById(params.riskId);
    if (!risk || risk.projectId !== params.id) {
      return NextResponse.json({ error: "Risk not found" }, { status: 404 });
    }

    await deleteRisk(params.riskId);

    await createAuditLog({
      userId: user.id,
      projectId: params.id,
      action: "DELETE",
      entity: "Risk",
      entityId: params.riskId,
      changes: { riskStatement: { old: risk.riskStatement, new: null } },
    });

    return NextResponse.json({ success: true });
  },
);
