# Agent Dashboard Phase 1 — Pipeline Refresh Runbook

## Overview

Self-service refresh for **Agent Dashboard Phase 1 (Silver)** via the `agent-dashboard` Databricks Asset Bundle.

```
Export → upload canonical filename to bronze_volume root
  → file trigger (when UNPAUSED) or bundle run
    → Ingest_bronze (01, incremental)
    → Silver_preprocess (02)
    → Gold_dimensional (07)
    → Bot / Copilot / Governance metrics (03/04/05)
    → Validate_dashboard (08)
    → Publish_dashboard (09)
```

| Constant | Value |
|----------|-------|
| Bundle | `ds-cicd-agent-dashboard` |
| Databricks profile (DEV) | `adb-7181820732839861` |
| SQL warehouse (DEV) | `69ada62b2fb9b9e2` |
| Job resource key | `agent_dashboard` |
| Volume (DEV) | `/Volumes/automation_d/bronze/bronze_volume` |
| Target schema (DEV) | `automation_d.silver` |
| Dashboard (DEV) | [Agent Dashboard Phase 1 (Silver)](https://adb-7181820732839861.1.azuredatabricks.net/sql/dashboardsv3/01f19237ae0419ea830abdda6219869d) |
| Default load mode | **incremental** (append + dedup) |
| Workspace notebooks (T/A/P) | `/Workspace/automation/ds-cicd-agent-dashboard/{T\|A\|P}/...` |

See **[UPLOAD_CONVENTIONS.md](UPLOAD_CONVENTIONS.md)** for exact filenames, formats, archive behavior, and overwrite caveats.

---

## 1. Upload files (self-service)

Upload to the **volume root** only, using canonical names (e.g. `agents_inventory.xlsx`, `microsoft_purview_audit_log.csv`).

```powershell
databricks fs cp ".\agents_inventory.xlsx" `
  dbfs:/Volumes/automation_d/bronze/bronze_volume/agents_inventory.xlsx `
  --profile adb-7181820732839861 --overwrite
```

After a successful ingest, files move to `archive/YYYY-MM-DD/`.

---

## 2. Run the pipeline

### Full job (8 tasks) via bundle

```powershell
cd agent-dashboard
databricks bundle deploy --target D --profile adb-7181820732839861
databricks bundle run agent_dashboard --target D --profile adb-7181820732839861
```

Task DAG:

| Task | Notebook |
|------|----------|
| `Ingest_bronze` | `01_excel_to_bronze.sql` (`load_mode=incremental`) |
| `Silver_preprocess` | `02_silver_layer_pipeline.py` |
| `Gold_dimensional` | `07_dimensional_layer_refresh.sql` |
| `Bot_usage_metrics` | `03_bot_usage_metrics.sql` |
| `Copilot_metrics` | `04_metric_creation.py` |
| `Governance_cost_metrics` | `05_metric_views_refresh.py` |
| `Validate_dashboard` | `08_validate_dashboard.py` |
| `Publish_dashboard` | `09_publish_dashboard.py` |

### One-time overwrite rebuild

Pass widget override on task `Ingest_bronze` only (job UI):

```json
{"load_mode": "overwrite"}
```

Use when agents were deleted from platform exports and must disappear from bronze.

### Deploy via Asset Bundle (preferred)

```powershell
cd agent-dashboard
databricks bundle validate --target D --profile adb-7181820732839861
databricks bundle deploy --target D --profile adb-7181820732839861
```

CI/CD in DS-Master-Repo deploys the same bundle to T / A / P automatically.

---

## 3. Validate refresh

### In-job gate (automatic)

Task `Validate_dashboard` runs smoke counts, L1 patch asserts, and all 35 dataset SQLs. Publish is blocked if it fails.

---

## 4. File-arrival trigger

Trigger watches `/Volumes/{catalog}/bronze/bronze_volume/` (from `${var.catalog}` in the job YAML).

- Bundle default: **PAUSED** until verified in TEST.
- Unpause in the job UI (or `databricks jobs update`) after a green e2e run.
- `max_concurrent_runs = 1` prevents overlapping appends.

---

## 5. SQL smoke tests (DEV)

```sql
SELECT COUNT(*) FROM automation_d.silver.fact_agent_credit;
SELECT COUNT(*) FROM automation_d.silver.dim_agent;
SELECT COUNT(*) FROM automation_d.silver.bot_usage;
SELECT COUNT(*) FROM automation_d.silver.sl_purview_log;
```

For ACC/PRD, swap catalog to `automation_a` / `automation_p`.

---

## Known limitations (v1)

| Item | Notes |
|------|-------|
| `_agent_name_bridge` | **Not refreshed** — joins live bridge table. |
| Incremental deletes | Removed agents stay until overwrite rebuild. |
| `vw_agent_governance` | `agent_age_in_days` drifts with `CURRENT_DATE()`. |
| ACC/PRD warehouse IDs | Confirm / update `warehouse_id` in `databricks.yml` after first deploy. |
