# Release Status - 2026-10-13

## Implemented And Placed In Master Repo

- New top-level `industry-sales-dashboards` bundle under the existing DEV Git Folder `/Workspace/Users/mustafaarda.bicakci@etexgroup.com/DS-Master-Repo`.
- Existing branch remains `feature/Master_Data_App`. No Git commit, push, branch change, or ACC/PRD deployment was performed.
- D/T/A/P targets follow the current Master-owned `ai-cost-dashboards` conventions, including automation catalogs, warehouse IDs, Job Compute policies, and shared CI discovery. Shared pipeline YAML was not modified.
- Existing bronze/silver/gold schemas only; no schema-creation statement anywhere in runtime source.
- 108-row CS-team seed replaces the DEV sandbox dependency. It is versioned configuration and must be updated through a reviewed release when business mappings change.
- Two original dashboards remain untouched. Their native business SQL, filters, 19 datasets, 10 pages, and 135 widgets are preserved, with only environment-specific source references changed.
- Existing explicit dashboard readers/editors are retained. Credentials are not embedded; target data and warehouse grants must be checked for those viewers.

## Verified

- Twelve focused regression tests pass, including full native-page/widget parity, original-reader preservation, mapping completeness/uniqueness, and wrong-target/workspace/name rejection.
- Generated resources and lookup seed pass deterministic regeneration checks; deployment helper passes shell syntax validation.
- D and T bundle validation succeeds.
- Both D dashboard copies are deployed and published on warehouse `69ada62b2fb9b9e2`, with `embed_credentials=false`. Live serialized JSON matches the source definitions plus the exact target substitutions.
- D job `38702778571616` is deployed with its schedule paused. Both native dashboard tasks depend on the mapping task and use deployed dashboard IDs rather than source IDs.
- Repaired mapping task `787702914912477` succeeded in job run `129611750320677`. It validated all 14 source tables and existing schemas, wrote the isolated `_dev` mapping through bronze/silver/gold, and checked exact Spark write/read parity at each layer.
- Read-only ACC and PRD metadata queries confirmed the existing three schemas and all 14 shared `synapse-prd.pbi` source tables are visible to the current human account. This does not prove the CI identities have the same grants.
- Every uploaded source file is downloaded again and byte-compared; the local receipt is `validation/master_source_upload.json`.

## Runtime And Release Gates Still Open

1. A/P bundle validation cannot complete as the current human account: both protected `/Workspace/automation` roots return permission denied. Use the existing CI deployment identities; do not move the production roots to a personal folder.
2. Azure DevOps browser access requires sign-in. The Master Git Folder contains the new files, but they must be reviewed, committed/pushed, and promoted through the normal TEST, ACC build-validation, and main/PRD path. Source upload alone is not a release.
3. The first D attempt failed before writes because a deployment during startup mixed an older notebook snapshot with a newer helper signature. Both deployed files were then exported and byte-verified, and the source-frozen repair passed the mapping stage. Keep deployed source frozen during smoke runs.
4. D dashboard refreshes did not finish. Query-history entries linked directly to the new dashboards showed running/queued statements on the shared 2X-Small automation warehouse. The smoke run was explicitly canceled to bound shared-compute load; latest dashboard task results are CANCELED, not SUCCESS. Root cause of the slow/queued execution, including warehouse contention versus source federation/query performance, is not established. No shared warehouse was resized and no business SQL was changed.
5. Eleven of nineteen DEV dataset analysis checks passed in the initial preflight. The others were canceled at the 50-second statement limit and remain unverified, not proven invalid. Independent SQL reads of the tiny deployed mapping also timed out; the successful Spark parity checks are the current runtime mapping evidence.
6. Integrated-browser verification is blocked by Databricks sign-in. API publication and exact JSON parity are confirmed, but visual rendering, filter interaction, viewer access, and all-widget data loading are not certified.
7. Verify the CI identity can read all source tables, write/own the bundle tables in existing schemas, use the warehouse and compute policy, and manage/publish its dashboards. Verify preserved reader/editor principals exist in each workspace and have the required target/source data grants.
8. A/P configuration specifies a daily 06:30 Europe/Brussels schedule. Complete runtime and viewer acceptance before merging/activating the production release; deployment alone does not certify the first refresh. The deploy/publish helper explicitly runs that first refresh, but the external shared CI template's invocation of it is not established here.

## Selective Loading Investigation

- User screenshots confirm the dashboard layouts open and some Quotations values load; Conversion Rate and Open Orders allocation counters continue spinning. This is partial browser evidence, not full rendering certification.
- User-started DEV run `394542741543224` passed its mapping task `912129997252130`; both downstream dashboard tasks remained RUNNING during the investigation. This run was not canceled or repaired by the assistant.
- A bounded recent query-history page showed 26 QUEUED and 11 RUNNING statements explicitly linked to the two new dashboard IDs, alongside six FINISHED statements. No SQL errors were present in those dashboard records. This supports workload queueing and long execution; it does not rule out a separate problem outside the captured records. Query text is REDACTED, so exact running statements cannot be matched to individual widgets from history alone.
- Both dashboards and browser viewers share `dau-automation-sqlwh-d-01`, a single-cluster 2X-Small serverless warehouse. The job previously launched both full dashboard refreshes concurrently.
- Conversion Rate has a defined measure and an explicit `ds_quotations` dataset binding; the visible loading state is not evidence of a missing conversion-rate definition. Its original business formula is unchanged. Other allocation KPI bindings and source computations were inspected without modifying them.
- The job YAML now serializes refreshes as mapping -> Open Orders -> Quotations. Resolved DEV bundle validation verified the chain and the one-run concurrency limit. The same shared YAML is used by T/A/P. Only the future DEV Quotations task dependency was updated live through Jobs API; no full bundle/source deployment, warehouse resizing, business SQL edit, extra refresh run, or current-run cancellation was performed during this investigation.
- The scheduling change reduces overlapping refresh load; it is not a demonstrated cure for the current spinners. The current run uses its original task graph. Individual query performance, cache behavior, source federation, and end-to-end refresh completion still need verification before ACC/PRD acceptance. Do not repeatedly start refresh jobs while diagnosing a pending run.

## DEV Links

- Workspace dashboard folder: https://adb-7181820732839861.1.azuredatabricks.net/browse/folders/2091892049417791
- Open Orders: https://adb-7181820732839861.1.azuredatabricks.net/dashboardsv3/01f1c6f4f7b219909870c67394157901/published
- Quotations: https://adb-7181820732839861.1.azuredatabricks.net/dashboardsv3/01f1c6f4f7ac13ff9d8a7fbdda2a4560/published
- Job: https://adb-7181820732839861.1.azuredatabricks.net/jobs/38702778571616
- Smoke run: https://adb-7181820732839861.1.azuredatabricks.net/?o=7181820732839861#job/38702778571616/run/129611750320677

The earlier hand-built `/pages/<page-name>` Open Orders link showed Page not found in the user's authenticated browser. Both dashboard objects remain ACTIVE, a published version exists, and the current user has CAN_MANAGE. The published links above come from live bundle summary, not inferred page routes; they still require authenticated browser verification. Open the dashboard folder and select the dashboard to obtain the link generated by the current Databricks UI if direct navigation fails. Running the refresh job is not a remedy for a browser route failure.