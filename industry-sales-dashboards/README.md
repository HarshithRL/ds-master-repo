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

The upstream source is the shared read-only `synapse-prd.pbi` catalog. Only the job identity reads it; neither dashboard definition requires consumers to query that catalog. Foundation/Terraform manages access to this upstream catalog. The consumer access pipeline manages only the target automation catalog; no fixed foreign catalog is added to its manifest.

## Data And Refresh

The 108-row CS-team mapping was captured completely from `supply_chain_sandbox_d.datamodel.cs_team_sales_org_mapping`. The versioned JSON seed preserves every string value, including sales organization identifiers. Runtime jobs have no dependency on that DEV sandbox.

The refresh validates existing schemas and source access, publishes the seed through bronze, silver, and gold, and independently verifies exact write/read parity at each layer. Only tables tagged `industry_sales.bundle=industry-sales-dashboards` can be replaced. The gold mapping is `industry_sales_cs_team_sales_org_mapping`; D uses the `_dev` suffix so development does not claim TEST's tables. The mapping is release-managed configuration, not a live synchronization from the sandbox. Changes require a new verified capture and release.

The job contains three table-production tasks: mapping, source snapshots, then allocation materialization. A failed prerequisite prevents later production; job concurrency is one. The existing A/P schedule remains 06:30 Europe/Brussels daily, and D/T stay paused. The two Spark Python tasks use `sqlglot==27.20.0`; no schemas are created.

`snapshot_dashboard_sources` copies all rows from the 14 required source tables, without date filters, deduplication, quantity transformations, or a substitute source catalog. The generated `source_snapshots.json` lists required columns; ambiguous/wildcard projections retain every source column instead of silently omitting fields. In the current plan the sales-document fact retains all 297 columns. This is a full daily transfer, not incremental CDC, so first-run volume, processing time, storage cost, and source-owner approval must be measured in DEV before promotion.

Each raw bronze Delta table is named `industry_sales_raw_<source-table>`. It uses name-based Delta column mapping to preserve native column names and an internal batch marker. Matching silver views are `industry_sales_src_<source-table>` and expose only original source columns from the batch selected by `gold.industry_sales_source_snapshot_state`. D appends `_dev` to all those objects; T/A/P use the unsuffixed names in their target catalogs. The state pointer advances only after every source's write/read multiset parity check succeeds. A failed partial batch leaves the previous completed batch visible. The current and previous successful batches are retained; older/unpublished rows are removed after a successful publication. No VACUUM is performed. Schema changes require an explicit reviewed migration, rather than automatic overwrite.

The 14 upstream reads are sequential, so the copied batch is not a single transactionally consistent Synapse point-in-time snapshot. The batch guarantees complete publication of the collected sources, not upstream cross-table atomicity. During initial setup, views must not be considered usable until the first batch completes. Cleanup retains one prior batch for in-flight readers; a query spanning more than one later publication needs separate operational handling.

The `materialize_open_orders_allocation` task runs the original allocation SQL's 18 CTEs once over the local inputs, with eager checkpoints to truncate repeated plans. It pins the raw inputs to the completed batch ID and business date, and refuses publication if the pointer changes during the calculation. It replaces only its bundle-owned gold output.

The native `refresh_open_orders` and `refresh_quotations` tasks remain removed. The scheduled job finishes when table production finishes; it does not precompute dashboard query caches or send native dashboard subscription snapshots. Both dashboard resources and their publication remain intact. Dashboard queries run interactively when needed; cached browser results may still require refresh. Moving sources local removes interactive foreign reads, but it is not a measured latency guarantee for every remaining query.

The Open Orders `ds_overview_allocation` dataset reads the six original result columns from `gold.industry_sales_open_orders_allocation`, with `_dev` appended for D. All other Open Orders datasets and all Quotations datasets reference the local silver snapshots. Their original business expressions, measures, pages, widgets, filters, and parameter handling are preserved. `open_orders_allocation.sql` also references those local inputs. `allocation_as_of_date`, `allocation_refreshed_at`, and `source_snapshot_id` identify the allocation output. Other interactive queries retain original CURRENT_DATE logic while reading copied data; changing the clock does not make the snapshot current.

A failed source transfer retains the prior source batch. If source publication succeeds but allocation fails, silver views can represent the new source batch while gold allocation remains the previous batch. Compare the state and allocation dates/IDs before treating the dashboard as a synchronized current view. Snapshot freshness must be reviewed operationally; a successful deployment is not a successful first transfer.

The local inputs do not exist merely because the bundle is deployed. The source task must succeed before the 14 views are usable, and allocation must succeed before its gold dataset can load. Readers need SELECT on the silver views and gold outputs, not the raw bronze copies or snapshot state. Existing mapping grants remain. This change removes the direct-source permission dependency for both dashboards; live viewer access and latency still need testing.

If an upstream table is empty, its exact empty snapshot is allowed rather than invented data. The allocation producer still refuses to replace its previous output with an empty result. Source schema drift fails before that batch is published. First-run raw/source views and empty state may exist after a failed attempt, but they are not evidence of a complete batch.

Dashboard credentials are not embedded. Existing explicit readers and editors are retained, along with Master Repo maintainers and Noel. The Industry Sales READ group containing Francois, Noel, and Arda receives automation USE CATALOG, USE SCHEMA, SELECT on its mapping/allocation outputs, and SELECT on the 14 silver views through `permissions/access.json`. The owner of each silver view needs access to its raw bronze/state dependencies so Unity Catalog can evaluate the view. Viewers also require warehouse access and dashboard permissions; neither group membership nor a dashboard ACL alone proves all prerequisites.

## Master CI Release

This is a new top-level bundle under DS-Master-Repo. Shared TEST/ACC/PRD pipeline YAML is unchanged. The checked-in generated dashboard resources work with ordinary `databricks bundle deploy`; no custom Azure stage or generator hook is required. D uses a personal root. T/A/P use `/Workspace/automation/industry-sales-dashboards/<target>` and the existing CI deployment identities, which also own/run the job when deployed by CI.

1. Review and commit only this new project folder in the existing Master Git Folder. The local DS-Master-Repo directory is a partial workspace export, not a Git checkout.
2. Use the repository's TEST validation and ACC PR/build-validation flow, then merge to main for PRD. Do not deploy ACC/PRD as a human to bypass the protected automation root.
3. Ensure the CI identity has Foundation-managed source SELECT, target CREATE TABLE/CREATE VIEW and ownership/write rights in the existing schemas, warehouse use, and compute-policy use. Consumers do not need upstream Synapse access. Run the central consumer access pipeline after its target silver views exist; it must grant the declared views rather than a nonexistent foreign catalog.
4. Validate the full transfer in DEV first. After deployment, run `industry_sales_refresh` once and verify all three table-production tasks succeed, 14 sources have complete receipts, source/state and allocation batch IDs match, and dates are appropriate. Check published browser pages and a consumer with no Synapse access separately. A paused D/T schedule does not prevent a manual smoke run. Do not promote merely because source validation passes.

The helper explicitly publishes without embedded credentials and runs the first table-production job, not a native dashboard refresh:

```bash
bash scripts/deploy_and_publish.sh T <ci-profile>
```

Do not assume the shared external deployment template automatically invokes that helper or performs a successful first table build. The scheduled job owns subsequent mapping, local source, and allocation table updates. Dashboard opening and query execution are separate from that schedule. Source and permission changes are made only in DEV; the user commits and promotes them through the existing pipeline.

## Validation

Use an isolated environment with Java 17 for the local Spark equivalence tests. Install the pinned dependencies from `requirements-dev.txt` there, not over system Python. The ad hoc run/cleanup helpers enforce the exact DEV workspace and job; they do not accept ACC/PRD receipts. Source changes and validation are DEV-only; the user promotes through the established pipeline.

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m unittest discover -s tests -v
python3 scripts/render_dashboard_resources.py --check
databricks bundle validate --target D --profile DEFAULT
python3 scripts/preflight_sql.py D
python3 scripts/validate_snapshot_projections.py
```

The original-source preflight uses read-only `DESCRIBE QUERY` with an identical inline mapping seed and typed empty native filters. It requires engineer/source access and is not a consumer permission test. The projection validator reads DEV metadata only, builds empty local Spark schemas, and compares projected and full-source query schemas. Seventeen native queries matched; the original Decimal STACK and Databricks QUALIFY queries have identical baseline failures in local Spark and remain explicitly unverified there. Native Databricks execution must validate those two. These checks do not certify transfer runtime, source consistency, browser rendering, or viewer permissions. A canceled statement is not evidence of missing data. Reports live under ignored `validation/`.

`scripts/sync_master_repo.py` uploads only this project into the existing DEV Master Git Folder and byte-verifies every file. It neither commits nor pushes, and it is not an ACC/PRD deployment.

Original dashboard IDs: Open Orders `01f1b99401ce107e98453f33f5afefe2`, Quotations `01f1b9dbf7ea1d8483cdaa18dd976a80`. Raw metadata, ACLs, and the source SQL statement receipt are retained under `source_dashboards/` for exact preservation checks and excluded from runtime synchronization.