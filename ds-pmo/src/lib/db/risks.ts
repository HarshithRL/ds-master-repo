import { selectRows, selectOne, insertRow, insertRows, updateRow, deleteRows, findByIds, readBackWithRetry } from "./query-builder";
import { fromRow, toRow } from "./rowmap";
import type { Risk } from "./models";

const TABLE = "risks";

function map(row: Record<string, unknown>): Risk {
  return fromRow<Risk>(row);
}

const NARROW_COLUMNS = "id, project_id, type, impact, probability, cost_impact, time_impact, status, weight";

export async function listRisksForProject(projectId: string): Promise<Risk[]> {
  const rows = await selectRows<Record<string, unknown>>(TABLE, {
    where: [{ type: "eq", column: "project_id", value: projectId }],
  });
  return rows.map(map);
}

/** Narrow projection used by list-view risk-summary aggregation (matches Prisma's `select`). */
export async function listRisksNarrowForProjects(projectIds: string[]): Promise<Partial<Risk>[]> {
  return (await findByIds<Record<string, unknown>>(TABLE, "project_id", projectIds, { columns: NARROW_COLUMNS })).map(
    (r) => fromRow<Partial<Risk>>(r),
  );
}

export async function getRiskById(id: string): Promise<Risk | null> {
  const row = await selectOne<Record<string, unknown>>(TABLE, { where: [{ type: "eq", column: "id", value: id }] });
  return row ? map(row) : null;
}

export async function countClosedRisksForProjects(projectIds: string[]): Promise<Map<string, number>> {
  const rows = await findByIds<{ project_id: string; status: string }>(TABLE, "project_id", projectIds, {
    columns: "project_id, status",
  });
  const counts = new Map<string, number>();
  for (const r of rows) {
    if (r.status === "CLOSED") counts.set(r.project_id, (counts.get(r.project_id) ?? 0) + 1);
  }
  return counts;
}

export interface RiskInput {
  projectId: string;
  riskNumber?: number | null;
  type?: Risk["type"];
  riskStatement: string;
  ifClause?: string | null;
  dueToClause?: string | null;
  thenClause?: string | null;
  impact?: Risk["impact"];
  category?: string | null;
  probability?: number | null;
  costImpact?: number | null;
  timeImpact?: number | null;
  weight?: number | null;
  counterMeasures?: string | null;
  responseStrategy?: string | null;
  completionDate?: Date | null;
  ownerName?: string | null;
  status?: Risk["status"];
  comments?: string | null;
}

export async function createRisk(input: RiskInput): Promise<Risk> {
  const now = new Date();
  const id = await insertRow(
    TABLE,
    toRow({
      type: "RISK",
      impact: "MODERATE",
      status: "OPEN",
      ...input,
      createdAt: now,
      updatedAt: now,
    }),
  );
  return readBackWithRetry(() => getRiskById(id), "Failed to read back created risk");
}

export async function updateRisk(id: string, fields: Partial<RiskInput>): Promise<void> {
  await updateRow(TABLE, id, toRow({ ...fields, updatedAt: new Date() }));
}

export async function deleteRisk(id: string): Promise<void> {
  await deleteRows(TABLE, [{ type: "eq", column: "id", value: id }]);
}

export async function deleteRisksForProject(projectId: string): Promise<void> {
  await deleteRows(TABLE, [{ type: "eq", column: "project_id", value: projectId }]);
}

export async function createRisksBatch(risks: RiskInput[]): Promise<void> {
  const now = new Date();
  await insertRows(
    TABLE,
    risks.map((r) => toRow({ type: "RISK", impact: "MODERATE", status: "OPEN", ...r, createdAt: now, updatedAt: now })),
  );
}
