# One-Time PMO Volume Migration

## Completed DEV Snapshot

The 2026-10-19 export run `505652025820818` succeeded, including its actual import-validator task. The ZIP is ready at `/Volumes/automation_d/bronze/bronze_volume/pmo_app/PMO_pmo_initial_20261019.zip` (233,294 bytes). It contains all 18 tables and 4,142 rows, including 139 projects, 187 users, 167 factories and 1,800 audit rows. Every CSV count independently matched the recorded source Delta version. Source authorization is 5 ADMIN and 182 MEMBER, all active. All checked relationship-reference counts are zero missing. Data has not been applied to app tables.

Use this exact import approval hash:

```text
07ec01659fe5364a690a3b2e4bd55eac7d67d4d7faf8006d7515807842b65630
```

Full receipt: [EXPORT_RECEIPT.json](EXPORT_RECEIPT.json). The initial failed run stopped before writing files due to the Databricks task wrapper not defining `__file__`; deployed tasks now supply `--migration-root` explicitly and the successful run exercised that execution path. Do not rerun export with the same snapshot name: the completed immutable package already exists. Use the separate import job for validation/apply.

## What Moves

All 18 source tables in `engineering_global_pmo_s.pmo` are captured into typed UTF-8 CSV files plus a manifest. Each source Delta version, column/type/nullability, row count, byte count and SHA-256 is recorded. Source IDs, users, permissions, project relationships, historical audit rows and NULL values are preserved. `users.email_verified` is retained; the single app-specific alias is `project_snapshots.current_bac` to `PMO_project_snapshots.current_b_a_c`.

The format is `pmo-json-cell-csv-v1`: each CSV cell contains a JSON scalar, with timestamps stored as UTC microsecond strings. This avoids conflating NULL, empty strings, literal `null`, embedded JSON, commas and multiline text. Download/copy the ZIP unchanged; do not open and resave the CSVs in Excel, which can change IDs/dates/formulas and invalidate the hashes. The ZIP is portable and contains only the manifest and 18 PMO CSVs at its root. No model, OCR service or external storage is called.

## Export In DEV

`PMO - One-Time Export To DEV Volume` is defined only for the D target. Its source access never ships as a runnable extraction job in A/P. Neither deployment nor setup automatically runs this export.

Run from the project bundle directory:

```bash
databricks bundle run pmo_export --target D --profile DEFAULT
```

Default snapshot: `pmo_initial_20261019`. For a fresh capture use a new simple snapshot name in the job parameters; existing captures are never overwritten. Pause edits in the original app during capture. Export pins all 18 Delta versions and refuses publication if any table version changed during collection. This is a version-pinned capture, not a cross-table transactional lock.

The export job's second task, `validate_export`, reads the produced package through the actual import validator on the same cluster. It performs read-only target preflight; it never applies data. If export succeeds but this second task fails, the ZIP can exist while import is not yet accepted. Inspect both task results rather than equating a file's existence with successful validation.

The default output is:

```text
/Volumes/automation_d/bronze/bronze_volume/pmo_app/PMO_pmo_initial_20261019.zip
/Volumes/automation_d/bronze/bronze_volume/pmo_app/pmo_initial_20261019/manifest.json
/Volumes/automation_d/bronze/bronze_volume/pmo_app/pmo_initial_20261019/PMO_<table>.csv
```

Job output reports the ZIP checksum and the approved `manifest_sha256`, plus table counts and authorization-role counts. No record-level data or credentials are printed.

## Copy To Each Environment

Download the ZIP from the DEV volume. Upload that exact ZIP, without renaming, into each existing folder:

| Target | Existing Folder |
| --- | --- |
| D/T | `/Volumes/automation_d/bronze/bronze_volume/pmo_app/` |
| A | `/Volumes/automation_a/bronze/bronze_volume/pmo_app/` |
| P | `/Volumes/automation_p/bronze/bronze_volume/pmo_app/` |

The import job prefers `PMO_<snapshot>.zip`. Alternatively copy the entire `<snapshot>` folder with manifest and all 18 CSVs unchanged. Upload only one consistent package form; a ZIP takes precedence if both exist. A/P never read the original source catalog or DEV volume. They read their own catalog's volume only.

## Promote And Import

Promote the project source through the established Azure DevOps pipeline. The bundle explicitly includes `resources/jobs/pmo_migration.job.yml`; shared pipeline files do not change. `PMO - One-Time Import From Volume` is available in D/T/A/P, with no schedule or automatic data load.

In the target workspace, open the job and choose **Run Now With Different Parameters**:

| Parameter | First Run | Approved Import |
| --- | --- | --- |
| `snapshot` | `pmo_initial_20261019` | same |
| `mode` | `validate` | `apply` |
| `manifest_sha256` | exported manifest hash, recommended | exported manifest hash, required |
| `accept_user_authorization` | `false` | `true`, only after reviewing source roles |

Always validate first. All CSV checksums, row counts, schemas, ID uniqueness, current child relationships and user permissions are checked before target mutation. Missing historical audit/snapshot/editor references are counted and preserved, not silently removed. Actual source role counts are in the export receipt; importing users does not grant account/workspace/app/warehouse access or change the central consumer manifest.

Apply requires explicit approval of the manifest hash AND source user authorization. The snapshot contains existing ADMIN/MEMBER assignments and active flags. Do not apply if those users/roles are not approved in the target. It requires that the configured initial admin remains an active ADMIN in the package.

The import creates only missing `PMO_*` Delta tables in the existing `silver` schema. Existing tables may receive only the reviewed compatibility changes: nullable `users.email_verified` and source-compatible nullable user permissions/project JSON/confidentiality columns. No catalog, schema, volume or grants are created. Original NULL confidentiality flags remain NULL, matching the existing application's interpretation; no values are invented.

The target must be empty or contain only rows that are already byte/value-equivalent to this approved snapshot. The only replacement is an untouched setup-generated initial admin, with no other target rows, replaced atomically in the users-table MERGE by the original source admin ID. An edited/used bootstrap account, unrelated records or changed rows stop the import. Existing business data is never updated, truncated or overwritten.

Each table is reconciled in both directions after its MERGE. A receipt at `_PMO_initial_migration_<catalog>.json` tracks completion. A failed multi-table import is not atomic: some earlier tables may be committed. Keep the app in a maintenance window and rerun the SAME snapshot/hash; matching partial rows are preserved and only missing IDs are inserted. A different snapshot or edits to imported rows are refused. Restore the same receipt from backup if it was damaged; do not delete the marker to bypass a guard.

Run this only once per catalog. D and T share `automation_d` and therefore the same data and receipt. Do not run the D and T migration jobs concurrently. Stop application writes and do not perform manual table/DDL changes during validation/apply. After success, verify UI/API totals and project samples before consumer onboarding.

## Job Identity Permissions

The export identity needs USE CATALOG/USE SCHEMA and SELECT on all original source tables, plus READ_VOLUME/WRITE_VOLUME on the DEV existing bronze volume and USE privileges on its parents. It must be allowed to run the configured job compute policy.

The import identity needs USE CATALOG/USE SCHEMA on its own automation catalog, READ_VOLUME/WRITE_VOLUME on its own existing bronze volume (WRITE for the receipt), CREATE TABLE on its existing silver schema for missing tables, SELECT/MODIFY on PMO tables and ownership/MANAGE needed for the narrow compatibility DDL. These are deployment/job privileges, not app consumer privileges. An administrator must provision them through the approved platform process. This code does not grant them.

Volume ACLs apply to the whole shared volume, not just `pmo_app`. Treat the ZIP as confidential because it includes users, permission assignments and business data. Store and remove copies according to the approved retention process.

## Validation

```bash
python -m unittest discover -s tests -p test_migration.py -v
npm run schema:check
databricks bundle validate --target D --profile DEFAULT
```

The local codec and orchestration suite requires only the Python standard library. Spark functions are exercised in the actual Databricks job, not emulated by local package versions. The default import is read-only; apply requires manual owner approval.