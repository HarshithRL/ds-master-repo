import type { DBSQLParameterValue } from "./client";

// Databricks SQL rows come back snake_case (matching the DDL); the app's JS
// objects (and API response shapes, kept byte-identical to the old Prisma
// output) are camelCase. TIMESTAMP columns already arrive as JS `Date`
// objects (the driver converts them) — only JSON-encoded STRING columns
// (arrays/objects) need an explicit parse/stringify step, listed per call
// by the caller since which columns are JSON-encoded is table-specific.

function snakeToCamel(key: string): string {
  return key.replace(/_([a-z0-9])/g, (_, c: string) => c.toUpperCase());
}

function camelToSnake(key: string): string {
  return key.replace(/[A-Z]/g, (c) => `_${c.toLowerCase()}`);
}

/** Raw Databricks row (snake_case) → camelCase JS object. */
export function fromRow<T>(row: Record<string, unknown>, jsonColumns: string[] = []): T {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(row)) {
    const camelKey = snakeToCamel(key);
    // `jsonColumns` is declared in camelCase by every caller (matching
    // `toRow`'s own camelCase input) — compare against `camelKey`, not the
    // raw snake_case `key`, or multi-word columns (e.g. wbsCodes / wbs_codes)
    // never match and stay an unparsed JSON string instead of an array.
    out[camelKey] = jsonColumns.includes(camelKey) && typeof value === "string" ? JSON.parse(value) : value;
  }
  return out as T;
}

export function fromRows<T>(rows: Record<string, unknown>[], jsonColumns: string[] = []): T[] {
  return rows.map((r) => fromRow<T>(r, jsonColumns));
}

/** camelCase JS object → snake_case columns for insert/update. Skips `undefined` values. */
export function toRow(
  obj: Record<string, unknown>,
  jsonColumns: string[] = [],
): Record<string, DBSQLParameterValue> {
  const out: Record<string, DBSQLParameterValue> = {};
  for (const [key, value] of Object.entries(obj)) {
    if (value === undefined) continue;
    const snakeKey = camelToSnake(key);
    out[snakeKey] = jsonColumns.includes(key)
      ? value == null
        ? null
        : JSON.stringify(value)
      : (value as DBSQLParameterValue);
  }
  return out;
}
