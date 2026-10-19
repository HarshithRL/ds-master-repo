import { selectRows, selectOne, insertRow, updateRow, deleteRows, findByIds, countRows, readBackWithRetry } from "./query-builder";
import { fromRow, toRow } from "./rowmap";
import type { Category } from "./models";

const TABLE = "categories";

function map(row: Record<string, unknown>): Category {
  return fromRow<Category>(row);
}

export async function listCategories(activeOnly = false): Promise<Category[]> {
  const rows = await selectRows<Record<string, unknown>>(TABLE, {
    where: activeOnly ? [{ type: "eq", column: "is_active", value: true }] : [],
    orderBy: [{ column: "name", direction: "ASC" }],
  });
  return rows.map(map);
}

export async function getCategoriesByIds(ids: string[]): Promise<Category[]> {
  return (await findByIds<Record<string, unknown>>(TABLE, "id", ids)).map(map);
}

export async function getCategoryById(id: string): Promise<Category | null> {
  const row = await selectOne<Record<string, unknown>>(TABLE, { where: [{ type: "eq", column: "id", value: id }] });
  return row ? map(row) : null;
}

export async function getCategoryByCode(code: string): Promise<Category | null> {
  const row = await selectOne<Record<string, unknown>>(TABLE, { where: [{ type: "ilike", column: "code", value: code }] });
  return row ? map(row) : null;
}

/** Resolve a list of category *names* (case-insensitive) to their ids. */
export async function getCategoryIdsByNames(names: string[]): Promise<string[]> {
  if (names.length === 0) return [];
  const rows = await selectRows<{ id: string }>(TABLE, {
    where: [{ type: "or", conditions: names.map((n) => ({ type: "ilike" as const, column: "name", value: n })) }],
    columns: "id",
  });
  return rows.map((r) => r.id);
}

export async function countProjectsForCategory(categoryId: string): Promise<number> {
  return countRows("projects", [{ type: "eq", column: "category_id", value: categoryId }]);
}

export async function createCategory(input: { code: string; name: string; isActive?: boolean }): Promise<Category> {
  const now = new Date();
  const id = await insertRow(TABLE, toRow({ ...input, isActive: input.isActive ?? true, createdAt: now, updatedAt: now }));
  return readBackWithRetry(() => getCategoryById(id), "Failed to read back created category");
}

export async function updateCategory(id: string, fields: Partial<{ code: string; name: string; isActive: boolean }>): Promise<void> {
  await updateRow(TABLE, id, toRow({ ...fields, updatedAt: new Date() }));
}

export async function deleteCategory(id: string): Promise<void> {
  await deleteRows(TABLE, [{ type: "eq", column: "id", value: id }]);
}
