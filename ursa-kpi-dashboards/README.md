# URSA PS4 Daily KPI Tracker

Independent Databricks Asset Bundle in DS-Master-Repo, following the current
`industry-sales-dashboards` deployment and result-materialization pattern.

## Ownership and Scope

- Bundle: `ursa-kpi-dashboards`.
- Original dashboard: `/Users/kerem.yenideniz@etexgroup.com/URSA PS4 Daily KPI Tracker.lvdash.json`.
- Original dashboard ID: `01f1c64b4d221e24ad538c8f31226e41`.
- Source snapshot: `source_dashboards/ursa_ps4_daily_kpi_tracker.lvdash.json`.
- Seven datasets, fourteen pages and fifty widgets are retained, including
  Mock/Test pages and the dataset not directly referenced by a widget.
- Only dataset SQL is replaced. Widget definitions, filters, calculated dataset
  columns, page layout and presentation metadata are preserved.
- No catalog, schema, volume or consumer group is created by this bundle.
- All persistent relations use the `URSA_KPI_` prefix in the existing
  `bronze`, `silver` and `gold` schemas of the selected automation catalog.

## Data Flow

The refresh job reads fifteen `synapse-prd.pbi` relations through explicit
projections of eighty-one required columns. These include join, filter,
grouping and calculation inputs. The native DEV metadata check found 1,477
available source columns; no wildcard or full-table copy is used.

Source projections are lazy session views, not persisted source snapshots.
The original filtering, joins and calculations produce the seven final dataset
results. Only these computed results are materialized:

1. Final dataset frames are durably staged under the existing
   `/Volumes/<catalog>/bronze/bronze_volume/URSA_KPI/<target>/<batch>/` directory.
2. Seven Delta tables in `silver` retain the result rows and a batch marker.
3. Seven views in `gold` expose explicit result columns for the active batch.
4. `gold.URSA_KPI_result_state` selects the published batch.
5. `bronze.URSA_KPI_refresh_audit` records start, failure and publication events.

Dataset result relation names in both `silver` and `gold`:

```text
URSA_KPI_result_ursa_kpi_data
URSA_KPI_result_test_invoiced_value
URSA_KPI_result_hypercare_mock
URSA_KPI_result_hc_baseline
URSA_KPI_result_hc_actuals_vs_baseline
URSA_KPI_result_hc_matrix_formatted
URSA_KPI_result_o2c_live_matrix
```

There are nine tables and seven views. Target D adds `_dev` to every persistent
relation name, including the state and audit tables. T uses the unsuffixed names
in `automation_d`; A and P use `automation_a` and `automation_p` respectively.

## Publication Guarantees

The job checks the actual Spark workspace ID against its target and automation
catalog before executing SQL. It describes the existing schemas, validates
native source projections and checks Volume write/read capability.

Every dataset is staged once and read back, appended to its silver Delta table,
and compared in both directions with `EXCEPT ALL`. Consumer SQL, including
`ORDER BY`, is analyzed against the new staged result before publication.
The known nonempty mock/master spines cannot publish empty results. The live
billing test dataset is allowed to have no matching invoices.

Only a complete set of seven verified receipts can change the single publication
pointer with `INSERT OVERWRITE`. Existing views use `ALTER VIEW AS`, not
`CREATE OR REPLACE VIEW`, to retain consumer grants. Existing objects must carry
the bundle's ownership property before they can be modified. Schema changes fail
closed and require an explicit migration.

Failed unpublished batches do not replace the prior successful batch. A successful
run retains the current and previous result batches. A cleanup warning after
publication is logged separately and does not pretend that publication rolled
back. Initial installation is not an all-object transaction; until the first
successful publication, newly created views have no active result batch.

The business date is frozen once per materialization run. This is atomic
publication of computed outputs, not a transactional point-in-time snapshot of
all independent live Synapse relations.

## Source Acceptance Caveats

This bundle productizes the supplied dashboard, not a redesigned or certified
URSA KPI model. Source semantics are intentionally unchanged:

- `ursa_kpi_data` contains generated mock values for 12-18 October 2026.
- `hypercare_mock` and associated matrix datasets contain inline mock values,
  including the 2-8 November 2026 display window.
- `hc_baseline` contains manually supplied inline Oct-Dec 2025 baseline values;
  these are not recomputed from historical Synapse data.
- `test_invoiced_value` uses pilot company codes 6700, 6740 and 6760 and preserves
  the original currency-conversion fallback.
- `o2c_live_matrix` uses the original Skamol pilot plant/company map, not an
  approved complete URSA plant map. Its rolling seven-day date window is retained.
- The live matrix retains its original zero baseline, explicit placeholder KPIs,
  missing-match-to-zero rules and `1970-01-01` source-marker predicates.
  A displayed zero is not independent evidence of absent operational activity.

Business owners must approve the real URSA plant/company scope, baseline rules,
placeholder KPIs and Mock/Test page disposition before operational go-live.
Do not silently replace these rules or describe mock outputs as live URSA KPIs.

## Job and Schedule

Resource key: `ursa_kpi_refresh`.

```text
preflight_sources -> materialize_results -> verify_dashboard_results
```

The job uses the existing per-workspace Job Compute policy, Runtime 16.4,
Photon and a one-to-two-worker cluster. The overall timeout is two hours;
preflight includes a twenty-minute startup/library allowance. Automatic retries
are disabled so incomplete attempts remain explicit.

A daily 06:30 Europe/Brussels schedule is **UNPAUSED for A/P** at the user's
request and **PAUSED for D/T**. The A/P schedule becomes active when the updated
bundle is deployed through the normal pipeline. No live ACC/PRD schedule was
changed directly. Source-scope acceptance and target access checks remain
required; enabling a schedule does not certify the source business rules.

## Build and DEV Validation

Use an isolated Python environment outside Desktop/Documents:

```bash
python -m pip install -r requirements-dev.txt
python scripts/build_bundle.py
python scripts/build_bundle.py --check
python -m unittest discover -s tests -v
databricks bundle validate --target D --profile DEFAULT
databricks bundle deploy --target D --profile DEFAULT
databricks bundle run ursa_kpi_refresh --target D --profile DEFAULT
```

The build deterministically regenerates `src/config/dashboard_plan.json` and
`resources/dashboards/ursa_ps4.dashboard.yml`. Source archive, tests and scripts
are committed for review but excluded from runtime sync. The runtime receives
`--config-path` explicitly and does not depend on `__file__` being defined by
the Databricks Python task wrapper.

## Manual DEV UI Capture

The manual `Sync_URSA_Dashboard_To_Bundle` notebook lives outside this bundle at
`/Workspace/Users/mustafaarda.bicakci@etexgroup.com/DEV-Tools/`.
It is not a job, is not scheduled, and is not included in ACC/PRD deployments.
The local notebook is `dev_tools/sync_ursa_dashboard.ipynb` in the development
workspace, also outside the bundle project.

The notebook defaults to the bundle's DEV dashboard
`01f1ccc9fb9c1806b7de5a73ac5154fa`. The original Kerem dashboard can be selected
explicitly if its dataset SQL still matches the archived source contract.
It reads the current draft, not a possibly older published revision.

1. Edit the selected DEV dashboard's presentation in the UI.
2. Run the notebook through Cell 8 to preview and validate the proposed changes.
3. In Cell 10, set `APPLY_CHANGES=True` and set `CONFIRMATION` to that preview's
  approval value. Rerun Cell 10 to apply. The default remains preview-only.
4. Review the DEV Git folder diff, then commit/push and promote through the
  existing PR/pipeline process. The notebook does not commit, push or deploy.

Capture writes only `source_dashboards/dashboard_presentation.json` and
`resources/dashboards/ursa_ps4.dashboard.yml`. The build now consumes the
optional presentation file so captured visuals survive regeneration, while
the archived source SQL and `src/config/dashboard_plan.json` remain unchanged.
New pages/widgets and expressions over existing result columns are supported;
dataset SQL/inventory and relationship-graph changes require separate review.
DEV result addresses are replaced by the existing catalog/suffix placeholders.

The authenticated server must confirm the DEV workspace ID. Branch/head, source
bytes, dashboard etag and native result schemas are rechecked before writes.
Original files are backed up outside the repo under
`DEV-Tools/URSA_Dashboard_Backups`, and uploads are read back byte-for-byte.
Workspace file writes have no cross-file transaction or server-side CAS lock:
a partial failure stops with the backup path and requires review before commit.
The notebook never modifies the live dashboard, data tables, job, schedules,
permissions, warehouse bindings or shared pipeline files.

## ACC and PRD Promotion

Add this folder to the current DEV Git folder and use the existing shared Azure
DevOps pipeline. No shared pipeline file or existing product needs modification.
No direct ACC/PRD deployment is part of this implementation.

1. Review and commit/push the DEV source using the established team process.
2. Promote the bundle through the existing T/A/P pipeline stages.
3. Verify target job identity privileges on the fifteen foreign sources and the
   existing automation schemas/Volume. Foreign consumer access is not required.
4. Run the target refresh job successfully and verify all sixteen relations and
   seven native dashboard result receipts exist before consumer reconciliation.
5. Provision approved consumer membership and `SELECT` on the seven gold result
   views using the root `permissions/access.json` process. Provision foreign
   job-identity grants through the Foundation/Terraform-owned process.
6. Verify workspace groups, SQL warehouse `CAN_USE`, dashboard `CAN_READ` and
  the authenticated browser rendering. A/P schedules are enabled by deployment,
  so complete initial refresh and access acceptance before the first daily run.

No consumer members were supplied, so this bundle does not invent memberships,
change the shared permissions manifest, or bind nonexistent groups during the
initial deployment. Managers use the existing Arda/Pierre bundle convention.
Dashboard credentials are not embedded: consumers require their own appropriate
automation data, warehouse and dashboard permissions, but no Synapse access.

Read-only DEV metadata checks are not proof of future ACC/PRD service-principal
grants, consumer access or rendered widget correctness. A failed central
reconciliation may still remove old grants; always create and verify target
objects before submitting replacement consumer declarations.

See `RELEASE_STATUS.md` for the executed validation and native DEV evidence.