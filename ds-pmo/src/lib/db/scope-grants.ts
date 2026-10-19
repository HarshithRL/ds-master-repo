import { selectRows, insertRow, deleteRows } from "./query-builder";
import { fromRow } from "./rowmap";
import type { ScopeGrant } from "./models";

const TABLE = "scope_grants";

function mapGrant(row: Record<string, unknown>): ScopeGrant {
  return fromRow<ScopeGrant>(row);
}

export async function listGrantsForUser(userId: string): Promise<ScopeGrant[]> {
  const rows = await selectRows<Record<string, unknown>>(TABLE, {
    where: [{ type: "eq", column: "user_id", value: userId }],
  });
  return rows.map(mapGrant);
}

export async function findGrantMatchingFactoryOrDivision(
  userId: string,
  factoryId?: string | null,
  divisionId?: string | null,
): Promise<ScopeGrant | null> {
  const grants = await listGrantsForUser(userId);
  return (
    grants.find((g) => (factoryId && g.factoryId === factoryId) || (divisionId && g.divisionId === divisionId)) ?? null
  );
}

export async function createGrant(input: { userId: string; divisionId?: string | null; factoryId?: string | null }): Promise<void> {
  await insertRow(TABLE, {
    user_id: input.userId,
    division_id: input.divisionId ?? null,
    factory_id: input.factoryId ?? null,
    created_at: new Date(),
  });
}

export async function deleteGrant(id: string): Promise<void> {
  await deleteRows(TABLE, [{ type: "eq", column: "id", value: id }]);
}

export async function deleteGrantsForUser(userId: string): Promise<void> {
  await deleteRows(TABLE, [{ type: "eq", column: "user_id", value: userId }]);
}
