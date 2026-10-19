import { selectRows, selectOne, insertRow, updateRow, deleteRows, findByIds, readBackWithRetry } from "./query-builder";
import { fromRow, toRow } from "./rowmap";
import type { ScopeChange } from "./models";

const TABLE = "scope_changes";

function map(row: Record<string, unknown>): ScopeChange {
  return fromRow<ScopeChange>(row);
}

const NARROW_COLUMNS = "id, project_id, status, impact_cost_value, impact_schedule_value";

export async function listScopeChangesForProject(projectId: string): Promise<ScopeChange[]> {
  const rows = await selectRows<Record<string, unknown>>(TABLE, {
    where: [{ type: "eq", column: "project_id", value: projectId }],
  });
  return rows.map(map);
}

export async function listScopeChangesNarrowForProjects(projectIds: string[]): Promise<Partial<ScopeChange>[]> {
  return (await findByIds<Record<string, unknown>>(TABLE, "project_id", projectIds, { columns: NARROW_COLUMNS })).map(
    (r) => fromRow<Partial<ScopeChange>>(r),
  );
}

export async function getScopeChangeById(id: string): Promise<ScopeChange | null> {
  const row = await selectOne<Record<string, unknown>>(TABLE, { where: [{ type: "eq", column: "id", value: id }] });
  return row ? map(row) : null;
}

export interface ScopeChangeInput {
  projectId: string;
  submittedDate?: Date | null;
  description: string;
  impactCost?: string | null;
  impactSchedule?: string | null;
  impactCostValue?: number | null;
  impactScheduleValue?: number | null;
  status?: ScopeChange["status"];
}

export async function createScopeChange(input: ScopeChangeInput): Promise<ScopeChange> {
  const now = new Date();
  const id = await insertRow(TABLE, toRow({ status: "OPEN", ...input, createdAt: now, updatedAt: now }));
  return readBackWithRetry(() => getScopeChangeById(id), "Failed to read back created scope change");
}

export async function updateScopeChange(id: string, fields: Partial<ScopeChangeInput>): Promise<void> {
  await updateRow(TABLE, id, toRow({ ...fields, updatedAt: new Date() }));
}

export async function deleteScopeChange(id: string): Promise<void> {
  await deleteRows(TABLE, [{ type: "eq", column: "id", value: id }]);
}
