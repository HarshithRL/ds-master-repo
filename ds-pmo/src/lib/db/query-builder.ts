import { runDatabricksQuery, runDatabricksExecute, qualifiedTable, type DBSQLParameterValue } from "./client";
import { newId } from "./id";

// ─── WHERE condition compiler ──────────────────────────────────────────────

export type WhereCondition =
  | { type: "eq"; column: string; value: DBSQLParameterValue }
  | { type: "neq"; column: string; value: DBSQLParameterValue }
  | { type: "in"; column: string; values: DBSQLParameterValue[] }
  | { type: "isNull"; column: string; negate?: boolean }
  | { type: "gte"; column: string; value: DBSQLParameterValue }
  | { type: "lte"; column: string; value: DBSQLParameterValue }
  | { type: "ilike"; column: string; value: string }
  | { type: "or"; conditions: WhereCondition[] }
  | { type: "raw"; sql: string; params?: DBSQLParameterValue[] };

interface Compiled {
  sql: string;
  params: DBSQLParameterValue[];
}

function compileCondition(cond: WhereCondition): Compiled {
  switch (cond.type) {
    case "eq":
      return { sql: `${cond.column} = ?`, params: [cond.value] };
    case "neq":
      return { sql: `${cond.column} != ?`, params: [cond.value] };
    case "in":
      if (cond.values.length === 0) return { sql: "1 = 0", params: [] };
      return { sql: `${cond.column} IN (${cond.values.map(() => "?").join(", ")})`, params: cond.values };
    case "isNull":
      return { sql: `${cond.column} IS ${cond.negate ? "NOT " : ""}NULL`, params: [] };
    case "gte":
      return { sql: `${cond.column} >= ?`, params: [cond.value] };
    case "lte":
      return { sql: `${cond.column} <= ?`, params: [cond.value] };
    case "ilike":
      return { sql: `LOWER(${cond.column}) LIKE LOWER(?)`, params: [`%${cond.value}%`] };
    case "or": {
      if (cond.conditions.length === 0) return { sql: "1 = 0", params: [] };
      const parts = cond.conditions.map(compileCondition);
      return { sql: `(${parts.map((p) => p.sql).join(" OR ")})`, params: parts.flatMap((p) => p.params) };
    }
    case "raw":
      return { sql: cond.sql, params: cond.params ?? [] };
  }
}

export function buildWhereClause(conditions: WhereCondition[]): Compiled {
  if (conditions.length === 0) return { sql: "", params: [] };
  const parts = conditions.map(compileCondition);
  return { sql: `WHERE ${parts.map((p) => p.sql).join(" AND ")}`, params: parts.flatMap((p) => p.params) };
}

// ─── Generic read/write helpers ────────────────────────────────────────────

export interface OrderBy {
  column: string;
  direction: "ASC" | "DESC";
}

export interface SelectOptions {
  where?: WhereCondition[];
  orderBy?: OrderBy[];
  limit?: number;
  offset?: number;
  /** Override the default `*` column list, e.g. a narrow projection. */
  columns?: string;
  /** Raw JOIN clause(s) appended after the FROM table, before WHERE. */
  joins?: string;
}

export async function selectRows<T = Record<string, unknown>>(
  table: string,
  opts: SelectOptions = {},
): Promise<T[]> {
  const { sql: whereSql, params } = buildWhereClause(opts.where ?? []);
  const orderSql = opts.orderBy?.length
    ? `ORDER BY ${opts.orderBy.map((o) => `${o.column} ${o.direction}`).join(", ")}`
    : "";
  const limitSql = opts.limit != null ? `LIMIT ${Number(opts.limit)}` : "";
  const offsetSql = opts.offset != null ? `OFFSET ${Number(opts.offset)}` : "";
  const sql = [
    `SELECT ${opts.columns ?? "*"} FROM ${qualifiedTable(table)}`,
    opts.joins ?? "",
    whereSql,
    orderSql,
    limitSql,
    offsetSql,
  ]
    .filter(Boolean)
    .join(" ");
  return runDatabricksQuery<T>(sql, params);
}

export async function selectOne<T = Record<string, unknown>>(
  table: string,
  opts: SelectOptions = {},
): Promise<T | null> {
  const rows = await selectRows<T>(table, { ...opts, limit: 1 });
  return rows[0] ?? null;
}

export async function countRows(table: string, where: WhereCondition[] = [], joins?: string): Promise<number> {
  const { sql: whereSql, params } = buildWhereClause(where);
  const sql = [`SELECT COUNT(*) AS count FROM ${qualifiedTable(table)}`, joins ?? "", whereSql]
    .filter(Boolean)
    .join(" ");
  const rows = await runDatabricksQuery<{ count: number | string | bigint }>(sql, params);
  return Number(rows[0]?.count ?? 0);
}

/** Batched `WHERE column IN (...)` lookup, chunked to stay under statement-size limits. */
export async function findByIds<T = Record<string, unknown>>(
  table: string,
  column: string,
  ids: string[],
  opts: Omit<SelectOptions, "where" | "limit" | "offset"> = {},
): Promise<T[]> {
  const unique = [...new Set(ids)].filter((id): id is string => !!id);
  if (unique.length === 0) return [];

  const CHUNK = 500;
  const results: T[] = [];
  for (let i = 0; i < unique.length; i += CHUNK) {
    const chunk = unique.slice(i, i + CHUNK);
    const rows = await selectRows<T>(table, { ...opts, where: [{ type: "in", column, values: chunk }] });
    results.push(...rows);
  }
  return results;
}

export async function insertRow(
  table: string,
  columns: Record<string, DBSQLParameterValue>,
): Promise<string> {
  const id = (columns.id as string | undefined) ?? newId();
  const row: Record<string, DBSQLParameterValue> = { ...columns, id };
  const keys = Object.keys(row);
  const sql = `INSERT INTO ${qualifiedTable(table)} (${keys.join(", ")}) VALUES (${keys.map(() => "?").join(", ")})`;
  await runDatabricksExecute(sql, keys.map((k) => row[k]));
  return id;
}

const INSERT_BATCH_SIZE = 200;

/** Batched multi-row insert. All rows must share the same column set. */
export async function insertRows(
  table: string,
  rows: Record<string, DBSQLParameterValue>[],
): Promise<void> {
  if (rows.length === 0) return;
  const normalized: Record<string, DBSQLParameterValue>[] = rows.map((r) => ({ ...r, id: (r.id as string | undefined) ?? newId() }));
  const keys = Object.keys(normalized[0]);

  for (let i = 0; i < normalized.length; i += INSERT_BATCH_SIZE) {
    const batch = normalized.slice(i, i + INSERT_BATCH_SIZE);
    const placeholders = batch.map(() => `(${keys.map(() => "?").join(", ")})`).join(", ");
    const params = batch.flatMap((row) => keys.map((k) => row[k]));
    await runDatabricksExecute(
      `INSERT INTO ${qualifiedTable(table)} (${keys.join(", ")}) VALUES ${placeholders}`,
      params,
    );
  }
}

export async function updateRow(
  table: string,
  id: string,
  columns: Record<string, DBSQLParameterValue>,
): Promise<void> {
  const keys = Object.keys(columns);
  if (keys.length === 0) return;
  const setSql = keys.map((k) => `${k} = ?`).join(", ");
  const sql = `UPDATE ${qualifiedTable(table)} SET ${setSql} WHERE id = ?`;
  await runDatabricksExecute(sql, [...keys.map((k) => columns[k]), id]);
}

export async function deleteRows(table: string, where: WhereCondition[]): Promise<void> {
  const { sql: whereSql, params } = buildWhereClause(where);
  if (!whereSql) throw new Error(`deleteRows(${table}) refused: empty WHERE would delete the whole table`);
  await runDatabricksExecute(`DELETE FROM ${qualifiedTable(table)} ${whereSql}`, params);
}

/**
 * Read-back helper that retries to handle Delta Lake cross-session
 * read-after-write visibility lag. After an INSERT the row may not be
 * visible in a new session for a brief window; this retries the read
 * a few times before giving up.
 */
export async function readBackWithRetry<T>(
  readFn: () => Promise<T | null>,
  errorLabel: string,
  maxAttempts = 3,
  delayMs = 300,
): Promise<T> {
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    const result = await readFn();
    if (result) return result;
    if (attempt < maxAttempts) {
      await new Promise((resolve) => setTimeout(resolve, delayMs));
    }
  }
  throw new Error(errorLabel);
}

/**
 * MERGE-based upsert keyed on `keyColumns`. `columns` must include every
 * key column plus whatever else should be set on insert/update.
 */
export async function upsertRow(
  table: string,
  keyColumns: string[],
  columns: Record<string, DBSQLParameterValue>,
): Promise<void> {
  const row: Record<string, DBSQLParameterValue> = { ...columns, id: (columns.id as string | undefined) ?? newId() };
  const allKeys = Object.keys(row);
  const updateKeys = allKeys.filter((k) => !keyColumns.includes(k) && k !== "id");

  const selectList = allKeys.map((k) => `? AS ${k}`).join(", ");
  const onClause = keyColumns.map((k) => `t.${k} = s.${k}`).join(" AND ");
  const updateSet = updateKeys.map((k) => `${k} = s.${k}`).join(", ");
  const insertCols = allKeys.join(", ");
  const insertVals = allKeys.map((k) => `s.${k}`).join(", ");

  const sql = `
    MERGE INTO ${qualifiedTable(table)} t
    USING (SELECT ${selectList}) s
    ON ${onClause}
    WHEN MATCHED THEN UPDATE SET ${updateSet || "id = t.id"}
    WHEN NOT MATCHED THEN INSERT (${insertCols}) VALUES (${insertVals})
  `;
  await runDatabricksExecute(sql, allKeys.map((k) => row[k]));
}
