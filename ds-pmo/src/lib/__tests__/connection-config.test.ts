import { describe, expect, it } from "vitest";
import { resolveConnectionConfig } from "../db/connection-config";

const configurations = [
  ["adb-7181820732839861.1.azuredatabricks.net", "automation_d", "69ada62b2fb9b9e2"],
  ["adb-4796304964978539.19.azuredatabricks.net", "automation_a", "ab42869e34018a6e"],
  ["adb-4844910598668398.18.azuredatabricks.net", "automation_p", "4d5f9389063a8264"],
];

describe("PMO environment isolation", () => {
  for (const [host, catalog, warehouse] of configurations) {
    const env = { DATABRICKS_HOST: `https://${host}`, DATABRICKS_CATALOG: catalog,
      DATABRICKS_SCHEMA: "silver", DATABRICKS_WAREHOUSE_HTTP_PATH: `/sql/1.0/warehouses/${warehouse}` };
    it(`accepts the supplied ${catalog} connection`, () => {
      expect(resolveConnectionConfig(env)).toEqual({ host, path: env.DATABRICKS_WAREHOUSE_HTTP_PATH });
    });
    it(`accepts the Databricks Apps bare hostname for ${catalog}`, () => {
      expect(resolveConnectionConfig({ ...env, DATABRICKS_HOST: host })).toEqual({ host, path: env.DATABRICKS_WAREHOUSE_HTTP_PATH });
    });
    it(`rejects cross-environment configuration for ${catalog}`, () => {
      expect(() => resolveConnectionConfig({ ...env, DATABRICKS_CATALOG: "engineering_global_pmo_s" })).toThrow();
      expect(() => resolveConnectionConfig({ ...env, DATABRICKS_SCHEMA: "pmo" })).toThrow();
      expect(() => resolveConnectionConfig({ ...env, DATABRICKS_WAREHOUSE_HTTP_PATH: "/sql/1.0/warehouses/other" })).toThrow();
      for (const [, otherCatalog, otherWarehouse] of configurations) {
        if (otherCatalog !== catalog) {
          expect(() => resolveConnectionConfig({ ...env, DATABRICKS_WAREHOUSE_HTTP_PATH: `/sql/1.0/warehouses/${otherWarehouse}` })).toThrow();
        }
      }
    });
  }
  for (const [host, catalog, warehouse] of [
    ["adb-4796304964978539.19.azuredatabricks.net", "automation_a", "0ef3e37fbbd5b772"],
    ["adb-4844910598668398.18.azuredatabricks.net", "automation_p", "f500d0d670ae024b"],
  ]) {
    it(`rejects the replaced shared warehouse for ${catalog}`, () => {
      expect(() => resolveConnectionConfig({ DATABRICKS_HOST: host, DATABRICKS_CATALOG: catalog,
        DATABRICKS_SCHEMA: "silver", DATABRICKS_WAREHOUSE_HTTP_PATH: `/sql/1.0/warehouses/${warehouse}` })).toThrow();
    });
  }
  it("rejects unknown, insecure or credential-bearing endpoints", () => {
    for (const host of [undefined, "example.com", "http://adb-7181820732839861.1.azuredatabricks.net", "https://example.com", "https://user:secret@adb-7181820732839861.1.azuredatabricks.net", "https://adb-7181820732839861.1.azuredatabricks.net/?x=y"]) {
      expect(() => resolveConnectionConfig({ DATABRICKS_HOST: host })).toThrow();
    }
  });
});