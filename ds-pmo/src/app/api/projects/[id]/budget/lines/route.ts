import { withHandler, createAuditLog } from "@/lib/api-handler";
import { upsertBudgetLineSchema, type UpsertBudgetLineInput } from "@/lib/validations";
import { RATE_LIMITS } from "@/lib/rate-limit";
import { calcBAC } from "@/lib/calculations";
import {
  getBudgetForProject,
  createBudgetForProject,
  getBudgetLinesForBudget,
  upsertBudgetLine,
  upsertBudget,
} from "@/lib/db/budgets";
import { NextResponse } from "next/server";

export const GET = withHandler(
  { projectAccess: true, rateLimit: RATE_LIMITS.read },
  async ({ params }) => {
    // Auto-create budget if missing (legacy/seeded projects)
    const budget = (await getBudgetForProject(params.id)) ?? (await createBudgetForProject(params.id));
    const lines = await getBudgetLinesForBudget(budget.id);
    lines.sort((a, b) => (a.type === b.type ? a.year - b.year : a.type.localeCompare(b.type)));
    return NextResponse.json(lines);
  },
);

export const PUT = withHandler<UpsertBudgetLineInput, { id: string }>(
  {
    projectAccess: true,
    schema: upsertBudgetLineSchema,
    rateLimit: RATE_LIMITS.mutation,
  },
  async ({ user, params, body }) => {
    // Auto-create budget if missing (legacy/seeded projects)
    const budget = (await getBudgetForProject(params.id)) ?? (await createBudgetForProject(params.id));

    // Upsert the line
    await upsertBudgetLine(budget.id, body.type, body.year, body.amount);

    // Recompute denormalized BAC
    const allLines = await getBudgetLinesForBudget(budget.id);
    const bac = calcBAC(allLines);
    await upsertBudget(params.id, { bac });

    const line = allLines.find((l) => l.type === body.type && l.year === body.year)!;

    // Fire-and-forget audit log — don't block the response
    createAuditLog({
      userId: user.id,
      projectId: params.id,
      action: "UPDATE",
      entity: "BudgetLine",
      entityId: line.id,
      changes: {
        type: { old: null, new: body.type },
        year: { old: null, new: body.year },
        amount: { old: null, new: body.amount },
        bac: { old: budget.bac, new: bac },
      },
    }).catch(() => {});

    return NextResponse.json({ line, bac });
  },
);
