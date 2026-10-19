# PMO Deployment And Security

## Source And Environments

Adapted from the DEV `DashboardTesting` application. The original source folder and its data are unchanged. The existing Next.js UI, portfolio calculations, project roles and admin modules are retained. This project is an independent bundle discovered by the existing DS-Master-Repo shared pipelines. Do not deploy the local editor-only bundle in the parent directory.

| Target | Catalog | Warehouse | App |
| --- | --- | --- | --- |
| D | automation_d | 69ada62b2fb9b9e2 | ds-pmo-dev |
| T | automation_d | 69ada62b2fb9b9e2 | ds-pmo-test |
| A | automation_a | 0ef3e37fbbd5b772 | ds-pmo |
| P | automation_p | f500d0d670ae024b | ds-pmo |

D and T share the same DEV tables intentionally. T is not a separate data sandbox. All 18 managed Delta tables are `automation_<env>.silver.PMO_<logical_name>`. Unity Catalog normalizes identifiers to lowercase in metadata. No catalog or schema creation is performed. Deployment does not automatically copy original data or create fictitious references. The manual initial-data workflow is documented in [migration/README.md](migration/README.md): DEV-only extraction to the existing bronze volume, then an environment-local validated import. There are no bronze/gold tables without a business requirement.

The bundle explicitly includes the app and setup job YAMLs. Its direct deployment engine and `lifecycle.started: true` build and start the app during bundle deployment. This was verified on DEV; a resource registration alone is not runtime acceptance. The CI agent needs a Databricks CLI with direct-engine app lifecycle support (verified locally with 1.9.0); upgrade the central agent if it rejects these fields. Shared pipeline YAMLs were not changed. The external Foundations template could not be retrieved with the current Azure DevOps credentials, so its CLI version is not certified here.

## Rollout Order

1. Promote this project using the existing shared pipeline. ACC/PRD changes are made by the owner, not by local DEV validation.
2. For initial data, follow the volume workflow in [migration/README.md](migration/README.md): upload the approved ZIP to the target's own existing `bronze_volume/pmo_app` folder, run `pmo_import` with `mode=validate`, review its report, then run `mode=apply` with the approved manifest hash and explicit source-user authorization approval. It creates only missing PMO tables and refuses unrelated/changed target rows. The separate `pmo_setup` job remains available for an empty installation with only the initial admin; setup alone does not load business data. All setup/import jobs are manual and unscheduled.
3. Verify all 18 target tables exist before the central consumer reconciliation. Setup is additive and rerunnable, not transactional across tables. It never replaces tables, removes rows, or reactivates/elevates an existing user. Existing incompatible schemas require a separately reviewed migration; IF NOT EXISTS is not a schema migration.
4. The root `permissions/access.json` adds only data product `pmo`, initially with Arda in READ and WRITE. Existing products are preserved. The CENTRAL access pipeline provisions groups and table grants for ACC/PRD; this source change does not itself apply grants or create users in the Databricks account. Keep tables-first ordering because central reconciliation can apply partially on failure.
5. The manifest uses `warehouse: false` because these are the existing shared automation warehouses supplied by the owner. A platform administrator must grant each intended consumer CAN_USE on the correct existing warehouse. The central manifest does not grant access to an arbitrary existing warehouse, and adding an app resource would only authorize its service principal, not the visitor.
6. Once both groups and their table/warehouse grants are verified, add `resources/apps/consumer.permissions.yml` to the explicit include list and promote again. That file is intentionally not included before group provisioning, avoiding a failed initial deployment on absent groups. The app remains manager-only until then.
7. Sign in via Entra, approve the SQL user scope, and perform browser acceptance with separate admin, reader, project editor, inactive and unregistered users. Verify API 401/403, assignment scoping, confidential projects, CRUD, and audit output.

## Authorization Model And Boundaries

Every SQL query uses the visitor's delegated `x-forwarded-access-token`, never a PAT or app service-principal fallback. The `sql` user scope is enabled in the app resource. SQL clients are request-local and closed for API handlers and server-rendered pages. The expected host, catalog, silver schema and warehouse must match before connecting.

Identity requires a Databricks Apps forwarded Etex email and an active, pre-provisioned PMO_users record. Unknown users are denied; there is no auto-enrollment. Every request reads current roles, so deactivation and demotion take effect on the next request without the old 45-second privilege cache. Read-only login does not write last-login metadata. The setup job inserts only the configured initial administrator when absent. Add other users explicitly through the administrator UI and provision their UC/warehouse/app access separately. Being listed in either system alone is insufficient.

ADMIN can manage the portfolio and user directory. EXECUTIVE and project MEMBER permissions retain the original project assignment and scope checks. The Databricks Apps proxy is the trusted boundary for forwarded identity headers; do not expose the Node server as an independently reachable public service.

IMPORTANT: these project restrictions are application checks, not Unity Catalog row filters. READ consumers can query every PMO table they have SELECT on directly, regardless of UI project confidentiality. WRITE consumers have direct MODIFY, including user roles and assignments, so WRITE membership is suitable only for fully trusted PMO administrators. It must not be used as the generic project-editor group. Do not onboard restricted/confidential-project readers or ordinary project editors under these broad grants until the platform owner approves this trust model or adds database-enforced row/column policies and separate protected authorization-table grants. Never claim the UI hides data from direct SQL users.

## Remaining Data Integrity Limits

The source application implements relational workflows over Delta tables. Cross-table writes and DELETE-then-INSERT replacements are not atomic transactions, and email/code/assignment uniqueness checks are not enforced unique constraints. Concurrent writers may conflict or create duplicates. Setup and application validation do not remove these limitations. Review transactional storage or database-enforced integrity before a high-concurrency rollout. Audit rows use the caller's SQL identity, not an independently immutable audit sink.

No confidential content was sent to an LLM or external document service. The source uses Resend for transactional notifications; notifications stay disabled and no mail secret is copied until the enterprise owner approves and provisions that service. Existing external flag images are retained from the source UI.

## Checks And DEV Receipt

Use Node 22 and the committed lockfile: `npm ci`, `npm test`, `npm run schema:check`, `node --experimental-strip-types --test tests/table-names.test.mjs`, `npm run build`. Generate reviewed SQL changes with `npm run schema:generate`; the generator uses the TypeScript AST and the same camel-to-snake column convention as the repositories, including acronym fields. Asynchronous SQL writes now await the driver's `finished()` result before closing, propagating server-side errors instead of returning early.

The opt-in native DEV tests verify the actual application SQL driver, expected warehouse identity, all 18 tables, a single active bootstrap admin after repeated setup, and an inserted/read/deleted probe in PMO_resources. The probe was removed and its absence verified. These CLI-backed data-layer checks do not replace browser user-consent and role acceptance with separate identities.

Security validation on 2026-10-19 updated the lockfile within declared major-version ranges, including Next.js 16.4.2 and Databricks SQL 2.2.0. Targeted overrides pin get-uri's basic-ftp to 6.2.3 and ExcelJS's uuid to 11.1.1. A real XLSX conditional-formatting serialization/readback test and the native DEV SQL roundtrip passed with these versions. Clean `npm ci` with Node 22/npm 10, production build/typecheck, 116 unit tests, 4 table-name checks and 3 opt-in native checks passed; `npm audit --omit=dev` reported zero vulnerabilities. This is an advisory snapshot, not a guarantee against future vulnerabilities. Some upstream packages still emit deprecation warnings.

DEV app: https://ds-pmo-dev-7181820732839861.1.azure.databricksapps.com

DEV setup job: 704993786902650. Initial run 164165342789024 and idempotency run 816369928194313 both succeeded on 2026-10-19. Native warehouse metadata independently returned all 18 PMO tables. The app deployment succeeded and app status is RUNNING with `user_api_scopes: [sql]`. Authenticated browser acceptance remains pending because the integrated browser requires the owner's Entra sign-in. No ACC/PRD deployment, table creation, permission apply, commit or push was performed.

## Dashboard Runtime Fix And Actual Data Population

The owner's first authenticated dashboard request failed with ERR_INVALID_URL. Actual Databricks Apps logs showed DATABRICKS_HOST was the bare hostname `adb-7181820732839861.1.azuredatabricks.net`, not the full HTTPS URL used in the initial native test. The connection resolver now accepts both forms, normalizing a bare hostname to HTTPS before enforcing the same known-workspace/catalog/schema/warehouse checks. The native SQL test now uses the observed runtime form. Do not treat RUNNING/build success as proof of successful authenticated page rendering.

After this correction, 119 unit tests, three native DEV SQL checks and production build/typecheck passed. `PMO_NATIVE_DEV_HTTP_TEST=true node tests/native-dev-http.mjs` additionally starts the built production server on loopback, injects the current engineer's DEV token only inside test requests, verifies authenticated /dashboard HTML and /api/portfolio, /api/projects and /api/filter-options responses, verifies tokenless API access is 401, then stops the server. These checks passed against real DEV SQL, but do not substitute for Databricks Apps proxy/user-consent acceptance in the owner's browser.

Pre-import count-only queries on 2026-10-19 found the target has zero PMO_projects, zero PMO_factories, zero PMO_resources and one initial PMO_users administrator. The original source configuration targets `engineering_global_pmo_s.pmo`, with 139 projects, 187 users, 167 factories and 14 resources. The new app does NOT read that original catalog. The added extraction job writes a portable snapshot only, without modifying the source or applying target data. The separate import preserves project IDs and child relationships and requires explicit approval of source roles/activation before applying users. No recurring cross-catalog ingestion is configured, and exporting a snapshot alone does not populate the app.

The requested DEV volume snapshot is now complete: run `505652025820818` succeeded with both export and real import-preflight tasks. The 233,294-byte ZIP contains 18 tables / 4,142 rows. Independent downloaded-file validation and native SQL counts against all recorded Delta versions matched. Import validation reported the reviewed compatibility DDL and pristine bootstrap replacement without executing them. See [migration/EXPORT_RECEIPT.json](migration/EXPORT_RECEIPT.json) for exact hashes/counts and [migration/README.md](migration/README.md) for target upload/run steps. Twenty migration tests and 119 existing app tests passed. Neither DEV app-data apply nor ACC/PRD mutation was performed.