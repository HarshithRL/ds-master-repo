import { selectRows, selectOne, insertRow, updateRow, deleteRows, findByIds, countRows, readBackWithRetry } from "./query-builder";
import { fromRow, toRow } from "./rowmap";
import { attachOne } from "./include";
import { getDivisionsByIds } from "./divisions";
import type { Factory, Division } from "./models";

const TABLE = "factories";

function map(row: Record<string, unknown>): Factory {
  return fromRow<Factory>(row);
}

export async function listFactories(activeOnly = false): Promise<Factory[]> {
  const rows = await selectRows<Record<string, unknown>>(TABLE, {
    where: activeOnly ? [{ type: "eq", column: "is_active", value: true }] : [],
    orderBy: [{ column: "name", direction: "ASC" }],
  });
  return rows.map(map);
}

/** Factories with their `division` relation attached (mirrors Prisma's `include: { division: true }`). */
export async function listFactoriesWithDivision(activeOnly = false): Promise<(Factory & { division: Division | null })[]> {
  const factories = await listFactories(activeOnly);
  const divisions = await getDivisionsByIds(factories.map((f) => f.divisionId).filter((x): x is string => !!x));
  return attachOne(factories, divisions, (f) => f.divisionId, "division");
}

export async function getFactoriesByIds(ids: string[]): Promise<Factory[]> {
  return (await findByIds<Record<string, unknown>>(TABLE, "id", ids)).map(map);
}

export async function getFactoryById(id: string): Promise<Factory | null> {
  const row = await selectOne<Record<string, unknown>>(TABLE, { where: [{ type: "eq", column: "id", value: id }] });
  return row ? map(row) : null;
}

export async function getFactoryByCode(code: string): Promise<Factory | null> {
  const row = await selectOne<Record<string, unknown>>(TABLE, { where: [{ type: "ilike", column: "code", value: code }] });
  return row ? map(row) : null;
}

/** Resolve a list of factory *names* (case-insensitive) to their ids. */
export async function getFactoryIdsByNames(names: string[]): Promise<string[]> {
  if (names.length === 0) return [];
  const rows = await selectRows<{ id: string }>(TABLE, {
    where: [{ type: "or", conditions: names.map((n) => ({ type: "ilike" as const, column: "name", value: n })) }],
    columns: "id",
  });
  return rows.map((r) => r.id);
}

export async function countProjectsForFactory(factoryId: string): Promise<number> {
  return countRows("projects", [{ type: "eq", column: "factory_id", value: factoryId }]);
}

export interface CreateFactoryInput {
  code?: string | null;
  name: string;
  shortName?: string | null;
  country?: string | null;
  currency?: string | null;
  divisionId?: string | null;
  isActive?: boolean;
}

export async function createFactory(input: CreateFactoryInput): Promise<Factory> {
  const now = new Date();
  const id = await insertRow(TABLE, toRow({ ...input, isActive: input.isActive ?? true, createdAt: now, updatedAt: now }));
  return readBackWithRetry(() => getFactoryById(id), "Failed to read back created factory");
}

export async function updateFactory(id: string, fields: Partial<CreateFactoryInput>): Promise<void> {
  await updateRow(TABLE, id, toRow({ ...fields, updatedAt: new Date() }));
}

export async function deleteFactory(id: string): Promise<void> {
  await deleteRows(TABLE, [{ type: "eq", column: "id", value: id }]);
}
