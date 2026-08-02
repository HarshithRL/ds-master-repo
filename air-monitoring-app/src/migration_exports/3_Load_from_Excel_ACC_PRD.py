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
# MAGIC │   └── Output_Table.xlsx
# MAGIC ├── update_from_v1/     ← Incremental updates (run time-to-time)
# MAGIC │   └── Output_Table.xlsx
# MAGIC ├── sites/              ← Site config (overwrite anytime)
# MAGIC │   └── sites.xlsx
# MAGIC └── uploaded_reports/   ← App PDFs (NEVER TOUCHED by this notebook)
# MAGIC ```
# MAGIC
# MAGIC **Excel format**: Raw V1 export (23 columns, NO row_id).
# MAGIC This notebook GENERATES the 7 additional columns (row_id, row_status, etc.)
# MAGIC
# MAGIC **Dedup strategy**: LEFT ANTI JOIN on expanded grain:
# MAGIC `Code + Sample_no + Sample_Date + Volume + Concentration_result + Document_name`
# MAGIC (row_id can't be used — it's generated fresh each time and differs between runs)
# MAGIC
# MAGIC **Safety guarantees:**
# MAGIC - App-uploaded rows → **NEVER overwritten** (anti-join on 6-col grain, not row_id)
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

# Source folders
FIRST_MIGRATION_PATH = f"{VOLUME_BASE}/first_migration"
UPDATE_FROM_V1_PATH  = f"{VOLUME_BASE}/update_from_v1"
SITES_PATH           = f"{VOLUME_BASE}/sites"

# Target tables
TARGET_OUTPUT  = f"{TARGET_CATALOG}.{BRONZE_SCHEMA}.air_monitoring_output"
TARGET_SITES   = f"{TARGET_CATALOG}.{BRONZE_SCHEMA}.air_monitoring_sites"
TARGET_UPLOADS = f"{TARGET_CATALOG}.{BRONZE_SCHEMA}.air_monitoring_upload_log"

# Expanded grain for dedup (6 columns — from TECHNICAL_DOCUMENTATION.md)
DEDUP_GRAIN = ["Code", "Sample_no", "Sample_Date", "Volume", "Concentration_result", "Document_name"]

print(f"{'='*65}")
print(f"  LOAD_MODE      : {LOAD_MODE}")
print(f"  TARGET_CATALOG : {TARGET_CATALOG}")
print(f"  VOLUME_BASE    : {VOLUME_BASE}")
print(f"  DEDUP_GRAIN    : {DEDUP_GRAIN}")
print(f"{'='*65}")

# COMMAND ----------

# DBTITLE 1,Cell 2 — Install dependencies
%pip install openpyxl --quiet

# COMMAND ----------

# DBTITLE 1,Cell 3 — Load Logic
import pandas as pd
import numpy as np
import uuid
import os
from datetime import datetime
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType, StructField, StringType, TimestampType,
    IntegerType, BooleanType, DoubleType
)
import warnings
warnings.filterwarnings("ignore")


def _find_excel(folder_path):
    """Find the most recent .xlsx file in a volume folder."""
    try:
        files = [f for f in os.listdir(folder_path) if f.endswith(".xlsx")]
        files.sort(reverse=True)
        return files[0] if files else None
    except FileNotFoundError:
        return None


def _prepare_output_dataframe(df_excel):
    """
    Transform raw V1 Excel (23 cols) into the full Delta schema (30 cols).
    
    Generates 7 additional columns:
      - row_id: UUID4 per row (unique identifier)
      - row_status: 'active' or 'removed' (from Frozen_Docs)
      - removal_reason: 'V1 frozen document' if removed
      - status_updated_at: None
      - uploaded_by: 'migrated'
      - upload_batch_id: batch identifier with timestamp
      - modified_by: None
    
    Transforms:
      - Sample_Date: datetime → 'DD-Mon-YYYY' string (e.g. '01-Jul-2026')
      - Code: ensure string type
      - Flag_High_Concentration: bool (preserved)
      - Flag_EM_Concentration: int → float
    """
    df = df_excel.copy()
    batch_id = f"excel_migration_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # --- Generate 7 additional columns ---
    df["row_id"] = [str(uuid.uuid4()) for _ in range(len(df))]
    df["row_status"] = df["Frozen_Docs"].apply(
        lambda x: "removed" if str(x).strip().lower() == "x" else "active"
    )
    df["removal_reason"] = df["row_status"].apply(
        lambda x: "V1 frozen document" if x == "removed" else None
    )
    df["status_updated_at"] = None
    df["uploaded_by"] = "migrated"
    df["upload_batch_id"] = batch_id
    df["modified_by"] = None
    
    # --- Transform Sample_Date: datetime → 'DD-Mon-YYYY' string ---
    if "Sample_Date" in df.columns and pd.api.types.is_datetime64_any_dtype(df["Sample_Date"]):
        df["Sample_Date"] = df["Sample_Date"].apply(
            lambda x: x.strftime("%d-%b-%Y") if pd.notna(x) else None
        )
    
    # --- Ensure Code is string ---
    if "Code" in df.columns:
        df["Code"] = df["Code"].apply(lambda x: str(int(x)) if pd.notna(x) and isinstance(x, (int, float)) else str(x) if pd.notna(x) else None)
    
    # --- Preserve Flag_High_Concentration as BOOLEAN ---
    if "Flag_High_Concentration" in df.columns:
        df["Flag_High_Concentration"] = df["Flag_High_Concentration"].apply(
            lambda x: bool(x) if pd.notna(x) else None
        )
    
    # --- Flag_EM_Concentration: int → float ---
    if "Flag_EM_Concentration" in df.columns:
        df["Flag_EM_Concentration"] = pd.to_numeric(df["Flag_EM_Concentration"], errors="coerce").astype("float64")
    
    # --- Convert all remaining object columns: NaN → None ---
    for col in df.columns:
        if col in ("Flag_High_Concentration", "Flag_EM_Concentration"):
            continue
        if df[col].dtype == "object" or df[col].dtype == "float64":
            df[col] = df[col].apply(
                lambda x: str(x) if pd.notna(x) and str(x) not in ("nan", "NaT", "None") else None
            )
        elif pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = df[col].apply(
                lambda x: x.isoformat() if pd.notna(x) else None
            )
    
    return spark.createDataFrame(df)


def _load_output(source_path, mode_label):
    """
    Load V1 output Excel → generate migration columns → INSERT only NEW rows.
    
    Dedup: LEFT ANTI JOIN on expanded grain (6 columns).
    NOT on row_id (which is generated fresh each run and would never match).
    
    SAFETY: App-uploaded rows have different grain values (different Document_name,
    Sample_no patterns, etc.) — they will NEVER be matched → NEVER overwritten.
    Even if grain somehow matches, anti-join only SKIPS insertion — never deletes.
    """
    excel_file = _find_excel(source_path)
    if not excel_file:
        print(f"[output/{mode_label}] ⚠️  No .xlsx found in {source_path}")
        print(f"                    Upload the Excel file first, then re-run.")
        return

    full_path = f"{source_path}/{excel_file}"
    print(f"[output/{mode_label}] Reading: {excel_file}")

    # Read raw V1 Excel (23 columns)
    df_excel = pd.read_excel(full_path, engine="openpyxl")
    print(f"[output/{mode_label}] Excel rows: {len(df_excel):,} | Columns: {len(df_excel.columns)}")
    
    # Transform: generate row_id, row_status, etc. + type conversions
    df_spark = _prepare_output_dataframe(df_excel)
    n_excel = df_spark.count()
    print(f"[output/{mode_label}] Prepared DataFrame: {n_excel:,} rows, {len(df_spark.columns)} columns")

    # LEFT ANTI JOIN on expanded grain (6 columns)
    # This checks: does a row with the SAME Code+Sample_no+Sample_Date+Volume+
    # Concentration_result+Document_name already exist in the target?
    try:
        existing = spark.table(TARGET_OUTPUT).select(*DEDUP_GRAIN)
        df_to_write = df_spark.join(existing, DEDUP_GRAIN, "left_anti")
        n_existing = spark.table(TARGET_OUTPUT).count()
        n_write = df_to_write.count()
        n_skip = n_excel - n_write
        print(f"[output/{mode_label}] Target has {n_existing:,} existing rows")
        print(f"[output/{mode_label}] Grain match (skipped): {n_skip:,} | Net new: {n_write:,}")
    except Exception as e:
        # Table doesn't exist → write everything
        print(f"[output/{mode_label}] Table not found (will be created): {type(e).__name__}")
        df_to_write = df_spark
        n_write = n_excel

    if n_write == 0:
        print(f"[output/{mode_label}] ✅ All {n_excel:,} rows already present — 0 new rows.")
    else:
        df_to_write.write.mode("append").option("mergeSchema", "true").saveAsTable(TARGET_OUTPUT)
        print(f"[output/{mode_label}] ✅ APPEND: {n_write:,} new rows → {TARGET_OUTPUT}")

    # Final verification
    final_count = spark.table(TARGET_OUTPUT).count()
    print(f"[output/{mode_label}] Target table total: {final_count:,} rows")


def _load_sites():
    """
    Load sites Excel → OVERWRITE sites table.
    Safe: sites is config/dimension data, not user content.
    """
    excel_file = _find_excel(SITES_PATH)
    if not excel_file:
        print(f"[sites] ⚠️  No .xlsx found in {SITES_PATH}")
        print(f"        Upload sites.xlsx first, then re-run.")
        return

    full_path = f"{SITES_PATH}/{excel_file}"
    print(f"[sites] Reading: {excel_file}")

    df_sites_pd = pd.read_excel(full_path, engine="openpyxl")
    # Sites: all STRING columns — safe to use astype(str)
    df_sites_sp = spark.createDataFrame(
        df_sites_pd.astype(str).where(df_sites_pd.notna(), other=None)
    )
    n_sites = df_sites_sp.count()
    df_sites_sp.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(TARGET_SITES)
    print(f"[sites] ✅ OVERWRITE: {n_sites:,} rows → {TARGET_SITES}")


def _ensure_upload_log():
    """CREATE upload_log table if not exists. NEVER touches existing data."""
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
# EXECUTE
# ============================================================
print()

if LOAD_MODE == "initial":
    print("▶ MODE: Initial Migration (first_migration/)")
    print(f"  Source: {FIRST_MIGRATION_PATH}/")
    print()
    _load_output(FIRST_MIGRATION_PATH, "initial")
    _ensure_upload_log()

elif LOAD_MODE == "incremental":
    print("▶ MODE: Incremental Update (update_from_v1/)")
    print(f"  Source: {UPDATE_FROM_V1_PATH}/")
    print()
    _load_output(UPDATE_FROM_V1_PATH, "incremental")
    _ensure_upload_log()

elif LOAD_MODE == "sites":
    print("▶ MODE: Sites Update (sites/)")
    print(f"  Source: {SITES_PATH}/")
    print()
    _load_sites()
    _ensure_upload_log()

print()
print("=" * 65)
print("✅ LOAD COMPLETE")
print("=" * 65)

