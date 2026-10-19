import { selectRows, selectOne, insertRow, updateRow, deleteRows, findByIds, readBackWithRetry } from "./query-builder";
import { fromRow, toRow } from "./rowmap";
import type { Division } from "./models";

const TABLE = "divisions";

function map(row: Record<string, unknown>): Division {
  return fromRow<Division>(row);
}

export async function listDivisions(activeOnly = false): Promise<Division[]> {
  const rows = await selectRows<Record<string, unknown>>(TABLE, {
    where: activeOnly ? [{ type: "eq", column: "is_active", value: true }] : [],
    orderBy: [{ column: "name", direction: "ASC" }],
  });
  return rows.map(map);
}

export async function getDivisionsByIds(ids: string[]): Promise<Division[]> {
  return (await findByIds<Record<string, unknown>>(TABLE, "id", ids)).map(map);
}

export async function getDivisionById(id: string): Promise<Division | null> {
  const row = await selectOne<Record<string, unknown>>(TABLE, { where: [{ type: "eq", column: "id", value: id }] });
  return row ? map(row) : null;
}

export async function getDivisionByName(name: string): Promise<Division | null> {
  const row = await selectOne<Record<string, unknown>>(TABLE, {
    where: [{ type: "ilike", column: "name", value: name }],
  });
  return row ? map(row) : null;
}

export async function createDivision(input: { name: string; isActive?: boolean }): Promise<Division> {
  const now = new Date();
  const id = await insertRow(TABLE, toRow({ name: input.name, isActive: input.isActive ?? true, createdAt: now, updatedAt: now }));
  return readBackWithRetry(() => getDivisionById(id), "Failed to read back created division");
}

export async function updateDivision(id: string, fields: Partial<{ name: string; isActive: boolean }>): Promise<void> {
  await updateRow(TABLE, id, toRow({ ...fields, updatedAt: new Date() }));
}

export async function deleteDivision(id: string): Promise<void> {
  await deleteRows(TABLE, [{ type: "eq", column: "id", value: id }]);
}
