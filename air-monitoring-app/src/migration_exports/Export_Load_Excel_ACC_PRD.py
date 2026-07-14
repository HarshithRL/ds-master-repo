# Databricks notebook source
# DBTITLE 1,Header
# MAGIC %md
# MAGIC # Excel Export / Load for ACC & PRD
# MAGIC
# MAGIC **Workflow:**
# MAGIC 1. **DEV** — Run Cell 1 + Cell 2: exports `automation_d` tables as Excel to DEV volume
# MAGIC 2. Download Excel files from DEV volume via the Databricks Files UI
# MAGIC 3. Upload them to `automation_a` and `automation_p` volumes manually
# MAGIC 4. **ACC/PRD** — Run Cell 1 + Cell 3: reads Excel from local volume → creates tables
# MAGIC
# MAGIC | File | Rows | Path |
# MAGIC |---|---|---|
# MAGIC | `output_table_TIMESTAMP.xlsx` | ~7,600 | `/Volumes/automation_d/bronze/bronze_volume/migration_exports/` |
# MAGIC | `sites_TIMESTAMP.xlsx` | 53 | same |

# COMMAND ----------

# DBTITLE 1,Cell 1: Config (change per environment)
# ============================================================
# CELL 1 — Config
# Works in two modes:
#   Interactive : change values below and run manually
#   Job (pipeline): values injected via base_parameters (widgets)
# ============================================================

# --- Job parameters (widgets) ---
# When run as a Databricks Job, the pipeline passes these as base_parameters.
# When run interactively, the defaults below are used (or change them manually).
try:
    dbutils.widgets.text("TARGET_CATALOG", "automation_a")
    dbutils.widgets.text("OUTPUT_EXCEL",   "auto")   # 'auto' = pick latest file
    dbutils.widgets.text("SITES_EXCEL",    "auto")   # 'auto' = pick latest file
except Exception:
    pass

TARGET_CATALOG = dbutils.widgets.get("TARGET_CATALOG")
OUTPUT_EXCEL   = dbutils.widgets.get("OUTPUT_EXCEL")
SITES_EXCEL    = dbutils.widgets.get("SITES_EXCEL")

# --- Fixed config ---
SOURCE_CATALOG = "automation_d"  # export source is always DEV
BRONZE_SCHEMA  = "bronze"
GOLD_SCHEMA    = "gold"
VOLUME_NAME    = "bronze_volume"

SOURCE_OUTPUT  = f"{SOURCE_CATALOG}.{GOLD_SCHEMA}.air_monitoring_output"
SOURCE_SITES   = f"{SOURCE_CATALOG}.{GOLD_SCHEMA}.air_monitoring_sites"
EXPORT_VOLUME  = f"/Volumes/{SOURCE_CATALOG}/{BRONZE_SCHEMA}/{VOLUME_NAME}/migration_exports"

LOAD_VOLUME    = f"/Volumes/{TARGET_CATALOG}/{BRONZE_SCHEMA}/{VOLUME_NAME}/migration_exports"
TARGET_OUTPUT  = f"{TARGET_CATALOG}.{GOLD_SCHEMA}.air_monitoring_output"
TARGET_SITES   = f"{TARGET_CATALOG}.{GOLD_SCHEMA}.air_monitoring_sites"
TARGET_UPLOADS = f"{TARGET_CATALOG}.{BRONZE_SCHEMA}.air_monitoring_upload_log"

print(f"Export source:  {SOURCE_CATALOG}")
print(f"Export volume:  {EXPORT_VOLUME}")
print(f"Load target:    {TARGET_CATALOG}")
print(f"Load volume:    {LOAD_VOLUME}")
print(f"OUTPUT_EXCEL:   {OUTPUT_EXCEL}  ({'auto-detect' if OUTPUT_EXCEL == 'auto' else 'explicit'})")
print(f"SITES_EXCEL:    {SITES_EXCEL}  ({'auto-detect' if SITES_EXCEL == 'auto' else 'explicit'})")

# COMMAND ----------

# DBTITLE 1,Cell 2: EXPORT — automation_d → Excel (run in DEV)
# ============================================================
# CELL 2 — EXPORT (run in DEV only)
# Reads automation_d tables and saves as Excel to DEV volume.
# UC volumes don't support random writes (xlsx is a zip) --
# we write to /tmp/ first, then copy to the volume.
# After running: copy the printed file names into Cell 1.
# ============================================================
%pip install openpyxl --quiet

import pandas as pd
import shutil
import os
from datetime import datetime
import warnings
warnings.filterwarnings("ignore")

ts = datetime.now().strftime("%Y%m%d_%H%M")

# Ensure volume folder exists
dbutils.fs.mkdirs(EXPORT_VOLUME)

# --- output_table ---
df_output = spark.table(SOURCE_OUTPUT).toPandas()
# Convert timestamps to string so Excel handles them cleanly
for col in df_output.select_dtypes(include=["datetime64[ns]", "datetime64[ns, UTC]"]).columns:
    df_output[col] = df_output[col].astype(str).replace("NaT", "")

output_tmp  = f"/tmp/output_table_{ts}.xlsx"
output_dest = f"{EXPORT_VOLUME}/output_table_{ts}.xlsx"
df_output.to_excel(output_tmp, index=False)
shutil.copy(output_tmp, output_dest)
print(f"[output_table] {len(df_output):,} rows  ->  {output_dest}")

# --- sites ---
df_sites = spark.table(SOURCE_SITES).toPandas()
sites_tmp  = f"/tmp/sites_{ts}.xlsx"
sites_dest = f"{EXPORT_VOLUME}/sites_{ts}.xlsx"
df_sites.to_excel(sites_tmp, index=False)
shutil.copy(sites_tmp, sites_dest)
print(f"[sites]        {len(df_sites):,} rows  ->  {sites_dest}")

# Cleanup tmp
os.remove(output_tmp)
os.remove(sites_tmp)

print()
print("=" * 65)
print("Update Cell 1 with these file names:")
print(f"  OUTPUT_EXCEL = 'output_table_{ts}.xlsx'")
print(f"  SITES_EXCEL  = 'sites_{ts}.xlsx'")
print()
print("Download both files from Databricks UI:")
print(f"  Catalog > automation_d > bronze > Volumes > bronze_volume > migration_exports")
print()
print("Then upload to ACC volume:")
print(f"  /Volumes/automation_a/bronze/bronze_volume/migration_exports/")
print("And PRD volume:")
print(f"  /Volumes/automation_p/bronze/bronze_volume/migration_exports/")

# COMMAND ----------

# DBTITLE 1,Cell 3: LOAD — Excel → tables (run in ACC or PRD)
# ============================================================
# CELL 3 — SMART LOAD (run in ACC or PRD workspace)
#
# output_table : APPEND only rows whose row_id is NOT already
#                in the target (safe for concurrent app usage).
# sites        : MERGE on site_code — update existing + insert new.
# upload_log   : only CREATE if the table doesn’t exist yet.
#
# Prerequisites:
#   1. Excel files uploaded to TARGET volume (LOAD_VOLUME)
#   2. Cell 1 run (TARGET_CATALOG set, or passed via job params)
# ============================================================
%pip install openpyxl --quiet

import pandas as pd
import os
from pyspark.sql.types import (
    StructType, StructField, StringType, TimestampType, IntegerType
)
import warnings
warnings.filterwarnings("ignore")

# --- Auto-detect latest Excel files if OUTPUT_EXCEL = 'auto' ---
def _latest_file(volume_path, prefix):
    """Return the most-recent file in volume_path starting with prefix."""
    try:
        files = [f for f in os.listdir(volume_path)
                 if f.startswith(prefix) and f.endswith(".xlsx")]
        files.sort(reverse=True)
        return files[0] if files else None
    except Exception:
        return None

_out_file   = OUTPUT_EXCEL if OUTPUT_EXCEL != "auto" else _latest_file(LOAD_VOLUME, "output_table")
_sites_file = SITES_EXCEL  if SITES_EXCEL  != "auto" else _latest_file(LOAD_VOLUME, "sites")

assert _out_file,   f"No output_table*.xlsx found in {LOAD_VOLUME}. Upload the file first."
assert _sites_file, f"No sites*.xlsx found in {LOAD_VOLUME}. Upload the file first."

print(f"Using output file : {_out_file}")
print(f"Using sites file  : {_sites_file}")
print()

# ---------------------------------------------------------------
# output_table: APPEND new rows only (row_id dedup)
# Safe for concurrent app usage: rows uploaded via new app are
# untouched. Only rows from automation_d not yet in target are added.
# ---------------------------------------------------------------
df_out_pd = pd.read_excel(f"{LOAD_VOLUME}/{_out_file}")
for ts_col in ["upload_date", "status_updated_at"]:
    if ts_col in df_out_pd.columns:
        df_out_pd[ts_col] = pd.to_datetime(df_out_pd[ts_col], errors="coerce")
if "Flag_High_Concentration" in df_out_pd.columns:
    df_out_pd["Flag_High_Concentration"] = df_out_pd["Flag_High_Concentration"].map(
        {True: True, False: False, "True": True, "False": False, 1: True, 0: False}
    )
df_out_pd = df_out_pd.where(pd.notnull(df_out_pd), None)
spk_excel = spark.createDataFrame(df_out_pd)
n_excel   = spk_excel.count()

try:
    existing_ids = spark.table(TARGET_OUTPUT).select("row_id")
    spk_new      = spk_excel.join(existing_ids, "row_id", "left_anti")
    n_new  = spk_new.count()
    n_skip = n_excel - n_new
except Exception:
    # Target table does not exist yet -> insert all
    spk_new = spk_excel
    n_new   = n_excel
    n_skip  = 0

if n_new == 0:
    print(f"[output_table] All {n_excel:,} rows already present. Nothing to add.")
else:
    spk_new.write.mode("append").option("mergeSchema", "true").saveAsTable(TARGET_OUTPUT)
    print(f"[output_table] APPEND: {n_new:,} new rows  ->  {TARGET_OUTPUT}")
    print(f"               Skipped (already existed): {n_skip:,} rows")

# ---------------------------------------------------------------
# sites: MERGE on site_code
# Updates existing sites (address/allowed_users may have changed)
# and inserts new ones. Never deletes.
# ---------------------------------------------------------------
df_sites_pd = pd.read_excel(f"{LOAD_VOLUME}/{_sites_file}")
df_sites_pd = df_sites_pd.where(pd.notnull(df_sites_pd), None)
spk_sites   = spark.createDataFrame(df_sites_pd)
spk_sites.createOrReplaceTempView("_migration_sites")

try:
    spark.sql(f"""
        MERGE INTO {TARGET_SITES} AS tgt
        USING _migration_sites AS src
        ON tgt.site_code = src.site_code
        WHEN MATCHED THEN
            UPDATE SET
                tgt.site_name    = src.site_name,
                tgt.address      = src.address,
                tgt.allowed_users = src.allowed_users
        WHEN NOT MATCHED THEN
            INSERT (site_name, site_code, address, allowed_users)
            VALUES (src.site_name, src.site_code, src.address, src.allowed_users)
    """)
    print(f"[sites]        MERGE on site_code  ->  {TARGET_SITES}")
except Exception:
    # Table doesn't exist yet -> create from scratch
    spk_sites.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(TARGET_SITES)
    print(f"[sites]        CREATED: {spk_sites.count():,} rows  ->  {TARGET_SITES}")

# ---------------------------------------------------------------
# upload_log: only create empty table if it doesn't exist yet.
# All future rows are written by the new Streamlit app.
# ---------------------------------------------------------------
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
    print(f"[upload_log]   Already exists ({n_log:,} rows). Not touched.")
except Exception:
    spark.createDataFrame([], upload_log_schema).write.mode("overwrite") \
        .option("overwriteSchema", "true").saveAsTable(TARGET_UPLOADS)
    print(f"[upload_log]   CREATED empty  ->  {TARGET_UPLOADS}")

print()
print("SMART LOAD COMPLETE")
print(f"Target catalog: {TARGET_CATALOG}")

# COMMAND ----------

# DBTITLE 1,TEMP: DEV dry-run override (delete after test)
# TEMP: Override to automation_d for dry-run test.
# automation_d volume already has the exported Excel files.
# Expected: Cell 3 should say 'All X rows already present' for output_table.
TARGET_CATALOG = "automation_d"
LOAD_VOLUME    = f"/Volumes/{TARGET_CATALOG}/bronze/bronze_volume/migration_exports"
TARGET_OUTPUT  = f"{TARGET_CATALOG}.gold.air_monitoring_output"
TARGET_SITES   = f"{TARGET_CATALOG}.gold.air_monitoring_sites"
TARGET_UPLOADS = f"{TARGET_CATALOG}.bronze.air_monitoring_upload_log"
print(f"DRY-RUN: target overridden to {TARGET_CATALOG}")
print(f"Load volume: {LOAD_VOLUME}")
