# Databricks notebook source
# DBTITLE 1,Header
# MAGIC %md
# MAGIC # Load from Excel — Air Monitoring Migration
# MAGIC
# MAGIC Reads Excel files from UC Volume subfolders and loads into target catalog tables.
# MAGIC
# MAGIC **Volume structure** (per environment):
# MAGIC ```
# MAGIC /Volumes/{catalog}/bronze/bronze_volume/air_monitoring/
# MAGIC ├── first_migration/    ← Initial V1 full export (run once)
# MAGIC │   └── output_table.xlsx
# MAGIC ├── update_from_v1/     ← Incremental updates (run time-to-time)
# MAGIC │   └── output_table.xlsx
# MAGIC ├── sites/              ← Site config (overwrite anytime)
# MAGIC │   └── sites.xlsx
# MAGIC └── uploaded_reports/   ← App PDFs (NEVER TOUCHED by this notebook)
# MAGIC ```
# MAGIC
# MAGIC **Jobs** (run manually when needed):
# MAGIC | Job | LOAD_MODE | When to use |
# MAGIC |-----|-----------|-------------|
# MAGIC | Initial Migration | `initial` | First-time setup on empty env |
# MAGIC | Update from V1 | `incremental` | When V1 has new records |
# MAGIC | Sites Update | `sites` | When site config changes |
# MAGIC
# MAGIC **Safety guarantees:**
# MAGIC - App-uploaded rows → **NEVER overwritten** (different row_ids, LEFT ANTI JOIN)
# MAGIC - upload_log → **NEVER touched** (only CREATE if not exists)
# MAGIC - uploaded_reports volume → **NEVER touched**
# MAGIC - Re-running with same Excel → 0 new rows (idempotent)

# COMMAND ----------

# DBTITLE 1,Cell 1 — Parameters
# ============================================================
# PARAMETERS — passed by job or set manually via widgets
# ============================================================
try:
    dbutils.widgets.dropdown("LOAD_MODE", "incremental", ["initial", "incremental", "sites"])
    dbutils.widgets.text("TARGET_CATALOG", "automation_a")
except Exception:
    pass

LOAD_MODE      = dbutils.widgets.get("LOAD_MODE")       # initial | incremental | sites
TARGET_CATALOG = dbutils.widgets.get("TARGET_CATALOG")  # automation_d | automation_a | automation_p

# ============================================================
# DERIVED PATHS
# ============================================================
BRONZE_SCHEMA = "bronze"
VOLUME_BASE   = f"/Volumes/{TARGET_CATALOG}/{BRONZE_SCHEMA}/bronze_volume/air_monitoring"

# Source folders (user uploads Excel here manually)
FIRST_MIGRATION_PATH = f"{VOLUME_BASE}/first_migration"
UPDATE_FROM_V1_PATH  = f"{VOLUME_BASE}/update_from_v1"
SITES_PATH           = f"{VOLUME_BASE}/sites"

# Target tables
TARGET_OUTPUT  = f"{TARGET_CATALOG}.{BRONZE_SCHEMA}.air_monitoring_output"
TARGET_SITES   = f"{TARGET_CATALOG}.{BRONZE_SCHEMA}.air_monitoring_sites"
TARGET_UPLOADS = f"{TARGET_CATALOG}.{BRONZE_SCHEMA}.air_monitoring_upload_log"

print(f"{'='*65}")
print(f"  LOAD_MODE      : {LOAD_MODE}")
print(f"  TARGET_CATALOG : {TARGET_CATALOG}")
print(f"  VOLUME_BASE    : {VOLUME_BASE}")
print(f"{'='*65}")
print(f"  Source paths:")
if LOAD_MODE == "initial":
    print(f"    Output Excel : {FIRST_MIGRATION_PATH}/")
elif LOAD_MODE == "incremental":
    print(f"    Output Excel : {UPDATE_FROM_V1_PATH}/")
elif LOAD_MODE == "sites":
    print(f"    Sites Excel  : {SITES_PATH}/")
print(f"  Target tables:")
print(f"    output       : {TARGET_OUTPUT}")
print(f"    sites        : {TARGET_SITES}")
print(f"    upload_log   : {TARGET_UPLOADS}")
print(f"{'='*65}")

# COMMAND ----------

# DBTITLE 1,Cell 2 — Install dependencies
# BUG FIX: %pip MUST be in its own cell (Databricks restarts Python after pip)
%pip install openpyxl --quiet

# COMMAND ----------

# DBTITLE 1,Cell 3 — Load Logic
import pandas as pd
import numpy as np
import os
from pyspark.sql.types import (
    StructType, StructField, StringType, TimestampType,
    IntegerType, BooleanType, DoubleType
)
import warnings
warnings.filterwarnings("ignore")


def _find_excel(folder_path, prefix=""):
    """Find the most recent .xlsx file in a volume folder."""
    try:
        files = [f for f in os.listdir(folder_path)
                 if f.endswith(".xlsx") and (not prefix or f.startswith(prefix))]
        files.sort(reverse=True)
        return files[0] if files else None
    except FileNotFoundError:
        return None


def _prepare_dataframe(df_excel):
    """
    Convert pandas DataFrame to Spark-ready format preserving critical types.
    
    BUG FIX: Previous version used astype(str) for ALL columns, which:
    - Turned Flag_High_Concentration into STRING "True"/"False" → app.py sum() breaks
    - Turned Flag_EM_Concentration into STRING "0.0"/"1.0" → type mismatch
    
    FIX: Preserve BOOLEAN/DOUBLE types, convert everything else to STRING safely.
    """
    df = df_excel.copy()
    
    # --- Preserve BOOLEAN columns ---
    bool_cols = ["Flag_High_Concentration"]
    for col in bool_cols:
        if col in df.columns:
            # Handle various representations: True/False, "True"/"False", 1/0
            df[col] = df[col].apply(
                lambda x: True if str(x).lower() in ("true", "1", "1.0")
                else (False if str(x).lower() in ("false", "0", "0.0")
                      else None) if pd.notna(x) else None
            )
    
    # --- Preserve DOUBLE columns ---
    float_cols = ["Flag_EM_Concentration"]
    for col in float_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    
    # --- Convert remaining columns to STRING (safely handling NaN/NaT) ---
    for col in df.columns:
        if col in bool_cols or col in float_cols:
            continue  # Already handled above
        # Convert to string, replacing NaN/NaT/None with None (→ SQL NULL)
        df[col] = df[col].apply(
            lambda x: str(x) if pd.notna(x) and str(x) not in ("nan", "NaT", "None", "") else None
        )
    
    return spark.createDataFrame(df)


def _load_output(source_path, mode_label):
    """
    Load output_table Excel → INSERT only new rows (LEFT ANTI JOIN on row_id).
    
    SAFETY: App-uploaded rows have different row_ids from migration rows.
    They will NEVER be matched by the anti-join → NEVER overwritten or deleted.
    """
    excel_file = _find_excel(source_path)
    if not excel_file:
        print(f"[output/{mode_label}] ⚠️  No .xlsx found in {source_path}")
        print(f"                    Upload the Excel file first, then re-run.")
        return

    full_path = f"{source_path}/{excel_file}"
    print(f"[output/{mode_label}] Reading: {excel_file}")

    # Read Excel (pandas infers types from content)
    df_excel = pd.read_excel(full_path, engine="openpyxl")
    
    # --- CRITICAL CHECK: row_id column must exist ---
    assert "row_id" in df_excel.columns, (
        f"ERROR: Excel file is missing 'row_id' column!\n"
        f"File: {full_path}\n"
        f"Columns found: {list(df_excel.columns)[:10]}...\n\n"
        f"This means the Excel was NOT exported from DEV via '2_Export_to_Excel_DEV'.\n"
        f"row_id is required for safe deduplication (LEFT ANTI JOIN).\n"
        f"Please export from DEV first, then upload that file."
    )
    
    # Convert to Spark DataFrame with proper types
    df_spark = _prepare_dataframe(df_excel)
    n_excel = df_spark.count()
    print(f"[output/{mode_label}] Excel rows: {n_excel:,}")

    # LEFT ANTI JOIN: only keep rows whose row_id is NOT in target
    try:
        existing_ids = spark.table(TARGET_OUTPUT).select("row_id")
        df_to_write = df_spark.join(existing_ids, "row_id", "left_anti")
        n_existing = existing_ids.count()
        n_skip = n_excel - df_to_write.count()
        print(f"[output/{mode_label}] Target has {n_existing:,} existing rows")
    except Exception as e:
        # Table doesn't exist yet → write everything
        print(f"[output/{mode_label}] Table not found (will be created): {type(e).__name__}")
        df_to_write = df_spark
        n_existing = 0
        n_skip = 0

    n_write = df_to_write.count()

    if n_write == 0:
        print(f"[output/{mode_label}] ✅ All {n_excel:,} rows already present — 0 new rows.")
    else:
        df_to_write.write.mode("append").option("mergeSchema", "true").saveAsTable(TARGET_OUTPUT)
        print(f"[output/{mode_label}] ✅ APPEND: {n_write:,} new rows → {TARGET_OUTPUT}")
        if n_skip:
            print(f"                    ({n_skip:,} rows already existed — skipped)")

    # Verify final state
    final_count = spark.table(TARGET_OUTPUT).count()
    print(f"[output/{mode_label}] Target table total: {final_count:,} rows")


def _load_sites():
    """
    Load sites Excel → OVERWRITE sites table.
    Safe because sites is config/dimension data, not user-generated content.
    """
    excel_file = _find_excel(SITES_PATH)
    if not excel_file:
        print(f"[sites] ⚠️  No .xlsx found in {SITES_PATH}")
        print(f"        Upload sites.xlsx first, then re-run.")
        return

    full_path = f"{SITES_PATH}/{excel_file}"
    print(f"[sites] Reading: {excel_file}")

    df_sites_pd = pd.read_excel(full_path, engine="openpyxl")
    # Sites table is all STRING columns — safe to use astype(str)
    df_sites_sp = spark.createDataFrame(
        df_sites_pd.astype(str).where(df_sites_pd.notna(), other=None)
    )
    n_sites = df_sites_sp.count()
    df_sites_sp.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(TARGET_SITES)
    print(f"[sites] ✅ OVERWRITE: {n_sites:,} rows → {TARGET_SITES}")


def _ensure_upload_log():
    """
    CREATE upload_log table if it doesn't exist. NEVER touches existing data.
    This table is managed by the app — records are added per upload event.
    """
    upload_log_schema = StructType([
        StructField("upload_id",            StringType(),    True),
        StructField("batch_id",             StringType(),    True),
        StructField("filename",             StringType(),    True),
        StructField("site_code",            StringType(),    True),
        StructField("site_name",            StringType(),    True),
        StructField("uploaded_by",          StringType(),    True),
        StructField("upload_time",          TimestampType(), True),
        StructField("num_records",          IntegerType(),   True),
        StructField("num_duplicates_found", IntegerType(),   True),
        StructField("num_saved",            IntegerType(),   True),
        StructField("status",               StringType(),    True),
        StructField("volume_path",          StringType(),    True),
    ])
    try:
        n_log = spark.table(TARGET_UPLOADS).count()
        print(f"[upload_log] Already exists ({n_log:,} rows) — NOT touched.")
    except Exception:
        spark.createDataFrame([], upload_log_schema) \
            .write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(TARGET_UPLOADS)
        print(f"[upload_log] ✅ CREATED (empty) → {TARGET_UPLOADS}")


# ============================================================
# EXECUTE based on LOAD_MODE
# ============================================================
print()

if LOAD_MODE == "initial":
    print("▶ MODE: Initial Migration (first_migration/)")
    print("  Reading from:", FIRST_MIGRATION_PATH)
    print()
    _load_output(FIRST_MIGRATION_PATH, "initial")
    _ensure_upload_log()

elif LOAD_MODE == "incremental":
    print("▶ MODE: Incremental Update (update_from_v1/)")
    print("  Reading from:", UPDATE_FROM_V1_PATH)
    print()
    _load_output(UPDATE_FROM_V1_PATH, "incremental")
    _ensure_upload_log()  # BUG FIX: ensure table exists even if initial was never run

elif LOAD_MODE == "sites":
    print("▶ MODE: Sites Update (sites/)")
    print("  Reading from:", SITES_PATH)
    print()
    _load_sites()
    _ensure_upload_log()  # App needs this table to function

print()
print("=" * 65)
print("✅ LOAD COMPLETE")
print("=" * 65)

