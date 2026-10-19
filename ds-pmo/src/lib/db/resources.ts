import { selectRows, selectOne, insertRow, updateRow, deleteRows, countRows, readBackWithRetry } from "./query-builder";
import { fromRow, toRow } from "./rowmap";
import type { Resource } from "./models";

const TABLE = "resources";

function map(row: Record<string, unknown>): Resource {
  return fromRow<Resource>(row);
}

export async function listResources(): Promise<Resource[]> {
  const rows = await selectRows<Record<string, unknown>>(TABLE, {
    orderBy: [
      { column: "category", direction: "ASC" },
      { column: "sort_order", direction: "ASC" },
      { column: "created_at", direction: "ASC" },
    ],
  });
  return rows.map(map);
}

export async function getResourceById(id: string): Promise<Resource | null> {
  const row = await selectOne<Record<string, unknown>>(TABLE, { where: [{ type: "eq", column: "id", value: id }] });
  return row ? map(row) : null;
}

/** New rows append to the end of their category — matches the page's display order. */
async function nextSortOrder(category: string): Promise<number> {
  return countRows(TABLE, [{ type: "eq", column: "category", value: category }]);
}

export async function createResource(input: {
  category: string;
  title: string;
  description?: string | null;
  href: string;
  format?: string | null;
}): Promise<Resource> {
  const now = new Date();
  const sortOrder = await nextSortOrder(input.category);
  const id = await insertRow(TABLE, toRow({
    category: input.category,
    title: input.title,
    description: input.description ?? null,
    href: input.href,
    format: input.format ?? null,
    sortOrder,
    createdAt: now,
    updatedAt: now,
  }));
  return readBackWithRetry(() => getResourceById(id), "Failed to read back created resource");
}

export async function updateResource(
  id: string,
  fields: Partial<{ category: string; title: string; description: string | null; href: string; format: string | null }>,
): Promise<void> {
  await updateRow(TABLE, id, toRow({ ...fields, updatedAt: new Date() }));
}

export async function deleteResource(id: string): Promise<void> {
  await deleteRows(TABLE, [{ type: "eq", column: "id", value: id }]);
}
