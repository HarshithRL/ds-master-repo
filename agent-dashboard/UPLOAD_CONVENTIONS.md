# Upload Conventions — Agent Dashboard Phase 1

Self-service refresh: export from each platform → upload to the volume **root** with the exact filename → file trigger (when unpaused) runs the full pipeline → dashboard auto-publishes.

## Volume path (root only)

Pattern (catalog = `automation_{d|a|p}` per environment):

```
/Volumes/{catalog}/bronze/bronze_volume/
```

DEV/TEST example:

```
/Volumes/automation_d/bronze/bronze_volume/
```

**Do not** upload into subfolders (`new_set/`, `air_monitoring/`, `archive/`, etc.). Notebook 01 only processes the volume root.

## Required filenames (exact)

| Platform export | Upload filename | Format | Target table |
|-----------------|-----------------|--------|--------------|
| Agents Inventory | `agents_inventory.xlsx` | Excel | `agents_inventory` |
| Agent-Level Credit (30d) | `agent_level_credit_consumption.xlsx` | Excel | `agent_level_credit_consumption` |
| Environment-Level Credit (30d) | `environment_level_credit_consumption.xlsx` | Excel | `environment_level_credit_consumption` |
| User-Level Credit (30d) | `user_level_credit_consumption.xlsx` | Excel | `user_level_credit_consumption` |
| Copilot Studio Kit | `copilot_studio_kit_all_records.xlsx` | Excel | `copilot_studio_kit_all_records` |
| PVA Bot Usage (COE Kit) | `bot_usage_pp_coe_kit.xlsx` | Excel | `bot_usage_pp_coe_kit` |
| Microsoft Purview Audit Log | `microsoft_purview_audit_log.csv` | **CSV** | `microsoft_purview_audit_log` |

## CLI example (DEV)

```powershell
databricks fs cp ".\agents_inventory.xlsx" `
  dbfs:/Volumes/automation_d/bronze/bronze_volume/agents_inventory.xlsx `
  --profile adb-7181820732839861 --overwrite
```

## Rules

1. **One canonical file per table** in the root at run time.
2. **Purview:** use `.csv` (180-day exports are too large for Excel). If both `.csv` and `.xlsx` exist, the pipeline prefers `.csv`.
3. **Do not** upload duplicate bot files (`bot_usage_pp_coe_kit.xlsx` AND `Bot Usage - PP COE Kit.xlsx`) — pipeline picks one and skips the other.
4. After a successful load, files are moved to `archive/YYYY-MM-DD/` so the file-arrival trigger does not re-fire on the same upload.
5. Legacy display-name aliases (e.g. `Agents Inventory.xlsx`) are still accepted at lower priority.

## Load mode

| Mode | Behavior | When to use |
|------|----------|-------------|
| **incremental** (default) | Appends only new rows (deduped) | Normal daily / self-service uploads |
| **overwrite** | Replaces the whole table from the file | One-time rebuild / disaster recovery (manual job param only) |

### Dedup keys (incremental)

| Table | Dedup key |
|-------|-----------|
| `microsoft_purview_audit_log` | `RecordId` |
| `agents_inventory` | `Item_ID` |
| `bot_usage_pp_coe_kit` | `Do_Not_Modify_PVA_Bot_Usage` |
| Credit / studio-kit exports | `_row_hash` (full-row MD5) |

### Known trade-off

If an agent is **removed** from a platform export, incremental bronze **keeps** the old row. Run a one-time job with `load_mode=overwrite` on the affected file(s) to rebuild a clean snapshot.

## What happens after upload

```
upload → Ingest_bronze → Silver_preprocess → Gold_dimensional
  → (Bot / Copilot / Governance metrics in parallel)
  → Validate_dashboard → Publish_dashboard
```

Job (bundle resource key): **`agent_dashboard`** — display name **Agent Dashboard Phase 1 Pipeline**.  
Dashboard: deployed from `src/dashboards/agent_dashboard_phase1.lvdash.json` (DEV id `01f19237ae0419ea830abdda6219869d`).
