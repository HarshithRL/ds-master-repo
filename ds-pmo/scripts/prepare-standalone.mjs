import { cpSync, existsSync } from "node:fs";

if (!existsSync(".next/standalone/server.js")) throw new Error("Standalone build is missing");
cpSync(".next/static", ".next/standalone/.next/static", { recursive: true });
cpSync("public", ".next/standalone/public", { recursive: true });