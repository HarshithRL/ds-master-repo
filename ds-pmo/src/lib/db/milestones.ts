import { selectRows, selectOne, insertRow, updateRow, deleteRows, readBackWithRetry } from "./query-builder";
import { fromRow, toRow } from "./rowmap";
import type { Milestone } from "./models";

const TABLE = "milestones";

function map(row: Record<string, unknown>): Milestone {
  return fromRow<Milestone>(row);
}

export async function listMilestonesForProject(projectId: string): Promise<Milestone[]> {
  const rows = await selectRows<Record<string, unknown>>(TABLE, {
    where: [{ type: "eq", column: "project_id", value: projectId }],
    orderBy: [{ column: "sort_order", direction: "ASC" }],
  });
  return rows.map(map);
}

export async function getMilestoneById(id: string): Promise<Milestone | null> {
  const row = await selectOne<Record<string, unknown>>(TABLE, { where: [{ type: "eq", column: "id", value: id }] });
  return row ? map(row) : null;
}

export interface MilestoneInput {
  projectId: string;
  name: string;
  targetDate?: Date | null;
  expectedDate?: Date | null;
  remarks?: string | null;
  sortOrder?: number;
}

export async function createMilestone(input: MilestoneInput): Promise<Milestone> {
  const now = new Date();
  const id = await insertRow(TABLE, toRow({ sortOrder: 0, ...input, createdAt: now, updatedAt: now }));
  return readBackWithRetry(() => getMilestoneById(id), "Failed to read back created milestone");
}

export async function updateMilestone(id: string, fields: Partial<MilestoneInput>): Promise<void> {
  await updateRow(TABLE, id, toRow({ ...fields, updatedAt: new Date() }));
}

export async function deleteMilestone(id: string): Promise<void> {
  await deleteRows(TABLE, [{ type: "eq", column: "id", value: id }]);
}
