# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# DBTITLE 1,Header
# MAGIC %md
# MAGIC # Data Migration: V1 Pipeline → `automation_{d|a|p}` Medallion
# MAGIC
# MAGIC Migrates V1 pipeline tables to the new CI/CD app's Medallion schema.
# MAGIC
# MAGIC
# MAGIC ## Source → Target Tables
# MAGIC
# MAGIC | Source (V1 Pipeline) | Target (New App) | Notes |
# MAGIC |---|---|---|
# MAGIC | `general_{d,a,p}.air_monitoring.output_table` | `automation_*.gold.air_monitoring_output` | 26 → 30 columns (row_id + 3 metadata added) |
# MAGIC | `general_{d,a,p}.Air_Monitoring.sites` | `automation_*.gold.air_monitoring_sites` | V1 7-column → new 4-column schema |
# MAGIC | (none) | `automation_*.bronze.air_monitoring_upload_log` | Not in V1 → empty table created |
# MAGIC
# MAGIC ## Schema Differences
# MAGIC
# MAGIC **output_table** — Columns missing in V1 (added during migration):
# MAGIC - `row_id` → UUID generated per row
# MAGIC - `uploaded_by` → fixed value `'v1_migration'`
# MAGIC - `upload_batch_id` → fixed value `'v1_migration'`
# MAGIC - `modified_by` → NULL
# MAGIC
# MAGIC **sites** — V1 → New mapping:
# MAGIC - `site` → `site_name`
# MAGIC - `code` → `site_code`
# MAGIC - `address_please_fill_in` → `address`
# MAGIC - `people_with_access_to_folder_and_data_1/2` → `allowed_users` (email extracted, joined with `/`)
# MAGIC
# MAGIC ## Modes
# MAGIC
# MAGIC | MODE | What it does |
# MAGIC |---|---|
# MAGIC | `"count_only"` | Show counts only — no writes |
# MAGIC | `"export"` | Save NEW rows as Parquet to volume |
# MAGIC | `"direct"` | Write NEW rows directly to TARGET_CATALOG tables |
# MAGIC | `"load_from_parquet"` | Load volume Parquet into tables (run in ACC/PRD) |
# MAGIC
# MAGIC > **PDF note:** `PDF_URL` columns reference `/Volumes/general_{d,a,p}/air_monitoring/...` paths.  
# MAGIC > Physical PDF files must be copied to the new volume separately.

# COMMAND ----------

# DBTITLE 1,Cell 1: Config
# ============================================================
# CELL 1 — Config
# Only this cell needs to change per environment.
# ============================================================

# --------------- SOURCE (V1 pipeline tables) ---------------
# DEV   : general_d
# ACC   : general_a
# PRD   : general_p
SOURCE_CATALOG = "general_d"  # <-- CHANGE: general_a or general_p

# NOTE: sites schema is capitalized (Air_Monitoring), output schema is lowercase (air_monitoring)
SOURCE_OUTPUT   = f"{SOURCE_CATALOG}.air_monitoring.output_table"     # V1 - 26 columns
SOURCE_SITES_V1 = f"{SOURCE_CATALOG}.Air_Monitoring.sites"           # V1 - 7 columns
SOURCE_SITES_V2 = f"general_d.air_monitoring_v2.sites"               # 4 columns (DEV only)

# --------------- TARGET ---------------
# DEV   : automation_d
# ACC   : automation_a
# PRD   : automation_p
TARGET_CATALOG = "automation_d"  # <-- CHANGE: automation_a or automation_p
BRONZE_SCHEMA  = "bronze"
GOLD_SCHEMA    = "gold"
VOLUME_NAME    = "bronze_volume"

TARGET_OUTPUT   = f"{TARGET_CATALOG}.{GOLD_SCHEMA}.air_monitoring_output"
TARGET_SITES    = f"{TARGET_CATALOG}.{GOLD_SCHEMA}.air_monitoring_sites"
TARGET_UPLOADS  = f"{TARGET_CATALOG}.{BRONZE_SCHEMA}.air_monitoring_upload_log"

# Sites source: always "v1" for ACC/PRD
SITES_SOURCE = "v1"  # "v1" or "v2" (v2 only available in DEV)

# --------------- Sync Grain ---------------
# V1 table has no row_id. New row detection uses MD5 fingerprint
# of these columns. Do not change.
SYNC_GRAIN = [
    "Code", "Document_name", "Sample_no",
    "Pump_Location", "Sample_Date", "Volume", "Concentration_result"
]

# --------------- Migration Mode ---------------
# "count_only"       -> show source/target counts + how many rows are NEW (no writes)
# "export"           -> save NEW rows only as Parquet to volume
# "direct"           -> write NEW rows directly to TARGET_CATALOG tables
# "load_from_parquet"-> load volume Parquet into target tables (run in ACC/PRD)
MODE = "direct"  # <-- count_only | export | direct | load_from_parquet

# --------------- Sites refresh ---------------
# True  -> reload sites table (use on first migration or when sites changed)
# False -> skip sites table (output sync only)
REFRESH_SITES = False  # <-- first migration: True | routine sync: False

# --------------- Volume paths ---------------
# Both paths are derived from TARGET_CATALOG automatically.
# DEV -> automation_d, ACC -> automation_a, PRD -> automation_p.
# Export and load use the SAME volume -- no manual file transfer needed.
EXPORT_VOLUME = f"/Volumes/{TARGET_CATALOG}/{BRONZE_SCHEMA}/{VOLUME_NAME}/migration_exports"
LOAD_VOLUME   = EXPORT_VOLUME

# load_from_parquet mode: copy folder names printed by Cell 4 after export
OUTPUT_PARQUET_FOLDER  = "output_table_YYYYMMDD_HHMM"   # <-- fill in after export
SITES_PARQUET_FOLDER   = "sites_YYYYMMDD_HHMM"           # <-- fill in after export

print(f"Source:         {SOURCE_CATALOG}.air_monitoring.output_table")
print(f"Target:         {TARGET_CATALOG}")
print(f"Sites source:   {SITES_SOURCE} | REFRESH_SITES={REFRESH_SITES}")
print(f"Mode:           {MODE}")
print(f"Sync grain:     {SYNC_GRAIN}")
print(f"Export volume:  {EXPORT_VOLUME}")

# COMMAND ----------

# DBTITLE 1,Cell 2: Transformation + Fingerprint Functions
# ============================================================
# CELL 2 — Transformation + Fingerprint functions
# Schema conversion from V1 to new app format.
# Do not modify this cell.
# ============================================================

import re
import uuid
from pyspark.sql import functions as F
from pyspark.sql.types import StringType

# --- UUID UDF (row_id generation) ---
uuid_udf = F.udf(lambda: str(uuid.uuid4()), StringType())


def add_fingerprint(df, grain_cols):
    """
    Generates an MD5 fingerprint from SYNC_GRAIN columns.
    Used to detect whether a row from the old table already exists
    in the new table. Not dependent on row_id -- consistent every run.
    NULL values are treated as empty string.
    """
    concat_expr = F.concat_ws("||", *[
        F.coalesce(F.trim(F.col(c).cast(StringType())), F.lit(""))
        for c in grain_cols
    ])
    return df.withColumn("_fp", F.md5(concat_expr))


def find_new_rows(df_old, df_new_table, grain_cols):
    """
    Returns rows from df_old that do NOT exist in df_new_table.
    Comparison is done via MD5 fingerprint (not row_id).

    - df_old       : V1 source (transformed, no _fp column yet)
    - df_new_table : Target table (already migrated rows)
    - grain_cols   : SYNC_GRAIN list
    Returns: DataFrame with only new rows (_fp column removed)
    """
    df_old_fp = add_fingerprint(df_old, grain_cols)

    try:
        df_new_fp    = add_fingerprint(df_new_table, grain_cols)
        existing_fps = df_new_fp.select("_fp").distinct()
        df_truly_new = df_old_fp.join(existing_fps, "_fp", "left_anti").drop("_fp")
    except Exception:
        # Target table does not exist yet -- all rows are new
        df_truly_new = df_old_fp.drop("_fp")

    return df_truly_new


def transform_output_v1_to_new(df, batch_label="v1_migration"):
    """
    V1 output_table (26 columns) -> new app schema (30 columns).
    Adds 4 missing columns: row_id, uploaded_by, upload_batch_id, modified_by.
    batch_label: first migration -> 'v1_migration' | sync run -> 'v1_sync_YYYYMMDD'
    """
    return (
        df
        .withColumn("row_id",          uuid_udf())
        .withColumn("uploaded_by",     F.lit(batch_label))
        .withColumn("upload_batch_id", F.lit(batch_label))
        .withColumn("modified_by",     F.lit(None).cast(StringType()))
    )


def _extract_email_udf(val):
    """Extracts email from V1 sites 'Name <email>' or plain 'email' format."""
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() in ('nan', 'none', ''):
        return None
    match = re.search(r'<([^>]+@[^>]+)>', s)
    if match:
        return match.group(1).strip().lower()
    if '@' in s:
        return s.strip().lower()
    return None

extract_email_udf = F.udf(_extract_email_udf, StringType())


def transform_sites_v1_to_new(df_v1):
    """V1 sites (7 columns) -> new app schema (4 columns)."""
    return (
        df_v1
        .withColumn("site_name",  F.col("site"))
        .withColumn("site_code",  F.col("code"))
        .withColumn("address",    F.col("address_please_fill_in"))
        .withColumn("_email1",    extract_email_udf(F.col("people_with_access_to_folder_and_data_1")))
        .withColumn("_email2",    extract_email_udf(F.col("people_with_access_to_folder_and_data_2")))
        .withColumn(
            "allowed_users",
            F.when(
                F.col("_email2").isNotNull() & (F.trim(F.col("_email2")) != ""),
                F.concat(F.col("_email1"), F.lit("/"), F.col("_email2"))
            ).otherwise(F.col("_email1"))
        )
        .select("site_name", "site_code", "address", "allowed_users")
    )


print("Functions loaded.")
print("  add_fingerprint(df, grain_cols)                 : MD5 fingerprint")
print("  find_new_rows(df_old, df_new_table, grain_cols) : detect new rows by fingerprint")
print("  transform_output_v1_to_new(df, batch_label)    : V1 -> new schema")
print("  transform_sites_v1_to_new(df)                  : V1 sites -> new schema")

# COMMAND ----------

# DBTITLE 1,Cell 3: Sync Preview
# ============================================================
# CELL 3 — Sync preview: how many rows are NEW?
# Run before any MODE. Does not write anything.
# ============================================================
from datetime import datetime
batch_label = f"v1_sync_{datetime.now().strftime('%Y%m%d')}"

print("=" * 65)
print("SOURCE TABLE COUNTS")
print("=" * 65)
try:
    df_src = spark.table(SOURCE_OUTPUT)
    n_src = df_src.count()
    print(f"  {SOURCE_OUTPUT}: {n_src:,} rows")
except Exception as e:
    print(f"  {SOURCE_OUTPUT}: ERROR -> {e}")
    n_src = 0
    df_src = None

print()
print("=" * 65)
print(f"TARGET TABLE COUNTS ({TARGET_CATALOG})")
print("=" * 65)
try:
    df_tgt = spark.table(TARGET_OUTPUT)
    n_tgt = df_tgt.count()
    print(f"  {TARGET_OUTPUT}: {n_tgt:,} rows")
except Exception as e:
    print(f"  {TARGET_OUTPUT}: (not yet created or no access)")
    df_tgt = None
    n_tgt = 0

for tbl in [TARGET_SITES, TARGET_UPLOADS]:
    try:
        print(f"  {tbl}: {spark.table(tbl).count():,} rows")
    except Exception:
        print(f"  {tbl}: (not yet created)")

# --- Fingerprint-based new row detection ---
print()
print("=" * 65)
print("SYNC ANALYSIS (fingerprint dedup)")
print("=" * 65)
if df_src is not None:
    df_src_transformed = transform_output_v1_to_new(df_src, batch_label)
    df_new_rows = find_new_rows(df_src_transformed, df_tgt, SYNC_GRAIN)
    n_new   = df_new_rows.count()
    n_exist = n_src - n_new
    print(f"  Old table total rows:      {n_src:,}")
    print(f"  Already in new table:      {n_exist:,}")
    print(f"  NEW rows to sync:          {n_new:,}  <-- only these will be written")
    print()
    if n_new > 0:
        print("  New rows breakdown by row_status:")
        df_new_rows.groupBy("row_status").count().orderBy("count", ascending=False).show()
    else:
        print("  No new rows to sync. Old tool has no new uploads since last run.")
else:
    print("  Could not read source table.")

# V1 sites preview
print()
print("V1 Sites schema preview (3 rows):")
try:
    display(spark.table(SOURCE_SITES_V1).limit(3))
except Exception as e:
    print(f"  {e}")

# COMMAND ----------

# DBTITLE 1,Cell 4: Export to Parquet — NEW rows only
# ============================================================
# CELL 4 — Export: save NEW rows only as Parquet
# Set MODE = "export".
# Existing rows are skipped -- detected via MD5 fingerprint.
# Output: EXPORT_VOLUME/output_table_TIMESTAMP/ + sites_TIMESTAMP/
# ============================================================
if MODE != "export":
    print(f"MODE='{MODE}' -- skipped. Set MODE='export' to run.")
else:
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    batch_label = f"v1_sync_{ts}"

    # --- Read source + transform ---
    df_src = spark.table(SOURCE_OUTPUT)
    df_src_transformed = transform_output_v1_to_new(df_src, batch_label)

    # --- Fingerprint: find NEW rows only ---
    try:
        df_existing = spark.table(TARGET_OUTPUT)
    except Exception:
        df_existing = None  # table does not exist yet -- all rows are new

    df_new_only = find_new_rows(df_src_transformed, df_existing, SYNC_GRAIN)
    n_total = df_src_transformed.count()
    n_new   = df_new_only.count()
    n_skip  = n_total - n_new

    if n_new == 0:
        print(f"No new rows ({n_total:,} rows already in target). Export skipped.")
    else:
        out_path = f"{EXPORT_VOLUME}/output_table_{ts}"
        df_new_only.write.mode("overwrite").parquet(out_path)
        print("=" * 65)
        print("OUTPUT EXPORT COMPLETE")
        print("=" * 65)
        print(f"  Source total:    {n_total:,} rows")
        print(f"  Already exists:  {n_skip:,} rows  (skipped)")
        print(f"  NEW rows:        {n_new:,} rows  (exported)")
        print(f"  Path: {out_path}")
        print()
        print(f"  Update Cell 1:")
        print(f"  OUTPUT_PARQUET_FOLDER = 'output_table_{ts}'")

    # --- Sites (if REFRESH_SITES = True) ---
    if REFRESH_SITES:
        if SITES_SOURCE == "v2":
            df_sites_new = spark.table(SOURCE_SITES_V2)
        else:
            df_sites_v1  = spark.table(SOURCE_SITES_V1)
            df_sites_new = transform_sites_v1_to_new(df_sites_v1)
        sites_path = f"{EXPORT_VOLUME}/sites_{ts}"
        df_sites_new.write.mode("overwrite").parquet(sites_path)
        print(f"\n  Sites ({df_sites_new.count():,} rows) -> {sites_path}")
        print(f"  SITES_PARQUET_FOLDER = 'sites_{ts}'")
        print("\n  Sites allowed_users preview:")
        display(df_sites_new.limit(10))
    else:
        print("\n  REFRESH_SITES=False -- sites skipped.")

    print("\nUpload log: not in V1 -- empty table will be created in Cell 5 (first run only).")

# COMMAND ----------

# DBTITLE 1,Cell 5: Load from Parquet (ACC/PRD)
# ============================================================
# CELL 5 — Load from Parquet -> write to target tables
# Run in ACC or PRD workspace.
# NOTE: Cell 4 (export) already saved only NEW rows.
#       This cell will not re-insert the same rows (row_id dedup).
# Steps:
#   1. Cell 1: update TARGET_CATALOG + *_PARQUET_FOLDER
#   2. Set MODE = "load_from_parquet"
#   3. Run this cell
# ============================================================
if MODE != "load_from_parquet":
    print(f"MODE='{MODE}' -- skipped. Set MODE='load_from_parquet' to run.")
else:
    from pyspark.sql.types import (
        StructType, StructField, StringType, TimestampType, IntegerType
    )

    print(f"Volume: {LOAD_VOLUME}")
    print()

    # --- Output Table ---
    # Cell 4 (export) already used fingerprint to save only NEW rows.
    # row_id dedup here is a safety layer against double-loads.
    if OUTPUT_PARQUET_FOLDER != "output_table_YYYYMMDD_HHMM":
        out_path = f"{LOAD_VOLUME}/{OUTPUT_PARQUET_FOLDER}"
        df_parquet = spark.read.parquet(out_path)
        n_parquet  = df_parquet.count()

        # Safety: skip rows whose row_id is already in target
        try:
            existing_ids = spark.table(TARGET_OUTPUT).select("row_id")
            df_to_write  = df_parquet.join(existing_ids, "row_id", "left_anti")
            n_skip = n_parquet - df_to_write.count()
        except Exception:
            df_to_write = df_parquet
            n_skip = 0

        if df_to_write.count() == 0:
            print(f"[output]  All rows already present ({n_parquet:,}). Skipped.")
        else:
            df_to_write.write.mode("append").option("mergeSchema", "true").saveAsTable(TARGET_OUTPUT)
            print(f"[output]  APPEND: {df_to_write.count():,} new rows -> {TARGET_OUTPUT}")
            if n_skip > 0:
                print(f"          ({n_skip:,} rows skipped by row_id safety check)")
    else:
        print("[output]  OUTPUT_PARQUET_FOLDER not updated -- skipped.")

    # --- Sites (if REFRESH_SITES = True) ---
    if REFRESH_SITES and SITES_PARQUET_FOLDER != "sites_YYYYMMDD_HHMM":
        sites_path = f"{LOAD_VOLUME}/{SITES_PARQUET_FOLDER}"
        df_sites   = spark.read.parquet(sites_path)
        df_sites.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(TARGET_SITES)
        print(f"[sites]   OVERWRITE: {df_sites.count():,} rows -> {TARGET_SITES}")
    else:
        print(f"[sites]   Skipped (REFRESH_SITES={REFRESH_SITES}).")

    # --- Upload Log: only create if it does not exist yet ---
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
        existing_log = spark.table(TARGET_UPLOADS).count()
        print(f"[upload_log] Already exists ({existing_log:,} rows). Not touched.")
    except Exception:
        spark.createDataFrame([], upload_log_schema).write.mode("overwrite") \
            .option("overwriteSchema", "true").saveAsTable(TARGET_UPLOADS)
        print(f"[upload_log] CREATED (empty): {TARGET_UPLOADS}")

    print()
    print("LOAD COMPLETE")

# COMMAND ----------

# DBTITLE 1,Cell 6: Direct Write — NEW rows only
# ============================================================
# CELL 6 — Direct write: NEW rows only (same metastore)
# Use when automation_a/p is accessible from this workspace.
# Set MODE = "direct".
# Fingerprint-based detection -- safe even without row_id in source.
# ============================================================
if MODE != "direct":
    print(f"MODE='{MODE}' -- skipped. Set MODE='direct' to run.")
else:
    from datetime import datetime
    from pyspark.sql.types import StructType, StructField, StringType, TimestampType, IntegerType
    batch_label = f"v1_sync_{datetime.now().strftime('%Y%m%d_%H%M')}"

    # --- Output Table: find NEW rows via fingerprint ---
    df_src       = spark.table(SOURCE_OUTPUT)
    df_src_tr    = transform_output_v1_to_new(df_src, batch_label)
    try:
        df_existing = spark.table(TARGET_OUTPUT)
    except Exception:
        df_existing = None

    df_new_only = find_new_rows(df_src_tr, df_existing, SYNC_GRAIN)
    n_total = df_src_tr.count()
    n_new   = df_new_only.count()
    n_skip  = n_total - n_new

    if n_new == 0:
        print(f"[output]  No new rows. ({n_total:,} rows already in target.) Skipped.")
    else:
        df_new_only.write.mode("append").option("mergeSchema", "true").saveAsTable(TARGET_OUTPUT)
        print(f"[output]  APPEND: {n_new:,} new rows -> {TARGET_OUTPUT}")
        print(f"          Skipped (already existed): {n_skip:,} rows")
        print(f"          Batch label: {batch_label}")

    # --- Sites (if REFRESH_SITES = True) ---
    if REFRESH_SITES:
        if SITES_SOURCE == "v2":
            df_sites_new = spark.table(SOURCE_SITES_V2)
        else:
            df_sites_v1  = spark.table(SOURCE_SITES_V1)
            df_sites_new = transform_sites_v1_to_new(df_sites_v1)
        df_sites_new.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(TARGET_SITES)
        print(f"[sites]   OVERWRITE: {df_sites_new.count():,} rows -> {TARGET_SITES}")
        print("\n  Sites allowed_users preview:")
        display(df_sites_new.select("site_code", "site_name", "allowed_users").limit(10))
    else:
        print(f"[sites]   Skipped (REFRESH_SITES=False).")

    # --- Upload Log: only create if it does not exist yet ---
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
        existing_log_n = spark.table(TARGET_UPLOADS).count()
        print(f"[upload_log] Already exists ({existing_log_n:,} rows). Not touched.")
    except Exception:
        spark.createDataFrame([], upload_log_schema).write.mode("overwrite") \
            .option("overwriteSchema", "true").saveAsTable(TARGET_UPLOADS)
        print(f"[upload_log] CREATED (empty): {TARGET_UPLOADS}")

    print()
    print("DIRECT SYNC COMPLETE")

# COMMAND ----------

# DBTITLE 1,Cell 6b: Output-Only Append (DEV sync)
# ============================================================
# CELL 6b — Output-only APPEND (new rows only)
# Does not touch sites or upload_log.
# Use instead of Cell 6 when:
#   - REFRESH_SITES = False
#   - You only want to sync output rows
# ============================================================
from datetime import datetime
batch_label = f"v1_sync_{datetime.now().strftime('%Y%m%d_%H%M')}"

df_src    = spark.table(SOURCE_OUTPUT)
df_src_tr = transform_output_v1_to_new(df_src, batch_label)

try:
    df_existing = spark.table(TARGET_OUTPUT)
except Exception:
    df_existing = None

df_new_only = find_new_rows(df_src_tr, df_existing, SYNC_GRAIN)
n_new = df_new_only.count()

if n_new == 0:
    print(f"No new rows. Target is already up to date: {TARGET_OUTPUT}")
else:
    df_new_only.write.mode("append").option("mergeSchema", "true").saveAsTable(TARGET_OUTPUT)
    print(f"DONE: {n_new:,} new rows appended -> {TARGET_OUTPUT}")
    print(f"Batch label: {batch_label}")

# COMMAND ----------

# DBTITLE 1,Cell 7: Verification
# ============================================================
# CELL 7 — Post-migration verification
# Run after any migration step.
# ============================================================
if MODE == "count_only":
    print("count_only mode -- no verification needed.")
else:
    print("=" * 60)
    print(f"POST-MIGRATION VERIFICATION ({TARGET_CATALOG})")
    print("=" * 60)

    src_n = spark.table(SOURCE_OUTPUT).count()
    try:
        tgt_n = spark.table(TARGET_OUTPUT).count()
        ok = "✅" if tgt_n >= src_n else "⚠️ MISSING ROWS"
        print(f"  output_table  src={src_n:>6,}  tgt={tgt_n:>6,}  {ok}")
    except Exception as e:
        print(f"  output_table  src={src_n:>6,}  tgt=ERROR: {e}")

    sites_src = SOURCE_SITES_V2 if SITES_SOURCE == "v2" else SOURCE_SITES_V1
    s_n = spark.table(sites_src).count()
    try:
        st_n = spark.table(TARGET_SITES).count()
        ok = "✅" if st_n >= s_n else "⚠️ MISSING ROWS"
        print(f"  sites         src={s_n:>6,}  tgt={st_n:>6,}  {ok}")
    except Exception as e:
        print(f"  sites         src={s_n:>6,}  tgt=ERROR: {e}")

    try:
        ul_n = spark.table(TARGET_UPLOADS).count()
        print(f"  upload_log    src=     -   tgt={ul_n:>6,}  ✅ (not in V1, managed by new app)")
    except Exception as e:
        print(f"  upload_log    tgt=ERROR: {e}")

    # Sites allowed_users verification
    print()
    print("Sites allowed_users sample (verify email extraction):")
    try:
        display(spark.table(TARGET_SITES).select("site_code", "site_name", "allowed_users"))
    except Exception as e:
        print(f"  {e}")

    print()
    print("row_status breakdown in target output_table:")
    try:
        spark.table(TARGET_OUTPUT).groupBy("row_status").count().orderBy("count", ascending=False).show()
    except Exception as e:
        print(f"  {e}")

    print()
    print("PDF_URL REMINDER:")
    print(f"  PDF_URL values reference /Volumes/{SOURCE_CATALOG}/air_monitoring/... paths.")
    print(f"  Physical PDF files must be copied to:")
    print(f"  /Volumes/{TARGET_CATALOG}/bronze/bronze_volume/uploaded_reports/")
