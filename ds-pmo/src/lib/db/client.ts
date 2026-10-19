export { runDatabricksQuery, runDatabricksExecute } from "../databricks-sql";
export type { DBSQLParameterValue } from "../databricks-sql";
import { resolveTableName } from "./table-names";

export function qualifiedTable(table: string): string {
  return resolveTableName(table);
}
