# Agent Dashboard (Phase 1)

Databricks Asset Bundle for the **Agent Dashboard Phase 1** pipeline: volume ingest → silver dims/facts → metric views → validate → publish Lakeview dashboard.

This folder is the deployable unit for [DS-Master-Repo](https://dev.azure.com/etexit/Etex%20Portfolio%202.0/_git/DS-Master-Repo). Shared Azure DevOps pipelines discover any top-level folder with a `databricks.yml` and deploy it (TEST / ACC / PRD).

## Structure

```
agent-dashboard/
├── databricks.yml
├── resources/
│   ├── agent_dashboard.job.yml
│   └── agent_dashboard.dashboard.yml
├── src/
│   ├── notebooks/
│   │   ├── config_file.py
│   │   ├── 01_excel_to_bronze.sql
│   │   ├── 02_silver_layer_pipeline.py
│   │   ├── 03_bot_usage_metrics.sql
│   │   ├── 04_metric_creation.py
│   │   ├── 05_metric_views_refresh.py
│   │   ├── 07_dimensional_layer_refresh.sql
│   │   ├── 08_validate_dashboard.py
│   │   └── 09_publish_dashboard.py
│   └── dashboards/
│       └── agent_dashboard_phase1.lvdash.json
├── UPLOAD_CONVENTIONS.md
└── PIPELINE_REFRESH_RUNBOOK.md
```

## Targets

| Target | Workspace | Catalog | Root path |
|--------|-----------|---------|-----------|
| D (dev) | `adb-7181820732839861` | `automation_d` | `/Workspace/Users/<you>/ds-cicd-agent-dashboard/D` |
| T (test) | same DEV workspace | `automation_d` | `/Workspace/automation/ds-cicd-agent-dashboard/T` |
| A (acc) | `adb-4796304964978539` | `automation_a` | `/Workspace/automation/ds-cicd-agent-dashboard/A` |
| P (prd) | `adb-4844910598668398` | `automation_p` | `/Workspace/automation/ds-cicd-agent-dashboard/P` |

Notebooks call `%run ./config_file`, which detects the workspace org id and sets `UNITY_CATALOG` / `SILVER` / `BRONZE_VOLUME`.

## Local commands

Run from this folder:

```powershell
databricks bundle validate --target D --profile adb-7181820732839861
databricks bundle deploy --target D --profile adb-7181820732839861
databricks bundle run agent_dashboard --target D --profile adb-7181820732839861
```

## CI/CD flow (DS-Master-Repo)

```
feature branch → TEST (manual) → PR → ACC (automatic) → merge → PRD (automatic)
```

Do **not** edit shared `pipelines/` YAMLs. First deploy keeps the file-arrival trigger **PAUSED**; unpause after a green TEST run.

## Ops docs

- [UPLOAD_CONVENTIONS.md](UPLOAD_CONVENTIONS.md) — canonical bronze volume filenames
- [PIPELINE_REFRESH_RUNBOOK.md](PIPELINE_REFRESH_RUNBOOK.md) — refresh / validate / publish

## Notes

- Job compute: serverless (`environment_version: "5"`), matching the live Phase 1 job.
- Dashboard warehouse / id are bundle variables (`warehouse_id`, `dashboard_id`). ACC/PRD warehouse IDs may need updating after first deploy.
- Volume path pattern: `/Volumes/{catalog}/bronze/bronze_volume/`
