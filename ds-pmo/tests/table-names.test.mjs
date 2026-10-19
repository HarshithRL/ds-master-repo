import assert from "node:assert/strict";
import test from "node:test";
import { resolveTableName } from "../src/lib/db/table-names.ts";

for (const suffix of ["d", "a", "p"]) {
  test(`PMO tables use automation_${suffix}.silver`, () => {
    assert.equal(resolveTableName("users", {
      DATABRICKS_CATALOG: `automation_${suffix}`,
      DATABRICKS_SCHEMA: "silver",
    }), `automation_${suffix}.silver.PMO_users`);
  });
}

test("rejects other catalogs, schemas, missing configuration and SQL injection", () => {
  for (const catalog of [undefined, "engineering_global_pmo_s", "automation_x", "automation_p; DROP TABLE x"]) {
    assert.throws(() => resolveTableName("users", { DATABRICKS_CATALOG: catalog, DATABRICKS_SCHEMA: "silver" }));
  }
  for (const schema of [undefined, "pmo", "bronze", "gold", "silver.other"]) {
    assert.throws(() => resolveTableName("users", { DATABRICKS_CATALOG: "automation_d", DATABRICKS_SCHEMA: schema }));
  }
  for (const table of ["", "users; DELETE FROM users", "other.users", "`users`", "PMO_users"]) {
    assert.throws(() => resolveTableName(table, { DATABRICKS_CATALOG: "automation_d", DATABRICKS_SCHEMA: "silver" }));
  }
});