import { selectRows, insertRow, countRows, deleteRows, findByIds } from "./query-builder";
import { fromRow, toRow } from "./rowmap";
import type { AuditLog } from "./models";
import type { WhereCondition } from "./query-builder";

const TABLE = "audit_logs";
const JSON_COLUMNS = ["changes"];

function map(row: Record<string, unknown>): AuditLog {
  return fromRow<AuditLog>(row, JSON_COLUMNS);
}

export async function createAuditLogRow(input: {
  userId?: string | null;
  projectId?: string | null;
  action: string;
  entity: string;
  entityId?: string | null;
  changes?: Record<string, { old: unknown; new: unknown }> | null;
}): Promise<void> {
  await insertRow(
    TABLE,
    toRow({ ...input, createdAt: new Date() }, JSON_COLUMNS),
  );
}

export interface ListAuditLogsOptions {
  entities?: string[];
  action?: string;
  userId?: string;
  from?: Date;
  to?: Date;
  search?: string;
  /** ids of users whose name/email matched `search` — resolved by the caller since users live in a separate table. */
  matchingUserIds?: string[];
  limit?: number;
  offset?: number;
}

export async function listAuditLogs(opts: ListAuditLogsOptions): Promise<{ logs: AuditLog[]; total: number }> {
  const where: WhereCondition[] = [];
  if (opts.entities?.length) where.push({ type: "in", column: "entity", values: opts.entities });
  if (opts.action) where.push({ type: "eq", column: "action", value: opts.action });
  if (opts.userId) where.push({ type: "eq", column: "user_id", value: opts.userId });
  if (opts.from) where.push({ type: "gte", column: "created_at", value: opts.from });
  if (opts.to) where.push({ type: "lte", column: "created_at", value: opts.to });
  if (opts.search) {
    const searchConds: WhereCondition[] = [
      { type: "ilike", column: "entity", value: opts.search },
      { type: "ilike", column: "action", value: opts.search },
    ];
    if (opts.matchingUserIds?.length) {
      searchConds.push({ type: "in", column: "user_id", values: opts.matchingUserIds });
    }
    where.push({ type: "or", conditions: searchConds });
  }

  const [rows, total] = await Promise.all([
    selectRows<Record<string, unknown>>(TABLE, {
      where,
      orderBy: [{ column: "created_at", direction: "DESC" }],
      limit: opts.limit,
      offset: opts.offset,
    }),
    countRows(TABLE, where),
  ]);
  return { logs: rows.map(map), total };
}

export async function listAuditLogsForProject(projectId: string, limit = 10): Promise<AuditLog[]> {
  const rows = await selectRows<Record<string, unknown>>(TABLE, {
    where: [{ type: "eq", column: "project_id", value: projectId }],
    orderBy: [{ column: "created_at", direction: "DESC" }],
    limit,
  });
  return rows.map(map);
}

export async function listAuditLogsForProjects(projectIds: string[]): Promise<AuditLog[]> {
  return (await findByIds<Record<string, unknown>>(TABLE, "project_id", projectIds)).map(map);
}

export async function deleteAllAuditLogs(): Promise<number> {
  const total = await countRows(TABLE);
  await deleteRows(TABLE, [{ type: "raw", sql: "1 = 1" }]);
  return total;
}
