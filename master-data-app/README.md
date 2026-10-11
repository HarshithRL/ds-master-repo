# Master Data App

This is an independent Databricks Asset Bundle for the DS-Master-Repo. The shared repo pipeline discovers this folder and deploys its bundle to TEST, ACC, and PRD.

## Data and identity

- App-owned request data is written to `{catalog}.bronze.master_data_app_requests`; activity history is provisioned in `{catalog}.bronze.master_data_app_request_history`.
- The paused setup job creates those operational tables and populates `{catalog}.bronze.master_data_app_configuration` with versioned snapshots of every sheet in the four bundled rules/reference workbooks. Re-running it atomically replaces only that dedicated configuration snapshot.
- The job does not create catalogs or schemas; the existing `bronze` schema must already be present. Request and history tables remain empty until app activity creates records.
- The app reads company, field, credit, and assignment rules from the populated configuration table. Customer records are still queried live with the visitor's token from the source table mapped in the reference workbook.
- The app uses the visitor's forwarded Databricks token and requires the `sql` user authorization scope. Consumers also need appropriate warehouse and Unity Catalog privileges for source and request tables.
- Run the setup job once per environment before starting the app. Its identity needs permission to create and write tables in the existing bronze schema; app users need SELECT on configuration and MODIFY on requests.

## Deployment status

- D and T targets use the shared DEV/TEST automation warehouse.
- ACC and PRD targets currently deploy the setup job only. Add the correct environment-specific consumer warehouse, app permissions, and table grants before enabling app resources in those targets.
- The shared pipeline does not supply project-specific warehouse IDs or consumer groups.
- The existing app's signed notification URL is intentionally not copied into source. Configure notifications through an approved secret resource and set the environment-specific workbench URL before enabling them.
- The setup job refuses to seed ACC/PRD while the bundled workbooks contain explicit test-only/dummy markers. Replace them with approved production mappings before running the setup job in those environments.
- No data is copied from the previous personal-schema request table. Any historical migration needs a separately reviewed, permissioned migration plan.

Validate locally with `databricks bundle validate --target D`. Deploy through the DS-Master-Repo shared CI/CD pipeline; do not deploy ACC or PRD directly from a workstation.