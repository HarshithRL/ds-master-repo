# Master Data App

An independent Databricks Asset Bundle in DS-Master-Repo. The shared repo pipeline discovers this folder and deploys its bundle to TEST, ACC and PRD. It contains one app and one setup job:

| Part | Folder | Deployed as | Who uses it |
|---|---|---|---|
| **AXIOM app** | `src/` | app `ds-master-data-app` | the **request portal** for requesters (create / extend / change a customer) and the **Customer Master Workbench** page for the Master Data team |
| **Setup job** | `src/setup_tables.py`, `resources/jobs/` | job "ds-master-data-app - Setup and Seed Bronze Tables" (paused) | run by a manager once per environment, and after each rule-workbook change |

The Workbench is a page of the same app (`/workbench`), so it exists in TEST, ACC and PRD and works on that environment's requests.
* **Who sees it:** the active Members of `assignment_rules.xlsx`, sheet Members (the people requests are assigned to), plus any emails in the optional `WORKBENCH_ADMINS` setting.
* **How they open it:** team members get a **Master Data** button in the portal header. The Teams message opens a request directly (`…/workbench?request=<id>`).
* **Everyone else:** sees no button, and gets "for the Master Data team only" if they open the address.

The portal code follows the AXIOM layout (`portal/core`, `portal/ui`, `portal/integrations`) with demo mode off. Customers come from SAP, requests go to the environment's bronze tables, and the rules come from the seeded configuration table instead of the files.

## What sets up what

| File | Sets up |
|---|---|
| `databricks.yml` | Targets **D / T / A / P**: workspace, root path, catalog, cluster policy, SQL warehouse and bundle managers. Per target: the app, its **permissions** (who may open them), its **resources** (SQL warehouse; secrets for SAP and Power Automate) and the `sql` user authorization scope. |
| `resources/jobs/master_data_setup.job.yml` | The paused setup job (single-node cluster under the environment's policy). It reads the rule workbooks from the environment's Volume. |
| `src/setup_tables.py` | Creates `{catalog}.bronze.master_data_app_requests`, `…_request_history` and `…_configuration` (no catalogs or schemas). Replaces the configuration snapshot with the workbooks' sheets. Blocks ACC/PRD seeding when workbooks contain test-only markers. |
| `src/app.py` | The entry point: routes to `request_portal.py` (default page) or `master_data_workbench.py` (`/workbench`). Neither page is in a menu. |
| `src/request_portal.py`, `src/portal/` | The request portal. |
| `src/master_data_workbench.py`, `src/workbench/` | The Workbench page. It checks team membership first (`portal/core/identity.py`), then uses the same tables as the portal. |
| `src/app.yaml` | How the app starts, and which resource fills which environment variable: `SQL_WAREHOUSE_ID`, `SAP_USER`, `SAP_PASSWORD`, `NOTIFICATION_FLOW_URL`. It is the same file in T, A and P. |
| `src/config.py` | The **catalog from the workspace** (DEV/TEST `automation_d`, ACC `automation_a`, PRD `automation_p`), and from it the table names. |
| `src/portal/config.py` | The **environment from the catalog**: TEST and ACC show a ribbon, PRD none. Also the SAP address per environment and the Workbench link (this app's `/workbench` page). Settings come only from the environment, never from YAML files. |
| `permissions/access.json` (shared repo) | The consumer READ / WRITE groups' data grants (warehouse and Unity Catalog), applied by the shared pipeline. |

Nothing outside `databricks.yml`, the job file and the shared pipeline deploys anything. Do not deploy ACC/PRD from a workstation or with the Databricks UI Deploy button. Validate locally with `databricks bundle validate --target D`.

## How a request flows

1. **Customer from SAP.** The portal reads the customer through SAP's Business Partner API (`API_BUSINESS_PARTNER`, OData v2) with the technical user from the `sap-user` / `sap-password` secrets (`src/portal/integrations/sap_business_partner.py`).
   * Which API property fills which AXIOM field is maintained in `sap_api_mapping.xlsx`, sheet Field_Mapping. It is seeded like the other workbooks.
   * `CUSTOMER_SOURCE=databricks` in `src/app.yaml` switches back to the Databricks source table mapped in `general_data.xlsx`.
2. **Rules from the configuration table.** Company list, fields, dropdowns, dependencies, credit and assignment rules come from `{catalog}.bronze.master_data_app_configuration`, seeded from the workbooks in the Volume.
3. **Submit.** The request is written to `{catalog}.bronze.master_data_app_requests` with status ASSIGNED, using the visitor's forwarded token (`sql` scope). Power Automate sends the Teams message (with a link that opens the request in the Workbench) and the confirmation email.
4. **Workbench page.** The Master Data team opens the request, enters the TOPdesk ticket and sets the status (history in `…_request_history`). The requester sees the status under **My requests**.

## Data and identity

* The app uses the visitor's forwarded Databricks token and needs the `sql` user authorization scope:
  * Requesters need SELECT on the configuration table and MODIFY on requests (the consumer groups in `permissions/access.json`).
  * Master Data members also need SELECT/MODIFY on the history table.
  * The Workbench button and page are hidden from everyone who is not in the team list, but the real data protection is the table grants above.
  * App access (CAN_USE) does not itself grant warehouse or Unity Catalog privileges.
* ACC/PRD give the portal to `AUTOMATION.MASTERDATAAPP.CONSUMER.WRITE` and `…CONSUMER.READ`.
* To give someone the Workbench: add them as an active row in Members of `assignment_rules.xlsx` (Volume), then re-run the setup job. They then also receive requests through the assignment pool.
* The setup job reads `/Volumes/{catalog}/bronze/bronze_volume/master_data_app`. T uses D's `automation_d` volume.
  * It needs `general_data.xlsx` (or the old `customer_reference_library.xlsx`), `customer_form_rules.xlsx`, `credit_management_rules.xlsx`, `assignment_rules.xlsx` and `sap_api_mapping.xlsx`.
  * The workbooks live only in the Volume; the app source carries no copies. After replacing a workbook, re-run the job so the seeded table follows.
  * The job's identity needs `USE_CATALOG`, `USE_SCHEMA`, `READ_VOLUME` and rights to create and write the app tables in the existing bronze schema.
* No data is copied from the previous personal-schema request table. A historical migration needs a separately reviewed plan.

## Before the first deployment of this version (per workspace: DEV/TEST, ACC, PRD)

1. **Secret scope `master-data-app`** (variable `secret_scope`), with these keys:
   * `sap-user`, `sap-password`: the read-only SAP technical user of that environment's SAP system (DEV/TEST = SD1, ACC = SQ1, PRD = SP1).
   * `notification-flow-url`: the signed Power Automate URL. Not wired yet — add the secret resource in `databricks.yml` and a `valueFrom` entry in `src/app.yaml` once the URL is stored, until then notifications stay off.

   A bundle cannot create the scope, so it must exist in a workspace **before** the deploy; otherwise the deploy fails with `Secret with scope master-data-app and key sap-user does not exist`. The deployment identity needs **Can manage** on the scope.

   An environment without an SAP endpoint or technical user keeps reading customers from Databricks: `portal/config.py` falls back to `CUSTOMER_SOURCE=databricks`.
2. **Network route** from Databricks serverless to SAP (`vhmcosd1ci.sap.etexgroup.com:44300` for DEV/TEST). Set up by the Databricks account admin and the network team; test from a serverless notebook.
3. **SAP host for ACC/PRD.** Fill in `_SAP_API_URL_BY_CATALOG` in `src/portal/config.py`, or set `SAP_API_URL` in `src/app.yaml`. If SAP's certificate is from an internal CA, add the CA file to `src/assets/` and set `SAP_CA_BUNDLE`.
4. **Upload** the five workbooks to the environment's Volume and **run the setup job**.

## Deployment status

* The app uses the stable name `ds-master-data-app` in T/A/P. D has no app resource, matching the Air Monitoring bundle and avoiding a second app name in the shared DEV/TEST workspace.
* Warehouses:
  * T uses the existing shared automation SQL warehouse.
  * A uses `aut-masterdataapp-consumer-sqlwh-a` (`d0aa411377ac7611`).
  * P uses `aut-masterdataapp-consumer-sqlwh-p` (`71c2830f1b638f65`).
  * The app receives its target's warehouse through its `sql-warehouse` resource.
* T/A/P declare Arda and Pierre as bundle-level `CAN_MANAGE` users (folder access). App-only permissions do not grant visibility into the bundle source directories.
* ACC/PRD use only the existing shared foundations deployment template. There is no separate per-app pipeline, template or deploy script.
* App deployment does not run the paused setup job. The setup job refuses to seed ACC/PRD while the workbooks contain test-only/dummy markers. The current workbooks pass that check.

## Tests

`python -m unittest discover -s tests`:

* `test_config.py`: catalog per workspace.
* `test_setup_tables.py`: tables, seeding and blockers.
* `test_portal_settings.py`: environment, SAP address and Workbench link per workspace.
* `test_sap_mapping.py`: the SAP mapping: entities, fallbacks, formats, company code / sales area scope, partner functions.
* `test_workbench_access.py`: who may open the Workbench page.
