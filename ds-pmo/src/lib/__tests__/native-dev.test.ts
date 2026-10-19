import { beforeAll, describe, expect, it } from "vitest";
import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { withAccessToken } from "../request-context";
import { closeRequestDatabricksClient, runDatabricksExecute, runDatabricksQuery } from "../databricks-sql";
import { qualifiedTable } from "../db/client";

describe.skipIf(process.env.PMO_NATIVE_DEV_TEST !== "true")("native DEV PMO data path", () => {
  let accessToken: string;
  const admin = "mustafaarda.bicakci@etexgroup.com";
  const tables = ["audit_logs", "budget_lines", "budgets", "categories", "divisions", "factories", "gate_records", "milestones", "planned_actions", "project_assignments", "project_documents", "project_snapshots", "projects", "resources", "risks", "scope_changes", "scope_grants", "users"];

  async function asUser<Result>(callback: () => Promise<Result>): Promise<Result> {
    return withAccessToken(accessToken, async () => {
      try { return await callback(); }
      finally { await closeRequestDatabricksClient(); }
    });
  }

  beforeAll(async () => {
    process.env.DATABRICKS_HOST = "adb-7181820732839861.1.azuredatabricks.net";
    process.env.DATABRICKS_CATALOG = "automation_d";
    process.env.DATABRICKS_SCHEMA = "silver";
    process.env.DATABRICKS_WAREHOUSE_HTTP_PATH = "/sql/1.0/warehouses/69ada62b2fb9b9e2";
    const credentials = JSON.parse(execFileSync("databricks", ["auth", "token", "--profile", "DEFAULT"], { encoding: "utf8" }));
    accessToken = credentials.access_token;
    expect(typeof accessToken).toBe("string");
    const identity = await asUser(() => runDatabricksQuery<{ principal: string }>("SELECT current_user() AS principal"));
    expect(identity[0]?.principal.toLowerCase()).toBe(admin);
  }, 120_000);

  it("has exactly the expected 18 DEV PMO tables", async () => {
    const inventory = await asUser(() => runDatabricksQuery<{ table_name: string }>(
      "SELECT table_name FROM automation_d.information_schema.tables WHERE table_schema = 'silver' AND startswith(lower(table_name), 'pmo_') ORDER BY table_name"));
    expect(inventory.map((row) => row.table_name.toLowerCase())).toEqual(tables.map((table) => `pmo_${table}`));
  }, 120_000);

  it("bootstrap reruns leave exactly one active initial admin", async () => {
    const result = await asUser(() => runDatabricksQuery<{ total: number | bigint; admins: number | bigint }>(
      `SELECT count(*) AS total, count_if(global_role = 'ADMIN' AND is_active) AS admins FROM ${qualifiedTable("users")} WHERE email = ?`, [admin]));
    expect(Number(result[0]?.total)).toBe(1);
    expect(Number(result[0]?.admins)).toBe(1);
  }, 120_000);

  it("completes parameterized insert/read/delete through the actual app SQL layer", async () => {
    const id = `pmo-validation-${randomUUID()}`;
    await asUser(async () => {
      const table = qualifiedTable("resources");
      try {
        await runDatabricksExecute(`INSERT INTO ${table} (id, category, title, description, href, format, sort_order, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
          [id, "VALIDATION", "PMO validation probe", null, "/", null, 0, new Date(), new Date()]);
        const rows = await runDatabricksQuery<{ id: string }>(`SELECT id FROM ${table} WHERE id = ?`, [id]);
        expect(rows).toEqual([{ id }]);
      } finally {
        await runDatabricksExecute(`DELETE FROM ${table} WHERE id = ?`, [id]);
      }
      const remaining = await runDatabricksQuery(`SELECT id FROM ${table} WHERE id = ?`, [id]);
      expect(remaining).toHaveLength(0);
    });
  }, 120_000);
});