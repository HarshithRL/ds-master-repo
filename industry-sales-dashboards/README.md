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

## Table Names And Count

Every product-owned table and published view uses the exact `SC_BI_` prefix. The simplified result-only workflow produces 24 physical tables and 20 views, totaling 44 distinct schema-qualified relations per target:

| Object | Layer | Count |
| --- | --- | --- |
| Mapping copies | bronze, silver, gold | 3 physical tables |
| Calculated result storage | silver | 20 physical tables |
| Completed result-batch state | gold | 1 physical table |
| Published dataset results | gold | 20 views |

Mapping is `SC_BI_industry_sales_cs_team_sales_org_mapping`; state is `SC_BI_industry_sales_dashboard_result_state`. Gold results start `SC_BI_industry_sales_<dashboard>_<dataset>_<component>`; their physical silver counterparts start `SC_BI_industry_sales_calc_`. The three identical quotation conversion components share `SC_BI_industry_sales_quotations_shared_converted`. D retains `_dev` after each base name. T/A/P use the unsuffixed names. Synapse source names, catalog/schema names, ownership property keys, task keys, and retained native widget/dataset identifiers are unchanged. Generated manifests, dashboard SQL, job table parameters, and all 44 permission object names share this contract.

This source rename does not rename, drop, migrate, or grant existing live objects. After the user promotes it through CI, the first successful data job creates/populates the prefixed objects; consumer grants must then be applied to those new names. Published definitions can refer to objects not yet created until that run completes. Old unprefixed objects remain untouched and are not automatically read as a fallback. This new-name initialization still needs source-frozen DEV runtime and viewer validation. Retained legacy helpers also use the prefix but are not additional active outputs or job tasks.

## Data And Refresh

The 108-row CS-team mapping was captured completely from `supply_chain_sandbox_d.datamodel.cs_team_sales_org_mapping`. The versioned JSON seed preserves every string value, including sales organization identifiers. Runtime jobs have no dependency on that DEV sandbox.

The refresh validates existing schemas and source access, publishes the seed through bronze, silver, and gold, and independently verifies exact write/read parity at each layer. Only tables tagged `industry_sales.bundle=industry-sales-dashboards` can be replaced. The gold mapping is `SC_BI_industry_sales_cs_team_sales_org_mapping`; D uses the `_dev` suffix so development does not claim TEST's tables. The mapping is release-managed configuration, not a live synchronization from the sandbox. Changes require a new verified capture and release.

The job now has two tasks: `refresh_cs_team_mapping` then `materialize_dashboard_results`. It no longer runs `snapshot_dashboard_sources` or the separate allocation task. It does not copy every row of the 14 source tables into persistent raw snapshots. The existing A/P 06:30 Europe/Brussels schedule, paused D/T schedules, concurrency of one, and fixed schemas remain unchanged. The result task uses `sqlglot==27.20.0` and a 5,400-second timeout; the job timeout remains 7,200 seconds.

The generated `dashboard_results.json` defines 17 active datasets: eight Open Orders and nine Quotations. The original `ds_top_late_orders` and `ds_cancellations_trend` have no page/widget/filter references and are removed from the generated definitions, relationship source registrations, job plans and grant inventory. Original captures remain unchanged for audit. Twelve parameter-free datasets materialize their final, originally filtered/calculated results. Five parameterized datasets preserve the necessary joined row detail and parameter-free calculation boundaries. Their original filters and aggregations remain in the consumer SQL. In particular, segment/country filters still run before quote-level SUM/MAX and COUNT DISTINCT; an All-segments total is not reused as a filtered total. Cancellation date bounds, priority/day buckets, output column names, and native ordering are retained. This produces 20 unique result relations: 12 final outputs and eight supporting relations for five filter-sensitive datasets. A small order-reason lookup is retained where required; this is not a full-source snapshot design.

The identical `converted` component in `ds_quotations`, `ds_quotations_detail` and `ds_expiring_quotes` is calculated, written and verified once per job batch. The other two producers load the verified silver rows pinned to that same batch, not the still-published previous gold batch, and establish their own temporary CTE and dataset receipt. All three consumer queries use the same gold result view. Sharing is restricted to this named, independent, fully-qualified calculation with identical parsed SQL; conflicting or CTE-dependent shared definitions fail before writing. Other source reads are not automatically deduplicated.

The producer executes the existing SQL/CTE calculations as the job identity, checkpointing intermediate frames to avoid plan expansion. Those temporary frames are not persistent copies of the whole source catalog. The producer's source date is fixed once at task start. Parameterized consumer date expressions still use their original CURRENT_DATE semantics over the saved input data, so a stale batch does not become fresh merely because the clock changes. Original lookback windows and source joins are not shortened to force lower row counts. Filter-sensitive details can still contain many qualifying rows, and sequential datasets can repeat some source reads; this design is not a guaranteed runtime or volume reduction until measured in DEV.

Each published gold result is backed by a silver Delta table using the `SC_BI_industry_sales_calc_` prefix and the internal `__industry_snapshot_id` marker. Consumer gold names use `SC_BI_industry_sales_<dashboard>_<dataset>_<component>`. D appends `_dev`; T/A/P use unsuffixed names in their target catalogs. Exact write/read multiset equality is checked for every result, including duplicates and NULLs, before the single `gold.SC_BI_industry_sales_dashboard_result_state` pointer publishes the batch. Receipts must match every expected dataset/table identity. Empty results are allowed only as the actual output of a successful computation; incomplete or failed computations cannot publish.

Until all 17 active datasets and 20 unique persisted relations verify, readers retain the previous completed batch. Initial views may exist but must not be considered ready before first publication. Existing owned views use `ALTER VIEW AS`, preserving consumer grants. Current and previous completed batches are retained; older/unpublished batches are deleted only after successful publication, with no VACUUM. A query lasting across more than one subsequent publication needs separate operational handling. This is atomic result-batch publication, not a transactionally consistent point-in-time snapshot of Synapse: sources are read sequentially. Mapping is updated in its own earlier task and is not included in the result pointer transaction.

The gold state records `snapshot_as_of_date`, `snapshot_completed_at`, and per-dataset result receipts with row counts/column names. Required result field/type changes fail and need reviewed migration. Logs identify each dataset/component, calculation start, verified result, and publication. Failure retains the old batch; operators must check its age. Job success alone does not certify viewer permissions, widget rendering, or an acceptable dashboard latency.

The native dashboard refresh tasks remain removed. Both native dashboard resources, pages, measures, widgets, filters, saved parameters, and explicit reader/editor ACLs remain. Consumer SQL reads the new gold results only, with no direct Synapse or legacy source-snapshot dependency. The job does not prepare native dashboard caches or subscription snapshots; interactive query execution and browser cache refresh remain separate.

Existing legacy raw tables, source views, state tables, allocation outputs, and old helper scripts are not dropped by this change. They are no longer produced or queried by the new job/dashboard graph. The permission manifest retires their declarations to match the new output inventory; this is not direct SQL revocation or deletion. The central permission pipeline's handling of removed declarations must be reviewed separately before retirement is considered complete. Do not run the legacy allocation/snapshot validation helpers as a test of this new flow.

Dashboard credentials are not embedded. The existing READ group members Francois, Noel, and Arda are preserved. `permissions/access.json` declares object-scoped SELECT on 20 gold result views, 20 silver physical calculation tables, the gold result state, and three mapping tables, plus the existing four catalog/schema USE grants: 48 grant entries. Direct silver inspection reveals retained batches/internal markers and is not required simply to read owned gold views. Gold view owners must retain access to underlying silver/state dependencies. Warehouse CAN_USE and dashboard ACLs are separate prerequisites; no warehouse is created by this manifest.

## Master CI Release

This is a new top-level bundle under DS-Master-Repo. Shared TEST/ACC/PRD pipeline YAML is unchanged. The checked-in generated dashboard resources work with ordinary `databricks bundle deploy`; no custom Azure stage or generator hook is required. D uses a personal root. T/A/P use `/Workspace/automation/industry-sales-dashboards/<target>` and the existing CI deployment identities, which also own/run the job when deployed by CI.

1. Review and commit only this new project folder in the existing Master Git Folder. The local DS-Master-Repo directory is a partial workspace export, not a Git checkout.
2. Use the repository's TEST validation and ACC PR/build-validation flow, then merge to main for PRD. Do not deploy ACC/PRD as a human to bypass the protected automation root.
3. Ensure the CI identity has Foundation-managed source SELECT, CREATE TABLE and owned-view update/write rights in the existing target schemas, warehouse use, and compute-policy use. Consumers do not need upstream Synapse access. Apply the central consumer manifest after all declared result objects exist, and verify the effective grants after a second data-production run.
4. Validate the new two-task result producer in DEV first. Verify both tasks succeed, all 17 active datasets have complete publication receipts and all 20 unique outputs verify (the shared conversion output has three dataset receipts), dates and row counts are appropriate, and consumers without Synapse access can load both dashboards. Test null/empty/single/multiple segment/country selections and cancellation ranges against original native queries. A paused D/T schedule permits a manual smoke run. Do not promote merely because source tests pass.

The helper explicitly publishes without embedded credentials and runs the first table-production job, not a native dashboard refresh:

```bash
bash scripts/deploy_and_publish.sh T <ci-profile>
```

Do not assume the shared external deployment template automatically invokes that helper or performs a successful first result build. The scheduled job owns subsequent mapping and dataset-result updates. Dashboard opening and query execution are separate from that schedule. Source and permission changes are made only in DEV; the user commits and promotes them through the existing pipeline.

## Validation

Use an isolated environment with Java 17 for the local Spark equivalence tests. Install the pinned dependencies from `requirements-dev.txt` there, not over system Python. The ad hoc run/cleanup helpers enforce the exact DEV workspace and job; they do not accept ACC/PRD receipts. Source changes and validation are DEV-only; the user promotes through the established pipeline.

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m unittest discover -s tests -v
python3 scripts/render_dashboard_resources.py --check
databricks bundle validate --target D --profile DEFAULT
python3 scripts/preflight_sql.py D
python3 scripts/validate_dataset_result_schemas.py
```

`scripts/capture_source_column_names.py` refreshes the versioned projection evidence using DEV metadata only, without reading data rows. Regenerate resources and rerun projected/full-schema checks when refreshing that evidence or editing source SQL. Do not silently apply DEV schema assumptions to changed target inputs; the transfer validates required native types against existing destination storage.

The original-source preflight requires engineer/source access and is not a consumer permission test. The result-schema validator reads DEV metadata only and compares empty local Spark producer/consumer schemas with original query schemas. The historical pre-simplification check matched 17 of 19 definitions; the current active scope has 15 comparable datasets plus allocation Decimal STACK and potential-match QUALIFY, which remain explicit local-engine gaps requiring native Databricks validation. Fixture tests cover original-versus-compiled multi-segment quote counts/values, country filtering before grouping, cancellation ranges, output names, ordering, and incomplete/wrong-identity receipts. The actual producer-loop fixture checks one shared compute/write, two same-batch reuses and old-batch exclusion with duplicate/NULL rows. These checks do not certify real-data performance, source consistency, browser behavior, or viewer permissions. A canceled statement is not evidence of missing data. Reports live under ignored `validation/`.

`scripts/sync_master_repo.py` uploads only this project into the existing DEV Master Git Folder and byte-verifies every file. It neither commits nor pushes, and it is not an ACC/PRD deployment.

Original dashboard IDs: Open Orders `01f1b99401ce107e98453f33f5afefe2`, Quotations `01f1b9dbf7ea1d8483cdaa18dd976a80`. Raw metadata, ACLs, and the source SQL statement receipt are retained under `source_dashboards/` for exact preservation checks and excluded from runtime synchronization.