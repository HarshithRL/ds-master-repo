import { existsSync } from "node:fs";
import { spawn } from "node:child_process";

const port = process.env.DATABRICKS_APP_PORT || process.env.PORT || "3000";
if (!/^\d+$/.test(port) || Number(port) < 1 || Number(port) > 65535) throw new Error("Invalid app port");
if (!existsSync(".next/standalone/server.js")) throw new Error("Run npm run build before starting PMO");
const server = spawn(process.execPath, [".next/standalone/server.js"], {
  stdio: "inherit",
  env: { ...process.env, PORT: port, HOSTNAME: "0.0.0.0", NODE_ENV: "production" },
});
for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => server.kill(signal));
}
server.on("exit", (code) => process.exit(code ?? 1));