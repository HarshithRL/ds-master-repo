# Industry Sales Dashboards

Master-owned Databricks Asset Bundle for Noel Vranckx's Industry Division Open Orders CX Summary and Quotations Dashboard. Original DEV assets are not overwritten.

See [RELEASE_STATUS.md](RELEASE_STATUS.md) for verified deployment evidence and the remaining ACC/PRD release and runtime gates. This source is prepared for Master CI but is not yet an accepted production release.

## Environment Configuration

| Target | Workspace | Output catalog | Warehouse | Daily schedule |
| --- | --- | --- | --- | --- |
| D | DEV | automation_d | 69ada62b2fb9b9e2 | Paused |
| T | DEV/TEST | automation_d | 69ada62b2fb9b9e2 | Paused |
| A | ACC | automation_a | 0ef3e37fbbd5b772 | 06:30 Europe/Brussels |
| P | PRD | automation_p | f500d0d670ae024b | 06:30 Europe/Brussels |

Schemas are the existing `bronze`, `silver`, and `gold`. This project never creates schemas. Missing schemas, invalid workspace/target/catalog combinations, duplicate mapping keys, inaccessible sources, and non-bundle-owned destination tables fail the refresh.

The 14 source tables remain in the shared read-only `synapse-prd.pbi` catalog, verified visible in DEV, ACC, and PRD. Source catalog configuration is separate from output catalog configuration; do not mechanically rename a production Synapse federation to a nonexistent acceptance catalog.

## Data And Refresh

The 108-row CS-team mapping was captured completely from `supply_chain_sandbox_d.datamodel.cs_team_sales_org_mapping`. The versioned JSON seed preserves every string value, including sales organization identifiers. Runtime jobs have no dependency on that DEV sandbox.

The refresh validates existing schemas and source access, publishes the seed through bronze, silver, and gold, and independently verifies exact write/read parity at each layer. Only tables tagged `industry_sales.bundle=industry-sales-dashboards` can be replaced. The gold mapping is `industry_sales_cs_team_sales_org_mapping`; D uses the `_dev` suffix so development does not claim TEST's tables. The mapping is release-managed configuration, not a live synchronization from the sandbox. Changes require a new verified capture and release.

The tasks run in order: mapping, allocation materialization, Open Orders refresh, then Quotations refresh. A failed prerequisite prevents downstream refreshes; job concurrency is one. The new `materialize_open_orders_allocation` task runs the original allocation SQL's 18 CTEs once, with eager checkpoints to truncate repeated foreign-source query plans. Its parser dependency is pinned to `sqlglot==27.20.0` on that task only. It creates no schemas and replaces only its bundle-owned gold output.

The Open Orders `ds_overview_allocation` dataset reads the six original result columns from `gold.industry_sales_open_orders_allocation`, with `_dev` appended for D. All its measures and widgets stay unchanged; the exact original business SQL is versioned in `src/config/open_orders_allocation.sql`. Other datasets, including all Quotations queries, are unchanged. This is a daily snapshot, not a fresh foreign-source recomputation per widget. `allocation_as_of_date` and `allocation_refreshed_at` record its business date and write time. The business date is fixed at task start; a failed later refresh leaves the previous snapshot, which must not be treated as current.

The new snapshot table does not exist merely because the bundle is deployed. Its materialization task must succeed before the dataset can load. Readers need SELECT on this gold output as well as the existing mapping/source grants. This change targets allocation KPI query expansion; it does not certify other slow datasets or solve Quotations Conversion Rate performance.

Dashboard credentials are not embedded. Existing explicit readers and editors are retained, along with Master Repo maintainers and Noel. Viewers must have warehouse access and `USE CATALOG`, `USE SCHEMA`, and `SELECT` on their target gold mapping and the required source tables. Dashboard ACLs alone do not grant data access.

## Master CI Release

This is a new top-level bundle under DS-Master-Repo. Shared TEST/ACC/PRD pipeline YAML is unchanged. The checked-in generated dashboard resources work with ordinary `databricks bundle deploy`; no custom Azure stage or generator hook is required. D uses a personal root. T/A/P use `/Workspace/automation/industry-sales-dashboards/<target>` and the existing CI deployment identities, which also own/run the job when deployed by CI.

1. Review and commit only this new project folder in the existing Master Git Folder. The local DS-Master-Repo directory is a partial workspace export, not a Git checkout.
2. Use the repository's TEST validation and ACC PR/build-validation flow, then merge to main for PRD. Do not deploy ACC/PRD as a human to bypass the protected automation root.
3. Ensure the CI identity has source SELECT, target schema/table creation and ownership rights, warehouse use, Job Compute policy use, and the relevant workspace principals exist.
4. Validate the new materialization in DEV first. After deployment, run `industry_sales_refresh` once and verify all four tasks succeed, the allocation table has an appropriate business date, published browser pages render, and original readers have the required SELECT grants. A paused D/T schedule does not prevent a manual smoke run. Do not promote the unverified snapshot change to ACC/PRD just because source validation passes.

The helper explicitly publishes without embedded credentials and runs the first refresh:

```bash
bash scripts/deploy_and_publish.sh T <ci-profile>
```

Do not assume the shared external deployment template automatically invokes that helper or performs a successful first refresh. The native scheduled job owns subsequent ACC/PRD refreshes.

## Validation

Use an isolated environment with Java 17 for the local Spark equivalence tests. Install the pinned dependencies from `requirements-dev.txt` there, not over system Python. The ad hoc run/cleanup helpers enforce the exact DEV workspace and job; they do not accept ACC/PRD receipts. Source changes and validation are DEV-only; the user promotes through the established pipeline.

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m unittest discover -s tests -v
python3 scripts/render_dashboard_resources.py --check
databricks bundle validate --target D --profile DEFAULT
python3 scripts/preflight_sql.py D
```

Preflight uses read-only `DESCRIBE QUERY` with an identical inline mapping seed and typed empty native filters. It verifies source analysis, not dashboard runtime performance or browser rendering. A canceled statement is an unverified check, not evidence of an invalid query or missing data. Reports live under ignored `validation/`.

`scripts/sync_master_repo.py` uploads only this project into the existing DEV Master Git Folder and byte-verifies every file. It neither commits nor pushes, and it is not an ACC/PRD deployment.

Original dashboard IDs: Open Orders `01f1b99401ce107e98453f33f5afefe2`, Quotations `01f1b9dbf7ea1d8483cdaa18dd976a80`. Raw metadata, ACLs, and the source SQL statement receipt are retained under `source_dashboards/` for exact preservation checks and excluded from runtime synchronization.