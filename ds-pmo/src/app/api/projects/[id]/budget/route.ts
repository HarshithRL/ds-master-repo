import { withHandler, createAuditLog } from "@/lib/api-handler";
import { updateBudgetSchema, type UpdateBudgetInput } from "@/lib/validations";
import { RATE_LIMITS } from "@/lib/rate-limit";
import { withResolvedBac } from "@/lib/calculations";
import { getBudgetForProject, createBudgetForProject, upsertBudget, getBudgetWithLinesForProject } from "@/lib/db/budgets";
import { NextResponse } from "next/server";

export const PUT = withHandler<UpdateBudgetInput, { id: string }>(
  {
    projectAccess: true,
    schema: updateBudgetSchema,
    rateLimit: RATE_LIMITS.mutation,
  },
  async ({ user, params, body }) => {
    // Auto-create budget if it doesn't exist (legacy/seeded projects may lack one)
    const budget = (await getBudgetForProject(params.id)) ?? (await createBudgetForProject(params.id));

    // Build update data from validated body. EAC and project VAC are
    // derived live via calcEAC / calcVariance — no denormalized fields.
    const updateData: Record<string, number> = {};
    for (const [key, val] of Object.entries(body)) {
      if (val !== undefined) updateData[key] = val;
    }

    await upsertBudget(params.id, updateData);
    const updated = await getBudgetWithLinesForProject(params.id);

    // Fire-and-forget audit log — don't block the response
    createAuditLog({
      userId: user.id,
      projectId: params.id,
      action: "UPDATE",
      entity: "Budget",
      entityId: budget.id,
      changes: Object.fromEntries(
        Object.keys(updateData).map((k) => [
          k,
          { old: (budget as unknown as Record<string, unknown>)[k], new: updateData[k] },
        ]),
      ),
    }).catch(() => {});

    return NextResponse.json(withResolvedBac(updated!));
  },
);
