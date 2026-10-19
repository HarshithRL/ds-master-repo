export function resolveTableName(table: string, env: Record<string, string | undefined> = process.env): string {
  const catalog = env.DATABRICKS_CATALOG;
  const schema = env.DATABRICKS_SCHEMA;
  if (!catalog || !/^automation_[dap]$/.test(catalog)) {
    throw new Error("DATABRICKS_CATALOG must be automation_d, automation_a or automation_p");
  }
  if (schema !== "silver") {
    throw new Error("DATABRICKS_SCHEMA must be the existing silver schema");
  }
  if (!/^[a-z][a-z0-9_]*$/.test(table)) {
    throw new Error("Invalid PMO table identifier");
  }
  return `${catalog}.${schema}.PMO_${table}`;
}