import assert from "node:assert/strict";
import { execFileSync, spawn } from "node:child_process";
import { once } from "node:events";
import { createServer } from "node:net";
import { fileURLToPath } from "node:url";

assert.equal(process.env.PMO_NATIVE_DEV_HTTP_TEST, "true", "Native DEV HTTP validation must be explicitly enabled");
const root = fileURLToPath(new URL("../", import.meta.url));
const credentials = JSON.parse(execFileSync("databricks", ["auth", "token", "--profile", "DEFAULT"], { encoding: "utf8" }));
assert.equal(typeof credentials.access_token, "string");
assert(credentials.access_token.length > 0);
const listener = createServer();
listener.listen(0, "127.0.0.1");
await once(listener, "listening");
const port = listener.address().port;
await new Promise((resolve) => listener.close(resolve));
const server = spawn(process.execPath, [".next/standalone/server.js"], {
  cwd: root,
  stdio: ["ignore", "pipe", "pipe"],
  env: {
    ...process.env,
    PORT: String(port), HOSTNAME: "127.0.0.1", NODE_ENV: "production",
    DATABRICKS_HOST: "adb-7181820732839861.1.azuredatabricks.net",
    DATABRICKS_CATALOG: "automation_d", DATABRICKS_SCHEMA: "silver",
    DATABRICKS_WAREHOUSE_HTTP_PATH: "/sql/1.0/warehouses/69ada62b2fb9b9e2",
    EMAIL_NOTIFICATIONS_DISABLED: "true", NEXT_TELEMETRY_DISABLED: "1",
  },
});
let output = "";
server.stderr.on("data", () => {});
try {
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("Production server did not become ready")), 30_000);
    server.once("error", (error) => { clearTimeout(timer); reject(error); });
    server.once("exit", () => { clearTimeout(timer); reject(new Error("Production server exited before validation")); });
    server.stdout.on("data", (chunk) => {
      output += chunk.toString();
      if (output.includes("Ready")) { clearTimeout(timer); resolve(); }
    });
  });
  const base = `http://127.0.0.1:${port}`;
  const headers = {
    "x-forwarded-email": "mustafaarda.bicakci@etexgroup.com",
    "x-forwarded-access-token": credentials.access_token,
  };
  const dashboard = await fetch(`${base}/dashboard`, { headers, redirect: "manual", signal: AbortSignal.timeout(120_000) });
  const html = await dashboard.text();
  assert.equal(dashboard.status, 200, "Dashboard must render instead of redirecting or failing");
  assert(html.includes(headers["x-forwarded-email"]), "Rendered app shell must contain the resolved admin identity");
  assert(!/data-dgst=|ERR_INVALID_URL|NEXT_HTTP_ERROR_FALLBACK/.test(html), "Dashboard must not contain a streamed server error");
  console.log("PASS: authenticated production /dashboard renders with the real Apps hostname format");

  for (const endpoint of ["/api/portfolio", "/api/projects", "/api/filter-options"]) {
    const response = await fetch(`${base}${endpoint}`, { headers, signal: AbortSignal.timeout(120_000) });
    assert.equal(response.status, 200, `${endpoint} must succeed`);
    const data = await response.json();
    assert(data && typeof data === "object");
    assert(!Object.hasOwn(data, "error"), `${endpoint} returned an application error`);
    console.log(`PASS: authenticated ${endpoint} returns DEV data successfully`);
  }
  const unauthenticated = await fetch(`${base}/api/portfolio`);
  assert.equal(unauthenticated.status, 401);
  console.log("PASS: API request without a delegated user token is rejected");
} finally {
  if (server.exitCode === null) {
    const exited = once(server, "exit");
    server.kill("SIGTERM");
    await exited;
  }
}