# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# DBTITLE 1,01 - Bronze Ingestion
# MAGIC %md
# MAGIC # 01 - Bronze Ingestion
# MAGIC
# MAGIC **Purpose:** Reads Excel/CSV files from the latest run subfolder and loads them into `automation_d.silver` as bronze tables.
# MAGIC
# MAGIC **Requires:** `00_sharepoint_to_volume` must have run successfully.
# MAGIC
# MAGIC **Parameter:** `run_folder` - path to the timestamped subfolder (auto-detected if not provided).

# COMMAND ----------

# DBTITLE 1,Install Dependencies
# MAGIC %pip install openpyxl --quiet

# COMMAND ----------

# DBTITLE 1,Configuration
import os, re, json
from datetime import datetime

# ---------------------------------------------------------------------------
# Target schema
# ---------------------------------------------------------------------------
dbutils.widgets.text("catalog", "automation_d", "Catalog")
CATALOG = dbutils.widgets.get("catalog")
TARGET_SCHEMA = f"{CATALOG}.silver"

# ---------------------------------------------------------------------------
# Source: use widget or auto-detect latest subfolder
# ---------------------------------------------------------------------------
VOLUME_BASE = f"/Volumes/{CATALOG}/bronze/bronze_volume/Copilot_Dashboard_Data"

dbutils.widgets.text("run_folder", "", "Run folder path (leave blank for latest)")
dbutils.widgets.dropdown("load_mode", "overwrite", ["overwrite", "incremental"])

run_folder = dbutils.widgets.get("run_folder").strip()
load_mode = dbutils.widgets.get("load_mode")

if not run_folder:
    # Auto-detect: pick the most recent timestamped subfolder
    entries = dbutils.fs.ls(VOLUME_BASE)
    folders = sorted([e for e in entries if e.isDir()], key=lambda e: e.name, reverse=True)
    if not folders:
        raise FileNotFoundError(f"No run subfolders found in {VOLUME_BASE}")
    run_folder = folders[0].path.replace("dbfs:", "")
    print(f"Auto-detected latest run folder: {run_folder}")
else:
    print(f"Using specified run folder: {run_folder}")

print(f"Target schema: {TARGET_SCHEMA}")
print(f"Load mode: {load_mode}")

# ---------------------------------------------------------------------------
# FILE -> TABLE mapping
# ---------------------------------------------------------------------------
FILE_TO_TABLE_MAP = {
    # Canonical names (both xlsx and csv variants)
    "agents_inventory.xlsx":                    "agents_inventory",
    "agents_inventory.csv":                     "agents_inventory",
    "agent_level_credit_consumption.xlsx":       "agent_level_credit_consumption",
    "agent_level_credit_consumption.csv":        "agent_level_credit_consumption",
    "environment_level_credit_consumption.xlsx": "environment_level_credit_consumption",
    "environment_level_credit_consumption.csv":  "environment_level_credit_consumption",
    "user_level_credit_consumption.xlsx":        "user_level_credit_consumption",
    "user_level_credit_consumption.csv":         "user_level_credit_consumption",
    "copilot_studio_kit_all_records.xlsx":       "copilot_studio_kit_all_records",
    "copilot_studio_kit_all_records.csv":        "copilot_studio_kit_all_records",
    "bot_usage_pp_coe_kit.xlsx":                 "bot_usage_pp_coe_kit",
    "bot_usage_pp_coe_kit.csv":                  "bot_usage_pp_coe_kit",
    "microsoft_purview_audit_log.csv":           "microsoft_purview_audit_log",
    "microsoft_purview_audit_log.xlsx":          "microsoft_purview_audit_log",
}

# Business-key dedup columns
BUSINESS_KEYS = {
    "microsoft_purview_audit_log": "RecordId",
    "agents_inventory": "Item_ID",
    "bot_usage_pp_coe_kit": "Do_Not_Modify_PVA_Bot_Usage",
}

# COMMAND ----------

# DBTITLE 1,Load Helpers
import openpyxl
from pyspark.sql import functions as F
from pyspark.sql.types import StructType, StructField, StringType


def sanitize_table_name(file_name):
    name = re.sub(r'\.(xlsx|xls|csv)\Z', '', file_name, flags=re.IGNORECASE)
    name = re.sub(r'[^a-zA-Z0-9]', '_', name)
    name = re.sub(r'_+', '_', name).strip('_').lower()
    return name


def sanitize_columns(df):
    """Rename columns to Delta-safe names: replace spaces/special chars with underscores."""
    for col in df.columns:
        safe = re.sub(r'[^a-zA-Z0-9_]', '_', col)
        safe = re.sub(r'_+', '_', safe).strip('_')
        if safe != col:
            df = df.withColumnRenamed(col, safe)
    return df


def read_excel_as_spark_df(file_path):
    """Read .xlsx via openpyxl into a Spark DataFrame (all StringType)."""
    wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
    ws = wb.active
    all_rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if not all_rows:
        raise ValueError(f"Excel file is empty: {file_path}")
    raw_headers = all_rows[0]
    headers = [
        str(h).strip().replace(' ', '_').replace('/', '_').replace('(', '').replace(')', '')
        if h else f"_col_{i}"
        for i, h in enumerate(raw_headers)
    ]
    # Deduplicate headers
    seen = {}
    unique = []
    for h in headers:
        if h in seen:
            seen[h] += 1
            unique.append(f"{h}_{seen[h]}")
        else:
            seen[h] = 1
            unique.append(h)
    schema = StructType([StructField(h, StringType(), True) for h in unique])
    data_rows = [[str(v) if v is not None else None for v in row]
                 for row in all_rows[1:] if any(v is not None for v in row)]
    return spark.createDataFrame(data_rows, schema=schema)


def add_metadata(df, file_name):
    hash_expr = F.md5(F.concat_ws("|", *[F.coalesce(F.col(f"`{c}`").cast("string"), F.lit("NULL")) for c in df.columns]))
    return df.withColumns({
        "_source_file": F.lit(file_name),
        "_ingestion_timestamp": F.current_timestamp(),
        "_row_hash": hash_expr,
    })


def write_table(df, full_table_name, table_name):
    """Write with overwrite or incremental (dedup) mode."""
    if load_mode == "overwrite":
        df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(full_table_name)
        print(f"  OVERWRITE | {df.count():,} rows")
    else:
        if not spark.catalog.tableExists(full_table_name):
            df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(full_table_name)
            print(f"  CREATED | {df.count():,} rows")
        else:
            bk = BUSINESS_KEYS.get(table_name)
            dedup_col = bk if bk and bk in df.columns else "_row_hash"
            existing = spark.table(full_table_name).select(dedup_col).distinct()
            new_rows = df.join(existing, on=dedup_col, how="left_anti")
            cnt = new_rows.count()
            if cnt > 0:
                new_rows.write.format("delta").mode("append").saveAsTable(full_table_name)
            print(f"  INCREMENTAL | {cnt:,} new rows appended")

print("Helpers loaded.")

# COMMAND ----------

# DBTITLE 1,Process Files
# ---------------------------------------------------------------------------
# Scan the run folder and ingest each file
# ---------------------------------------------------------------------------
files = dbutils.fs.ls(run_folder)
canonical_files = [f for f in files if not f.isDir() and f.name.lower().endswith(('.xlsx', '.xls', '.csv'))]

print(f"Found {len(canonical_files)} file(s) in {run_folder}")
print("=" * 70)

results = []
skipped = []
for f in canonical_files:
    table_name = FILE_TO_TABLE_MAP.get(f.name)
    if table_name is None:
        # File not in the map — skip it (likely a SharePoint display-name duplicate)
        skipped.append(f.name)
        print(f"SKIP: {f.name} (not a canonical file name, ignoring)")
        continue
    full_table = f"{TARGET_SCHEMA}.{table_name}"
    file_path = f.path.replace("dbfs:", "")
    print(f"Processing: {f.name} -> {full_table}")
    print(f"  Size: {f.size / 1024:.1f} KB")
    try:
        if f.name.lower().endswith('.csv'):
            df = (spark.read.format("csv")
                  .option("header", "true")
                  .option("inferSchema", "false")
                  .option("multiLine", "true")
                  .option("escape", '"')
                  .load(file_path))
        else:
            df = read_excel_as_spark_df(file_path)
        df = sanitize_columns(df)  # Delta-safe column names
        df = add_metadata(df, f.name)
        write_table(df, full_table, table_name)
        results.append((table_name, "OK"))
    except Exception as e:
        print(f"  ERROR: {e}")
        results.append((table_name, f"FAIL: {e}"))

print("=" * 70)
print("\nIngestion summary:")
for tbl, status in results:
    print(f"  {tbl:50s} {status}")

failed = [r for r in results if r[1].startswith("FAIL")]
if failed:
    raise RuntimeError(f"{len(failed)} table(s) failed to load")

if skipped:
    print(f"\nSkipped {len(skipped)} non-canonical file(s): {skipped}")
print(f"\nAll {len(results)} tables loaded to {TARGET_SCHEMA}")
dbutils.notebook.exit(json.dumps({"tables": len(results), "schema": TARGET_SCHEMA}))

# COMMAND ----------

