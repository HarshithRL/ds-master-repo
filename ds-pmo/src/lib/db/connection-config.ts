const environments: Record<string, { catalog: string; warehouse: string }> = {
  "adb-7181820732839861.1.azuredatabricks.net": { catalog: "automation_d", warehouse: "69ada62b2fb9b9e2" },
  "adb-4796304964978539.19.azuredatabricks.net": { catalog: "automation_a", warehouse: "0ef3e37fbbd5b772" },
  "adb-4844910598668398.18.azuredatabricks.net": { catalog: "automation_p", warehouse: "f500d0d670ae024b" },
};

export function resolveConnectionConfig(env: Record<string, string | undefined> = process.env): { host: string; path: string } {
  const suppliedHost = env.DATABRICKS_HOST ?? "";
  const url = new URL(suppliedHost.includes("://") ? suppliedHost : `https://${suppliedHost}`);
  const expected = environments[url.hostname];
  if (!expected || url.protocol !== "https:" || url.username || url.password || url.port || url.search || url.hash || url.pathname !== "/") {
    throw new Error("PMO requires a known HTTPS Databricks workspace origin");
  }
  const path = `/sql/1.0/warehouses/${expected.warehouse}`;
  if (env.DATABRICKS_CATALOG !== expected.catalog || env.DATABRICKS_SCHEMA !== "silver" || env.DATABRICKS_WAREHOUSE_HTTP_PATH !== path) {
    throw new Error("PMO workspace, catalog, schema and warehouse do not match");
  }
  return { host: url.hostname, path };
}