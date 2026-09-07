# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# DBTITLE 1,Copilot Dashboard - Pipeline Orchestrator
# MAGIC %md
# MAGIC # Copilot Dashboard — Pipeline Orchestrator
# MAGIC
# MAGIC Runs the full pipeline end-to-end:
# MAGIC
# MAGIC | Step | Notebook | Purpose |
# MAGIC |------|----------|---------|
# MAGIC | 0 | `00_sharepoint_to_volume` | Download 7 files from SharePoint → volume |
# MAGIC | 1 | `01_bronze_ingestion` | Volume files → bronze Delta tables |
# MAGIC | 2 | `02_silver_dimensional` | Silver normalize + dims + facts + views |
# MAGIC | 3 | `03_metrics_validate_publish` | Metric views + validate + publish dashboard |
# MAGIC
# MAGIC **Fail-fast:** If any step fails, the pipeline stops immediately.
# MAGIC
# MAGIC **Usage:** Run this notebook directly or schedule it as a Job.

# COMMAND ----------

# DBTITLE 1,Configuration
import json, time, os
from datetime import datetime

# ---------------------------------------------------------------------------
# Parameters (passed by DAB job or manually via widgets)
# ---------------------------------------------------------------------------
dbutils.widgets.text("catalog", "automation_d", "Catalog")
dbutils.widgets.text("warehouse_id", "69ada62b2fb9b9e2", "Warehouse ID")

CATALOG = dbutils.widgets.get("catalog")
WAREHOUSE_ID = dbutils.widgets.get("warehouse_id")

# Resolve notebook base path dynamically (works in any deployment target)
BASE = os.path.dirname(dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get())

STEPS = [
    {
        "name": "00_sharepoint_to_volume",
        "path": f"{BASE}/00_sharepoint_to_volume",
        "timeout": 30,  # minutes
        "params": {"catalog": CATALOG},
    },
    {
        "name": "01_bronze_ingestion",
        "path": f"{BASE}/01_bronze_ingestion",
        "timeout": 30,
        "params": {"catalog": CATALOG, "load_mode": "overwrite"},
    },
    {
        "name": "02_silver_dimensional",
        "path": f"{BASE}/02_silver_dimensional",
        "timeout": 30,
        "params": {"catalog": CATALOG},
    },
    {
        "name": "03_metrics_validate_publish",
        "path": f"{BASE}/03_metrics_validate_publish",
        "timeout": 30,
        "params": {"catalog": CATALOG, "warehouse_id": WAREHOUSE_ID},
    },
]

# Dashboard — read ID from persistent config on the volume
VOLUME_BASE = f"/Volumes/{CATALOG}/bronze/bronze_volume/Copilot_Dashboard_Data"
CONFIG_FILE = f"{VOLUME_BASE}/_pipeline_config.json"

try:
    with open(CONFIG_FILE) as f:
        _cfg = json.load(f)
    DASHBOARD_ID = _cfg.get("dashboard_id")
    print(f"Dashboard ID from config: {DASHBOARD_ID or '(not set yet)'}")
except FileNotFoundError:
    DASHBOARD_ID = None
    print("No pipeline config — 03 will create dashboard from template.")

print(f"Pipeline run started at {datetime.now():%Y-%m-%d %H:%M:%S}")
print(f"Steps: {len(STEPS)}")

# COMMAND ----------

# DBTITLE 1,Run Pipeline Steps
# ---------------------------------------------------------------------------
# Execute each step sequentially; fail-fast on error
# ---------------------------------------------------------------------------
results = []
pipeline_start = time.time()

for i, step in enumerate(STEPS):
    print(f"\n{'='*60}")
    print(f"STEP {i}/{len(STEPS)-1}: {step['name']}")
    print(f"{'='*60}")
    
    step_start = time.time()
    try:
        result_json = dbutils.notebook.run(
            step["path"],
            timeout_seconds=step["timeout"] * 60,
            arguments=step["params"],
        )
        elapsed = time.time() - step_start
        
        # Try to parse JSON exit value
        try:
            result = json.loads(result_json) if result_json else {}
        except (json.JSONDecodeError, TypeError):
            result = {"raw": str(result_json)}
        
        results.append({
            "step": step["name"],
            "status": "SUCCESS",
            "elapsed_min": round(elapsed / 60, 2),
            "result": result,
        })
        print(f"  ✓ {step['name']} completed in {elapsed/60:.1f} min")
        
        # Pass run_folder from step 00 to step 01
        if step["name"] == "00_sharepoint_to_volume" and isinstance(result, dict):
            run_folder = result.get("run_folder", "")
            if run_folder:
                STEPS[1]["params"]["run_folder"] = run_folder
                print(f"  → Passing run_folder to 01: {run_folder}")
        
    except Exception as e:
        elapsed = time.time() - step_start
        results.append({
            "step": step["name"],
            "status": "FAILED",
            "elapsed_min": round(elapsed / 60, 2),
            "error": str(e),
        })
        print(f"  ✗ {step['name']} FAILED after {elapsed/60:.1f} min")
        print(f"    Error: {e}")
        break  # fail-fast

pipeline_elapsed = time.time() - pipeline_start
print(f"\n{'='*60}")
print(f"Pipeline finished in {pipeline_elapsed/60:.1f} min")

# COMMAND ----------

# DBTITLE 1,Refresh Dashboard
# ---------------------------------------------------------------------------
# Dashboard refresh (03 handles creation + renames; this is a final publish)
# ---------------------------------------------------------------------------
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

all_ok = all(r["status"] == "SUCCESS" for r in results)

# 03 may have created a new dashboard — re-read config for latest ID
try:
    with open(CONFIG_FILE) as f:
        _cfg2 = json.load(f)
    DASHBOARD_ID = _cfg2.get("dashboard_id", DASHBOARD_ID)
except FileNotFoundError:
    pass

if all_ok and DASHBOARD_ID:
    print("All steps succeeded. Publishing dashboard...")
    try:
        w.lakeview.publish(
            dashboard_id=DASHBOARD_ID,
            warehouse_id=WAREHOUSE_ID,
            embed_credentials=True,
        )
        print(f"  \u2713 Dashboard {DASHBOARD_ID} published")
    except Exception as e:
        print(f"  \u26a0 Dashboard publish warning: {e}")
        print("  Data is updated; manual publish may be needed.")
elif all_ok and not DASHBOARD_ID:
    print("All steps succeeded but no dashboard ID — 03 should have created it.")
else:
    failed = [r for r in results if r["status"] == "FAILED"]
    print(f"\u26a0 Pipeline had failures - dashboard NOT refreshed.")
    print(f"  Failed step: {failed[0]['step']}")
    print(f"  Error: {failed[0]['error']}")

# COMMAND ----------

# DBTITLE 1,Summary
# ---------------------------------------------------------------------------
# Final summary
# ---------------------------------------------------------------------------
print("\n" + "="*60)
print("PIPELINE SUMMARY")
print("="*60)
for r in results:
    icon = "✓" if r["status"] == "SUCCESS" else "✗"
    print(f"  {icon} {r['step']:40s} {r['status']:8s} ({r['elapsed_min']} min)")

print(f"\nTotal time: {pipeline_elapsed/60:.1f} min")
print(f"Status: {'ALL OK' if all_ok else 'FAILED'}")

if not all_ok:
    raise RuntimeError(f"Pipeline failed at step: {failed[0]['step']}")

# Exit with summary for Job monitoring
dbutils.notebook.exit(json.dumps({
    "status": "SUCCESS" if all_ok else "FAILED",
    "total_min": round(pipeline_elapsed / 60, 2),
    "steps": results,
}))

# COMMAND ----------


