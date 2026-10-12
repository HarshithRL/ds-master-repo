# Master Data App  

This is an independent Databricks Asset Bundle for the DS-Master-Repo. The shared repo pipeline discovers this folder and deploys its bundle to TEST, ACC, and PRD.

The current portal UI and business logic are imported from Anastasija's latest
`/Workspace/Users/anastasija.lebedeva@etexgroup.com/axiom-demo` source. Active
modules follow its `portal/core`, `portal/ui` and `portal/integrations` layout.
Demo mode is disabled: customer queries use the existing forwarded-user SQL
client, requests use the environment's bronze tables, and configuration comes
from seeded SQL sheet snapshots rather than the demo customer workbook.
The existing bundle, app YAML, warehouse resources and shared pipeline are retained.

## Data and identity

- App-owned request data is written to `{catalog}.bronze.master_data_app_requests`; activity history is provisioned in `{catalog}.bronze.master_data_app_request_history`.
- The paused setup job reads its four environment-specific rule workbooks from `/Volumes/{catalog}/bronze/bronze_volume/master_data_app` and populates `{catalog}.bronze.master_data_app_configuration` with versioned sheet snapshots. Re-running it replaces only that dedicated configuration snapshot.
- The latest four inputs are `general_data.xlsx`, `customer_form_rules.xlsx`, `credit_management_rules.xlsx` and `assignment_rules.xlsx`. The latest source copies are in `src/data`. `general_data.xlsx` replaces the older `customer_reference_library.xlsx`; the seed and runtime support the old name for existing snapshots/volumes, preferring the new file when both are present. Replacing Repo source files does not update environment Volumes or their seeded tables.
- The job does not create catalogs or schemas; the existing `bronze` schema must already be present. Request and history tables remain empty until app activity creates records.
- The app reads company, field, credit, and assignment rules from the populated configuration table. Customer records are still queried live with the visitor's token from the source table mapped in the reference workbook.
- The app uses the visitor's forwarded Databricks token and requires the `sql` user authorization scope. Consumers also need appropriate warehouse and Unity Catalog privileges for source and request tables.
- The consumer READ/WRITE groups in `permissions/access.json` hold the planned data grants. App-level group `CAN_USE` is intentionally deferred until the group mapping is finalized.
- Run the setup job once per environment before starting the app. Its identity needs `USE_CATALOG`, `USE_SCHEMA`, `READ_VOLUME` on the config volume, and permission to create/write the app tables in the existing bronze schema; app users need SELECT on configuration and MODIFY on requests/history.

## Deployment status

- The app uses the stable name `ds-master-data-app` in T/A/P. D has no app resource, matching the Air Monitoring bundle and avoiding a second app name in the shared DEV/TEST workspace.
- T uses the existing shared automation SQL warehouse; A/P use the existing `dau-automation-sqlwh-a-01` and `dau-automation-sqlwh-p-01` warehouses. The central permissions entry does not request new consumer warehouses.
- The four configuration workbooks are uploaded to the existing bronze volume's `master_data_app` directory separately in D, A, and P. T uses D's `automation_d` catalog volume.
- App resources are declared inline under each target in `databricks.yml`; `include: resources/jobs/*.yml` loads the file-backed jobs. Air Monitoring uses the same jobs-only include pattern.
- T/A/P declare Arda and Pierre as bundle-level `CAN_MANAGE` users, matching Air Monitoring's folder-access pattern. App-only permissions do not grant visibility into the bundle source directories. The next shared CI/CD deploy must apply these permissions to the target root and its files. D retains the same setup-job managers without an app resource. On ACC, the exact Master Data automation root exists but the current user cannot manage its target folder; an empty or missing folder-selector entry is not proof the deployment identity has no source files.
- ACC/PRD use only the existing shared foundations deployment template, matching the other projects in DS-Master-Repo. The project-specific app deployment stage was removed after ACC run 319928 failed during Azure DevOps template compilation. No replacement per-app pipeline or app-deploy job is added. Do not deploy ACC/PRD from a workstation or use the Databricks UI Deploy button.
- This project has no separate deployment pipeline, template or deploy script. The existing DS-Master-Repo root pipelines and their variable templates remain unchanged. Restoring the shared pipeline structure does not by itself resolve or verify Master Data app runtime deployment.
- App deployment does not run the paused setup job or grant access to the live customer source table. The central consumer grants cover the environment-specific `automation_a`/`automation_p` bronze objects; the external customer source needs its own approved read grant.
- The existing app's signed notification URL is intentionally not copied into source. Configure notifications through an approved secret resource and set the environment-specific workbench URL before enabling them.
- The setup job refuses to seed ACC/PRD while the volume workbooks contain explicit test-only/dummy markers. Its error reports the source directory and the first offending sheet/row/column locations. Replace them with approved environment mappings before running the setup job in those environments; the app requires its configuration table to be populated before it can serve requests. A running app is not proof that seeding succeeded.
- No data is copied from the previous personal-schema request table. Any historical migration needs a separately reviewed, permissioned migration plan.

Validate locally with `databricks bundle validate --target D`. Deploy through the DS-Master-Repo shared CI/CD pipeline; do not deploy ACC or PRD directly from a workstation.