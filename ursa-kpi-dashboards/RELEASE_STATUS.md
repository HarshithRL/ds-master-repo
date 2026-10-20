# URSA KPI Bundle Release Status

## Source

- Captured in DEV on 2026-10-20 from dashboard
  `01f1c64b4d221e24ad538c8f31226e41` owned in Kerem's user directory.
- Canonical source SHA-256:
  `c3c3bc8d6b7ac4654c6314f7129b0cd936a94eb5be8f766e301b561a79618c4b`.
- Complete inventory retained: 7 datasets, 14 pages, 50 widgets.
- DEV Master Repo branch observed: `feature/PMO_app`.
- DEV Master Repo head observed:
  `50e3c218ce5f227d4b1f927eb13cef49fd80262e`.
- No source dashboard or existing Industry Sales bundle was modified.

## Executed Checks

- 34 focused local tests passed, including full native-source SQL AST equality
  after replacing only the upstream relation addresses.
- Deterministic generated-dashboard/plan freshness check passed.
- DEV `bundle validate --target D --profile DEFAULT` passed; the initial
  validation-directory warning is resolved when local evidence is present.
- Native DEV UC metadata: all 15 source relations and 81 required columns found;
  1,477 source columns available in total. This check reads metadata, not rows.
- Native DEV existing `automation_d.bronze.bronze_volume` confirmed.
- Native DEV warehouse `69ada62b2fb9b9e2` confirmed RUNNING.
- Runtime Python syntax check passed. Pylance reports only the expected local
  `reportMissingImports` warning for `pyspark.sql` in the lightweight validation
  environment; PySpark is provided by the configured Databricks Runtime.

## Native DEV Execution

- All 19 source files were uploaded to the actual DEV Master Repo subfolder,
  preserved as FILE objects and independently re-exported with exact byte
  comparisons. The additional regression test was also uploaded and verified.
- DEV bundle deployment completed successfully.
- DEV job ID: `746558592237245`.
- DEV dashboard ID: `01f1ccc9fb9c1806b7de5a73ac5154fa`.
- Published dashboard uses warehouse `69ada62b2fb9b9e2` and
  `embed_credentials=false`. Its complete JSON matches the generated dashboard
  after resolving the DEV catalog/suffix variables.
- The deployed job's three-task dependency graph, forwarded parameters,
  concurrency limit and PAUSED schedule were verified through the native API.
- Native refresh run `392874394534191` started at 2026-10-20 21:07:30 UTC.
  At this checkpoint it is waiting for cluster `1020-210732-qcck66r6` to finish
  initial provisioning. No successful materialization is claimed yet.
- Authenticated browser acceptance is blocked by a separate Microsoft Entra ID
  sign-in in the integrated browser. CLI OAuth access does not establish a
  browser SSO session; no credentials were requested through chat.

Update this section with terminal task states and native result receipts after
execution. Local tests and successful deployment alone are not runtime or
browser acceptance.

## Release Gates

- ACC/PRD have not been mutated or runtime-validated.
- No commit, push, branch change or shared pipeline change was performed.
- Shared consumer membership/grant declarations were not changed.
- At the user's request, A/P source configuration is UNPAUSED for daily 06:30
  Europe/Brussels runs; D/T remain PAUSED. The change takes effect after pipeline
  deployment. No live ACC/PRD schedule was changed directly.
- Original mock datasets, inline baselines, Skamol pilot filters, zero defaults
  and placeholder KPI behavior remain unchanged and need business approval
  before describing the dashboard as live, complete URSA coverage.