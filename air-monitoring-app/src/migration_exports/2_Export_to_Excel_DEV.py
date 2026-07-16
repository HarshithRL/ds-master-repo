# Databricks notebook source
# DBTITLE 1,Header
# MAGIC %md
# MAGIC # Step 1 — Export to Excel (DEV only)
# MAGIC
# MAGIC Reads `general_d` V1 pipeline tables and exports them as `.xlsx` files to the DEV volume.
# MAGIC
# MAGIC **After running:**
# MAGIC 1. Download the two `.xlsx` files from the volume path printed below
# MAGIC 2. Upload them to the ACC or PRD volume: `/Volumes/automation_a/bronze/bronze_volume/migration_exports/`
# MAGIC 3. Run notebook `2_Load_from_Excel_ACC_PRD` in the ACC/PRD workspace
# MAGIC
# MAGIC | Source | Target Excel |
# MAGIC |---|---|
# MAGIC | `general_d.air_monitoring.output_table` | `output_table_TIMESTAMP.xlsx` |
# MAGIC | `general_d.Air_Monitoring.sites` | `sites_TIMESTAMP.xlsx` |

# COMMAND ----------

# DBTITLE 1,Cell 1 — Config
# ============================================================
# CELL 1 — Config (DEV only, do not change)
# ============================================================
from datetime import datetime
import warnings
warnings.filterwarnings("ignore")

# Source: general_d
# output_table  ← V1 pipeline (air_monitoring schema)
# sites         ← V2 app    (air_monitoring_v2 schema — correct: site_code, site_name, address, allowed_users)
SOURCE_CATALOG  = "general_d"
SOURCE_OUTPUT   = f"{SOURCE_CATALOG}.air_monitoring.output_table"
SOURCE_SITES    = f"{SOURCE_CATALOG}.air_monitoring_v2.sites"

# Export destination: DEV volume
EXPORT_CATALOG  = "automation_d"
EXPORT_VOLUME   = f"/Volumes/{EXPORT_CATALOG}/bronze/bronze_volume/migration_exports"

# Export sites too? True = yes (do on first migration or when sites changed)
EXPORT_SITES    = True  # <-- set False to skip sites

print(f"Source output : {SOURCE_OUTPUT}")
print(f"Source sites  : {SOURCE_SITES}")
print(f"Export volume : {EXPORT_VOLUME}")
print(f"Export sites  : {EXPORT_SITES}")

# COMMAND ----------

# DBTITLE 1,Cell 2 — Export to Excel
# ============================================================
# CELL 2 — Export
# Reads V1 tables and saves as .xlsx to the DEV volume.
# UC Volumes don't support random writes (xlsx = zip) so we
# write to /tmp/ first, then copy to the volume.
# ============================================================
%pip install openpyxl --quiet

import pandas as pd
import shutil
import os
import re
from pyspark.sql import functions as F
from pyspark.sql.types import StringType

ts = datetime.now().strftime("%Y%m%d_%H%M")

# Ensure export folder exists
dbutils.fs.mkdirs(EXPORT_VOLUME)

# ---- output_table ----------------------------------------
df_out = spark.table(SOURCE_OUTPUT).toPandas()
# Timestamps to string so Excel handles them cleanly
for col in df_out.select_dtypes(include=["datetime64[ns]", "datetime64[ns, UTC]"]).columns:
    df_out[col] = df_out[col].astype(str).replace("NaT", "")

out_tmp  = f"/tmp/output_table_{ts}.xlsx"
out_dest = f"{EXPORT_VOLUME}/output_table_{ts}.xlsx"
df_out.to_excel(out_tmp, index=False, engine="openpyxl")
shutil.copy(out_tmp, out_dest)
os.remove(out_tmp)
print(f"[output_table] {len(df_out):,} rows  ->  {out_dest}")

# ---- sites -----------------------------------------------
if EXPORT_SITES:
    df_sites = spark.table(SOURCE_SITES).toPandas()
    sites_tmp  = f"/tmp/sites_{ts}.xlsx"
    sites_dest = f"{EXPORT_VOLUME}/sites_{ts}.xlsx"
    df_sites.to_excel(sites_tmp, index=False, engine="openpyxl")
    shutil.copy(sites_tmp, sites_dest)
    os.remove(sites_tmp)
    print(f"[sites]        {len(df_sites):,} rows  ->  {sites_dest}")
else:
    print("[sites]        EXPORT_SITES=False — skipped.")

print()
print("=" * 65)
print(f"Files saved to: {EXPORT_VOLUME}")
print()
print("NEXT STEPS:")
print(f"  1. Download from volume:  {EXPORT_VOLUME}")
print(f"     Files: output_table_{ts}.xlsx" + (f", sites_{ts}.xlsx" if EXPORT_SITES else ""))
print(f"  2. Upload to ACC/PRD volume:")
print(f"     /Volumes/automation_a/bronze/bronze_volume/migration_exports/  (ACC)")
print(f"     /Volumes/automation_p/bronze/bronze_volume/migration_exports/  (PRD)")
print(f"  3. Run notebook 2_Load_from_Excel_ACC_PRD in ACC/PRD workspace.")
print(f"     File names to enter in Cell 1:")
print(f"       OUTPUT_EXCEL = 'output_table_{ts}.xlsx'")
if EXPORT_SITES:
    print(f"       SITES_EXCEL  = 'sites_{ts}.xlsx'")

# COMMAND ----------


