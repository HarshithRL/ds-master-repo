import { selectRows, selectOne, insertRow, updateRow, deleteRows, readBackWithRetry } from "./query-builder";
import { fromRow, toRow } from "./rowmap";
import type { PlannedAction } from "./models";

const TABLE = "planned_actions";

function map(row: Record<string, unknown>): PlannedAction {
  return fromRow<PlannedAction>(row);
}

export async function listPlannedActionsForProject(projectId: string): Promise<PlannedAction[]> {
  const rows = await selectRows<Record<string, unknown>>(TABLE, {
    where: [{ type: "eq", column: "project_id", value: projectId }],
    orderBy: [{ column: "sort_order", direction: "ASC" }],
  });
  return rows.map(map);
}

export async function getPlannedActionById(id: string): Promise<PlannedAction | null> {
  const row = await selectOne<Record<string, unknown>>(TABLE, { where: [{ type: "eq", column: "id", value: id }] });
  return row ? map(row) : null;
}

export interface PlannedActionInput {
  projectId: string;
  action: string;
  ownerLabel?: string | null;
  byDate?: Date | null;
  status?: PlannedAction["status"];
  notes?: string | null;
  sortOrder?: number;
}

export async function createPlannedAction(input: PlannedActionInput): Promise<PlannedAction> {
  const now = new Date();
  const id = await insertRow(TABLE, toRow({ status: "OPEN", sortOrder: 0, ...input, createdAt: now, updatedAt: now }));
  return readBackWithRetry(() => getPlannedActionById(id), "Failed to read back created planned action");
}

export async function updatePlannedAction(id: string, fields: Partial<PlannedActionInput>): Promise<void> {
  await updateRow(TABLE, id, toRow({ ...fields, updatedAt: new Date() }));
}

export async function deletePlannedAction(id: string): Promise<void> {
  await deleteRows(TABLE, [{ type: "eq", column: "id", value: id }]);
}
