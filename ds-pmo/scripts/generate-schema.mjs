import ts from "typescript";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = fileURLToPath(new URL("../", import.meta.url));
const models = ts.createSourceFile("models.ts", readFileSync(path.join(root, "src/lib/db/models.ts"), "utf8"), ts.ScriptTarget.Latest, true);
const tables = {
  User: "users", Division: "divisions", Factory: "factories", Category: "categories", Resource: "resources",
  Project: "projects", ProjectAssignment: "project_assignments", ScopeGrant: "scope_grants", Budget: "budgets",
  BudgetLine: "budget_lines", GateRecord: "gate_records", Risk: "risks", Milestone: "milestones",
  PlannedAction: "planned_actions", ScopeChange: "scope_changes", ProjectDocument: "project_documents",
  ProjectSnapshot: "project_snapshots", AuditLog: "audit_logs",
};
const integerFields = new Set(["year", "sortOrder", "riskNumber", "ridsOpen", "redFlagsOpen", "risksIssuesCount", "risksHighCount", "risksModerateCount", "risksLowCount", "risksIdentifiedCount", "risksQuantifiedCount", "openRiskCount", "openIssueCount"]);
const nullableSourceFields = new Set(["User.permissions", "Project.wbsCodes", "Project.flags", "Project.isConfidential"]);
const statements = [
  "SELECT assert_true(:catalog IN ('automation_d', 'automation_a', 'automation_p'), 'Unsupported PMO catalog');",
  "SELECT assert_true(lower(:initial_admin_email) RLIKE '^[^@\\\\s]+@etexgroup[.]com$', 'Initial admin must be an Etex identity');",
];
const contract = { version: 1, tables: {} };
const covered = new Set();
for (const declaration of models.statements) {
  if (!ts.isInterfaceDeclaration(declaration) || !tables[declaration.name.text]) continue;
  const entity = declaration.name.text;
  covered.add(entity);
  const tableColumns = [];
  const columns = declaration.members.filter(ts.isPropertySignature).flatMap((member) => {
    const field = member.name.getText(models);
    const variants = ts.isUnionTypeNode(member.type) ? member.type.types : [member.type];
    const nullable = variants.some((variant) => variant.getText(models) === "null") || nullableSourceFields.has(`${entity}.${field}`);
    const actual = variants.find((variant) => variant.getText(models) !== "null");
    const type = actual.getText(models);
    const sqlType = type === "Date" ? "TIMESTAMP" : type === "boolean" ? "BOOLEAN" : type === "number" ? (integerFields.has(field) ? "INT" : "DOUBLE") : "STRING";
    const column = field.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`);
    tableColumns.push({ name: column, sql_type: sqlType.toLowerCase(), nullable });
    return [`  ${column} ${sqlType}${nullable ? "" : " NOT NULL"}`];
  });
  contract.tables[tables[entity]] = tableColumns;
  statements.push(`CREATE TABLE IF NOT EXISTS IDENTIFIER(:catalog || '.silver.PMO_${tables[entity]}') (\n${columns.join(",\n")}\n) USING DELTA;`);
}
if (covered.size !== 18) throw new Error(`Expected 18 PMO model contracts, found ${covered.size}`);
statements.push(`MERGE INTO IDENTIFIER(:catalog || '.silver.PMO_users') AS target
USING (SELECT lower(:initial_admin_email) AS email) AS source
ON lower(target.email) = source.email
WHEN NOT MATCHED THEN INSERT (id, email, name, image, global_role, permissions, is_active, last_login_at, created_at, updated_at)
VALUES (uuid(), source.email, source.email, NULL, 'ADMIN', '[]', true, NULL, current_timestamp(), current_timestamp());`);
const generated = `${statements.join("\n\n")}\n`;
const output = path.join(root, "sql/setup_tables.sql");
const contractPath = path.join(root, "migration/table_contract.json");
const generatedContract = `${JSON.stringify(contract, null, 2)}\n`;
if (process.argv.includes("--check")) {
  if (readFileSync(output, "utf8") !== generated) throw new Error("PMO SQL schema does not match application models");
  if (readFileSync(contractPath, "utf8") !== generatedContract) throw new Error("PMO migration contract does not match application models");
  console.log("All 18 PMO table contracts match application models");
} else {
  mkdirSync(path.dirname(output), { recursive: true });
  writeFileSync(output, generated);
  mkdirSync(path.dirname(contractPath), { recursive: true });
  writeFileSync(contractPath, generatedContract);
  console.log("Generated 18 PMO table contracts");
}