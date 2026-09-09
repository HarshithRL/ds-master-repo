# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# DBTITLE 1,Copilot Dashboard - Pipeline Orchestrator
# MAGIC %md
# MAGIC # Copilot Dashboard — Pipeline Orchestrator
# MAGIC
# MAGIC Runs the full pipeline end-to-end :
# MAGIC
# MAGIC | Step | Notebook | Purpose |
# MAGIC |------|----------|---------|
# MAGIC | 0 | `00_sharepoint_to_volume` | Download 7 files from SharePoint → volume |
# MAGIC | 1 | `01_bronze_ingestion` | Volume files → bronze Delta tables |
# MAGIC | 2 | `02_silver_dimensional` | Silver normalize + dims + facts + views |
# MAGIC | 3 | `03_metrics_validate_publish` | Metric views + validate |
# MAGIC | 4 | `04_promote_dev_dashboard` | DEV→Main diff + _v2 sync + publish dashboard |
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
        "params": {"catalog": CATALOG, "pipeline_schema": f"{CATALOG}.silver"},
    },
    {
        "name": "03_metrics_validate_publish",
        "path": f"{BASE}/03_metrics_validate_publish",
        "timeout": 30,
        "params": {"catalog": CATALOG, "warehouse_id": WAREHOUSE_ID},
    },
    {
        "name": "04_promote_dev_dashboard",
        "path": f"{BASE}/04_promote_dev_dashboard",
        "timeout": 15,
        "params": {"catalog": CATALOG, "warehouse_id": WAREHOUSE_ID, "auto_promote": "no"},
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

# DBTITLE 1,Post-Pipeline Check
# ---------------------------------------------------------------------------
# Post-pipeline check
# Dashboard publish is now handled by step 04_promote_dev_dashboard
# ---------------------------------------------------------------------------
all_ok = all(r["status"] == "SUCCESS" for r in results)

if all_ok:
    # Step 04 result contains dashboard status
    step04 = next((r for r in results if r["step"] == "04_promote_dev_dashboard"), None)
    if step04:
        dash_result = step04.get("result", {})
        print(f"Dashboard status: {dash_result.get('status', 'UNKNOWN')}")
        print(f"  Dashboard ID:  {dash_result.get('dashboard_id', 'N/A')}")
        print(f"  DEV changes:   {dash_result.get('dev_changes', 0)}")
        print(f"  _v2 synced:    {dash_result.get('v2_synced', 0)}")
    else:
        print("Step 04 result not found — check logs.")
else:
    failed = [r for r in results if r["status"] == "FAILED"]
    print(f"\u26a0 Pipeline had failures.")
    print(f"  Failed step: {failed[0]['step']}")
    print(f"  Error: {failed[0].get('error', 'unknown')}")

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


