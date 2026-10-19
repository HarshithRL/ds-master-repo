import { selectRows, selectOne, upsertRow, findByIds, readBackWithRetry } from "./query-builder";
import { fromRow, toRow } from "./rowmap";
import { attachMany } from "./include";
import type { Budget, BudgetLine } from "./models";

const BUDGET_TABLE = "budgets";
const LINE_TABLE = "budget_lines";

function mapBudget(row: Record<string, unknown>): Budget {
  return fromRow<Budget>(row);
}
function mapLine(row: Record<string, unknown>): BudgetLine {
  return fromRow<BudgetLine>(row);
}

export async function getBudgetForProject(projectId: string): Promise<Budget | null> {
  const row = await selectOne<Record<string, unknown>>(BUDGET_TABLE, {
    where: [{ type: "eq", column: "project_id", value: projectId }],
  });
  return row ? mapBudget(row) : null;
}

export async function getBudgetLinesForBudget(budgetId: string): Promise<BudgetLine[]> {
  const rows = await selectRows<Record<string, unknown>>(LINE_TABLE, {
    where: [{ type: "eq", column: "budget_id", value: budgetId }],
  });
  return rows.map(mapLine);
}

/** Budget + its lines for a single project, mirroring Prisma's `budget: { include: { lines: true } }`. */
export async function getBudgetWithLinesForProject(projectId: string): Promise<(Budget & { lines: BudgetLine[] }) | null> {
  const budget = await getBudgetForProject(projectId);
  if (!budget) return null;
  const lines = await getBudgetLinesForBudget(budget.id);
  return { ...budget, lines };
}

/** Batched: budgets (+lines) for many projects at once — avoids N+1 on list views. */
export async function getBudgetsWithLinesForProjects(
  projectIds: string[],
): Promise<Map<string, Budget & { lines: BudgetLine[] }>> {
  const budgets = (await findByIds<Record<string, unknown>>(BUDGET_TABLE, "project_id", projectIds)).map(mapBudget);
  const lines = await findByIds<Record<string, unknown>>(LINE_TABLE, "budget_id", budgets.map((b) => b.id));
  const withLines = attachMany(budgets, lines.map(mapLine), (l) => l.budgetId, "lines");
  return new Map(withLines.map((b) => [b.projectId, b]));
}

export async function createBudgetForProject(projectId: string): Promise<Budget> {
  await upsertRow(
    BUDGET_TABLE,
    ["project_id"],
    toRow({
      projectId,
      bac: 0,
      actuals: 0,
      committed: 0,
      expected: 0,
      riskContingencyBudgeted: 0,
      riskContingencyConsumed: 0,
      mgmtContingencyBudgeted: 0,
      mgmtContingencyConsumed: 0,
      createdAt: new Date(),
      updatedAt: new Date(),
    }),
  );
  return readBackWithRetry(() => getBudgetForProject(projectId), "Failed to read back created budget");
}

export interface UpsertBudgetFields {
  bac?: number;
  actuals?: number;
  committed?: number;
  expected?: number;
  riskContingencyBudgeted?: number;
  riskContingencyConsumed?: number;
  mgmtContingencyBudgeted?: number;
  mgmtContingencyConsumed?: number;
}

export async function upsertBudget(projectId: string, fields: UpsertBudgetFields): Promise<void> {
  const existing = await getBudgetForProject(projectId);
  await upsertRow(
    BUDGET_TABLE,
    ["project_id"],
    toRow({
      id: existing?.id,
      projectId,
      bac: fields.bac ?? existing?.bac ?? 0,
      actuals: fields.actuals ?? existing?.actuals ?? 0,
      committed: fields.committed ?? existing?.committed ?? 0,
      expected: fields.expected ?? existing?.expected ?? 0,
      riskContingencyBudgeted: fields.riskContingencyBudgeted ?? existing?.riskContingencyBudgeted ?? 0,
      riskContingencyConsumed: fields.riskContingencyConsumed ?? existing?.riskContingencyConsumed ?? 0,
      mgmtContingencyBudgeted: fields.mgmtContingencyBudgeted ?? existing?.mgmtContingencyBudgeted ?? 0,
      mgmtContingencyConsumed: fields.mgmtContingencyConsumed ?? existing?.mgmtContingencyConsumed ?? 0,
      createdAt: existing?.createdAt ?? new Date(),
      updatedAt: new Date(),
    }),
  );
}

export async function upsertBudgetLine(budgetId: string, type: "CAPEX" | "OPEX", year: number, amount: number): Promise<void> {
  await upsertRow(LINE_TABLE, ["budget_id", "type", "year"], toRow({ budgetId, type, year, amount }));
}
