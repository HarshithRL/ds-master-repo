# Databricks notebook source
# DBTITLE 1,Header
# MAGIC %md
# MAGIC # Step 2 — Load from Excel (ACC / PRD)
# MAGIC
# MAGIC Reads the `.xlsx` files exported by `1_Export_to_Excel_DEV` and loads them into the target catalog tables.
# MAGIC
# MAGIC **Prerequisites:**
# MAGIC - Excel files uploaded to this workspace's volume (see paths in Cell 1)
# MAGIC - Cell 1: set `TARGET_CATALOG` to `automation_a` or `automation_p`
# MAGIC
# MAGIC | Excel File | Target Table | Mode |
# MAGIC |---|---|---|
# MAGIC | `output_table_*.xlsx` | `automation_*.gold.air_monitoring_output` | APPEND (new rows only, row_id dedup) |
# MAGIC | `sites_*.xlsx` | `automation_*.gold.air_monitoring_sites` | OVERWRITE |
# MAGIC | — | `automation_*.bronze.air_monitoring_upload_log` | CREATE if not exists |

# COMMAND ----------

# DBTITLE 1,Cell 1 — Config
# ============================================================
# CELL 1 — Config
# Change TARGET_CATALOG and file names per environment.
# Can also be passed as job base_parameters.
# ============================================================
try:
    dbutils.widgets.text("TARGET_CATALOG", "automation_a")
    dbutils.widgets.text("OUTPUT_EXCEL",   "auto")  # 'auto' = pick latest file
    dbutils.widgets.text("SITES_EXCEL",    "auto")  # 'auto' = pick latest file, '' = skip
except Exception:
    pass

TARGET_CATALOG = dbutils.widgets.get("TARGET_CATALOG")  # automation_a or automation_p
OUTPUT_EXCEL   = dbutils.widgets.get("OUTPUT_EXCEL")     # e.g. 'output_table_20260715_1030.xlsx'
SITES_EXCEL    = dbutils.widgets.get("SITES_EXCEL")      # e.g. 'sites_20260715_1030.xlsx' or '' to skip

BRONZE_SCHEMA  = "bronze"
GOLD_SCHEMA    = "gold"
VOLUME_NAME    = "bronze_volume"

LOAD_VOLUME    = f"/Volumes/{TARGET_CATALOG}/{BRONZE_SCHEMA}/{VOLUME_NAME}/migration_exports"
TARGET_OUTPUT  = f"{TARGET_CATALOG}.{GOLD_SCHEMA}.air_monitoring_output"
TARGET_SITES   = f"{TARGET_CATALOG}.{GOLD_SCHEMA}.air_monitoring_sites"
TARGET_UPLOADS = f"{TARGET_CATALOG}.{BRONZE_SCHEMA}.air_monitoring_upload_log"

print(f"Target catalog : {TARGET_CATALOG}")
print(f"Load volume    : {LOAD_VOLUME}")
print(f"Target output  : {TARGET_OUTPUT}")
print(f"Target sites   : {TARGET_SITES}")
print(f"OUTPUT_EXCEL   : {OUTPUT_EXCEL}")
print(f"SITES_EXCEL    : {SITES_EXCEL}")

# COMMAND ----------

# DBTITLE 1,Cell 2 — Load from Excel
# ============================================================
# CELL 2 — Load
# Reads Excel files from the volume and writes to target tables.
#
# output_table : APPEND — only rows whose row_id is NOT already
#                in the target (safe for concurrent app usage).
# sites        : OVERWRITE — full replace.
# upload_log   : CREATE empty table if it does not exist yet.
# ============================================================
%pip install openpyxl --quiet

import pandas as pd
import os
from pyspark.sql.types import (
    StructType, StructField, StringType, TimestampType, IntegerType
)
import warnings
warnings.filterwarnings("ignore")

def _latest_file(volume_path, prefix):
    """Return the most-recent .xlsx in volume_path starting with prefix."""
    try:
        files = [f for f in os.listdir(volume_path)
                 if f.startswith(prefix) and f.endswith(".xlsx")]
        files.sort(reverse=True)
        return files[0] if files else None
    except Exception:
        return None

# --- Resolve file names (auto or explicit) -----------------
_out_file   = OUTPUT_EXCEL if OUTPUT_EXCEL not in ("auto", "") else _latest_file(LOAD_VOLUME, "output_table")
_sites_file = SITES_EXCEL  if SITES_EXCEL  not in ("auto", "") else _latest_file(LOAD_VOLUME, "sites")

assert _out_file, (
    f"No output_table*.xlsx found in {LOAD_VOLUME}.\n"
    "Upload the file first, then re-run this cell."
)
print(f"output_table file : {_out_file}")
if _sites_file:
    print(f"sites file        : {_sites_file}")
else:
    print("sites file        : (not found / skipped)")
print()

# --- output_table : APPEND new rows only -------------------
df_excel = pd.read_excel(f"{LOAD_VOLUME}/{_out_file}", engine="openpyxl")
df_spark = spark.createDataFrame(df_excel.astype(str).where(df_excel.notna(), other=None))
n_excel  = df_spark.count()

try:
    existing_ids = spark.table(TARGET_OUTPUT).select("row_id")
    df_to_write  = df_spark.join(existing_ids, "row_id", "left_anti")
    n_skip       = n_excel - df_to_write.count()
except Exception:
    df_to_write = df_spark
    n_skip      = 0

n_write = df_to_write.count()
if n_write == 0:
    print(f"[output]  All {n_excel:,} rows already present — skipped.")
else:
    df_to_write.write.mode("append").option("mergeSchema", "true").saveAsTable(TARGET_OUTPUT)
    print(f"[output]  APPEND: {n_write:,} new rows → {TARGET_OUTPUT}")
    if n_skip:
        print(f"          ({n_skip:,} rows already existed — skipped by row_id check)")

# --- sites : OVERWRITE -------------------------------------
if _sites_file and SITES_EXCEL != "":
    df_sites_pd = pd.read_excel(f"{LOAD_VOLUME}/{_sites_file}", engine="openpyxl")
    df_sites_sp = spark.createDataFrame(df_sites_pd.astype(str).where(df_sites_pd.notna(), other=None))
    df_sites_sp.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(TARGET_SITES)
    print(f"[sites]   OVERWRITE: {df_sites_sp.count():,} rows → {TARGET_SITES}")
else:
    print("[sites]   Skipped.")

# --- upload_log : CREATE if not exists ---------------------
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
    print(f"[upload_log] Already exists ({n_log:,} rows) — not touched.")
except Exception:
    spark.createDataFrame([], upload_log_schema) \
        .write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(TARGET_UPLOADS)
    print(f"[upload_log] CREATED (empty) → {TARGET_UPLOADS}")

print()
print("=" * 65)
print("LOAD COMPLETE")
print("=" * 65)

# COMMAND ----------


