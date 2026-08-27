"""Air Monitoring V2 — Table Setup & Data Migration from V1 Excel Export.

=== CONTEXT ===

OLD V1 app (SharePoint) exports data as Excel with 23 columns.
NEW V2 app (Databricks) has 30 columns (adds: row_id, row_status,
removal_reason, status_updated_at, uploaded_by, upload_batch_id, modified_by).

This script bridges V1 → V2 with proper transformations.

=== MATCHING STRATEGY ===

Uses LEFT ANTI JOIN (not MERGE) on expanded grain:
  Code + Sample_no + Sample_Date + Volume + Concentration_result + Document_name

Why anti-join instead of MERGE?
  - Delta table has legitimate duplicate grain keys (same row uploaded twice,
    one kept as active, other marked row_status='removed'). MERGE would fail
    with "multiple target rows match one source row".
  - Anti-join simply checks: "does this Excel row exist ANYWHERE in Delta?"
    If yes → skip. If no → INSERT.

=== DATA TRANSFORMATIONS ===

  Excel → Delta:
  - Sample_Date: datetime → 'DD-Mon-YYYY' string (e.g. '19-Feb-2025')
  - Frozen_Docs='x' → row_status='removed', removal_reason='V1 frozen document'
  - No Frozen_Docs → row_status='active'
  - row_id: generated UUID4 for each new row
  - uploaded_by: 'migrated'
  - upload_batch_id: 'excel_migration_YYYYMMDD_HHMMSS'
  - Delete_docs: float NaN → None (STRING column)

=== SCENARIOS ===

  1. FIRST TIME (empty table): Full INSERT of all Excel rows
  2. INCREMENTAL (both apps in use): Anti-join finds only NEW rows, inserts them
  3. RE-RUN (same Excel): 0 rows inserted (idempotent)
  4. UPDATED Excel (fresh export): Only net-new rows added

=== SAFETY GUARANTEES ===

  - Never overwrites existing rows (user edits, removals preserved)
  - Never resurrects removed rows
  - Never creates duplicate row_ids (fresh UUID per insert)
  - Idempotent: same Excel → 0 new rows on re-run

=== USAGE ===

  python setup_tables.py <catalog_name>
  
  python setup_tables.py automation_a   # ACC
  python setup_tables.py automation_p   # PRD
  python setup_tables.py automation_d   # TEST (re-run)

=== EXCEL FILES ===

  /Volumes/{catalog}/bronze/bronze_volume/air_monitoring/migration/
    - Output_Table.xlsx   (V1 full export, 23 columns)
    - sites.xlsx          (site dimension, 4 columns)
"""
import sys
import uuid
from datetime import datetime

import pandas as pd
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import StringType

spark = SparkSession.builder.getOrCreate()

# ============================================================
# Configuration
# ============================================================
CATALOG = sys.argv[1] if len(sys.argv) > 1 else "automation_d"

BRONZE_SCHEMA = "bronze"
SILVER_SCHEMA = "silver"
GOLD_SCHEMA = "gold"
VOLUME_NAME = "bronze_volume"

VOLUME_PATH = f"/Volumes/{CATALOG}/{BRONZE_SCHEMA}/{VOLUME_NAME}"
MIGRATION_PATH = f"{VOLUME_PATH}/air_monitoring/migration"

# Expanded grain for matching (Excel has 0 duplicates on this key)
MATCH_GRAIN = ["Code", "Sample_no", "Sample_Date", "Volume", "Concentration_result", "Document_name"]

# Migration batch identifier
BATCH_ID = f"excel_migration_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

print(f"{'='*70}")
print(f" Air Monitoring V2 — Table Setup & Migration")
print(f"{'='*70}")
print(f"  Catalog:        {CATALOG}")
print(f"  Migration path: {MIGRATION_PATH}")
print(f"  Batch ID:       {BATCH_ID}")
print(f"  Match grain:    {' + '.join(MATCH_GRAIN)}")
print(f"{'='*70}")

# ============================================================
# STEP 1: Create schemas
# ============================================================
print("\n[1/6] Creating schemas...")
for schema in [BRONZE_SCHEMA, SILVER_SCHEMA, GOLD_SCHEMA]:
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{schema}")
    print(f"  ✓ {CATALOG}.{schema}")

# ============================================================
# STEP 2: Create Volume
# ============================================================
print("\n[2/6] Creating volume...")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.{BRONZE_SCHEMA}.{VOLUME_NAME}")
print(f"  ✓ {CATALOG}.{BRONZE_SCHEMA}.{VOLUME_NAME}")

# ============================================================
# STEP 3: Create tables (IF NOT EXISTS)
# ============================================================
print("\n[3/6] Creating tables...")

spark.sql(f"""
    CREATE TABLE IF NOT EXISTS {CATALOG}.{BRONZE_SCHEMA}.air_monitoring_sites (
        site_name STRING,
        site_code STRING,
        address STRING,
        allowed_users STRING
    ) USING delta
    COMMENT 'Sites dimension — RLS via allowed_users (slash-separated emails)'
""")
print(f"  ✓ {CATALOG}.{BRONZE_SCHEMA}.air_monitoring_sites")

spark.sql(f"""
    CREATE TABLE IF NOT EXISTS {CATALOG}.{BRONZE_SCHEMA}.air_monitoring_output (
        row_id STRING,
        Site_name STRING,
        Code STRING,
        Site_Address STRING,
        upload_date TIMESTAMP,
        Document_name STRING,
        Report_number STRING,
        Sample_no STRING,
        Pump_Location STRING,
        Lab_name STRING,
        Project_Name STRING,
        Building STRING,
        Sample_Date STRING,
        Analysis_method STRING,
        Followed_Norm STRING,
        Volume STRING,
        Concentration_result STRING,
        Concentration_unit STRING,
        Concentration_result_in_f_ml STRING,
        Frozen_Docs STRING,
        PDF_URL STRING,
        Flag_EM_Concentration DOUBLE,
        Flag_High_Concentration BOOLEAN,
        Delete_docs STRING,
        row_status STRING,
        removal_reason STRING,
        status_updated_at TIMESTAMP,
        uploaded_by STRING,
        upload_batch_id STRING,
        modified_by STRING
    ) USING delta
    COMMENT 'Main output — one row per air sample measurement'
""")
print(f"  ✓ {CATALOG}.{BRONZE_SCHEMA}.air_monitoring_output")

spark.sql(f"""
    CREATE TABLE IF NOT EXISTS {CATALOG}.{BRONZE_SCHEMA}.air_monitoring_upload_log (
        upload_id STRING,
        batch_id STRING,
        filename STRING,
        site_code STRING,
        site_name STRING,
        uploaded_by STRING,
        upload_time TIMESTAMP,
        num_records INT,
        num_duplicates_found INT,
        num_saved INT,
        status STRING,
        volume_path STRING
    ) USING delta
    COMMENT 'Upload event audit log'
""")
print(f"  ✓ {CATALOG}.{BRONZE_SCHEMA}.air_monitoring_upload_log")

# ============================================================
# STEP 4: Migrate sites (UPSERT on site_code)
# ============================================================
print("\n[4/6] Migrating sites...")

sites_path = f"{MIGRATION_PATH}/sites.xlsx"
try:
    df_sites_pd = pd.read_excel(sites_path)
    df_sites = spark.createDataFrame(df_sites_pd)
    sites_count = df_sites.count()
    
    df_sites.createOrReplaceTempView("_mig_sites")
    target = f"{CATALOG}.{BRONZE_SCHEMA}.air_monitoring_sites"
    
    spark.sql(f"""
        MERGE INTO {target} AS t
        USING _mig_sites AS s
        ON t.site_code = s.site_code
        WHEN MATCHED THEN UPDATE SET
            t.site_name = s.site_name,
            t.address = s.address,
            t.allowed_users = s.allowed_users
        WHEN NOT MATCHED THEN INSERT *
    """)
    
    final = spark.sql(f"SELECT COUNT(*) FROM {target}").collect()[0][0]
    print(f"  ✓ UPSERT: {sites_count} Excel → {final} in table")
    spark.catalog.dropTempView("_mig_sites")

except FileNotFoundError:
    print(f"  ⏭ sites.xlsx not found — skipping")
except Exception as e:
    print(f"  ✗ Error: {str(e)[:200]}")

# ============================================================
# STEP 5: Migrate output table (LEFT ANTI JOIN — insert only NEW)
# ============================================================
print("\n[5/6] Migrating output table...")

output_path = f"{MIGRATION_PATH}/Output_Table.xlsx"
try:
    df_pd = pd.read_excel(output_path)
    excel_total = len(df_pd)
    print(f"  Excel loaded: {excel_total} rows, {len(df_pd.columns)} columns")
    
    # --- TRANSFORM: Sample_Date datetime → DD-Mon-YYYY string ---
    if 'Sample_Date' in df_pd.columns and pd.api.types.is_datetime64_any_dtype(df_pd['Sample_Date']):
        df_pd['Sample_Date'] = df_pd['Sample_Date'].dt.strftime('%d-%b-%Y')
        df_pd.loc[df_pd['Sample_Date'].isna(), 'Sample_Date'] = None
        print(f"  ✓ Sample_Date → DD-Mon-YYYY")
    
    # --- TRANSFORM: Derive row_status from Frozen_Docs ---
    df_pd['row_status'] = df_pd['Frozen_Docs'].apply(
        lambda x: 'removed' if str(x).strip().lower() == 'x' else 'active'
    )
    removed = (df_pd['row_status'] == 'removed').sum()
    print(f"  ✓ row_status: {excel_total - removed} active, {removed} removed")
    
    # --- TRANSFORM: Derive removal_reason ---
    df_pd['removal_reason'] = df_pd['Frozen_Docs'].apply(
        lambda x: 'V1 frozen document' if str(x).strip().lower() == 'x' else None
    )
    
    # --- TRANSFORM: Generate row_id ---
    df_pd['row_id'] = [str(uuid.uuid4()) for _ in range(excel_total)]
    
    # --- TRANSFORM: Migration metadata ---
    df_pd['uploaded_by'] = 'migrated'
    df_pd['upload_batch_id'] = BATCH_ID
    df_pd['status_updated_at'] = None
    df_pd['modified_by'] = None
    
    # --- TRANSFORM: Delete_docs float NaN → None ---
    df_pd['Delete_docs'] = df_pd['Delete_docs'].apply(
        lambda x: None if pd.isna(x) else str(x)
    )
    
    # --- Ensure grain columns are strings for matching ---
    for col in MATCH_GRAIN:
        if col in df_pd.columns:
            df_pd[col] = df_pd[col].apply(lambda x: None if pd.isna(x) else str(x))
    
    # Create Spark DataFrame
    df_excel = spark.createDataFrame(df_pd)
    
    # Get target table columns (for correct column ordering)
    target_table = f"{CATALOG}.{BRONZE_SCHEMA}.air_monitoring_output"
    target_cols = [f.name for f in spark.table(target_table).schema]
    
    # Select matching columns in target order
    select_cols = [c for c in target_cols if c in df_excel.columns]
    df_excel = df_excel.select(select_cols)
    
    # Check current state
    current_count = spark.sql(f"SELECT COUNT(*) FROM {target_table}").collect()[0][0]
    print(f"  Current table: {current_count} rows")
    
    if current_count == 0:
        # ===== FIRST TIME: Full INSERT =====
        print(f"  → Table EMPTY — full load...")
        df_excel.write.mode("append").saveAsTable(target_table)
        new_total = spark.sql(f"SELECT COUNT(*) FROM {target_table}").collect()[0][0]
        print(f"  ✓ FULL LOAD: {new_total} rows inserted")
        
    else:
        # ===== INCREMENTAL: LEFT ANTI JOIN =====
        print(f"  → Table has data — incremental anti-join...")
        
        # Load existing grain keys from Delta
        df_existing = spark.table(target_table).select(*MATCH_GRAIN)
        
        # Anti-join: keep only Excel rows NOT in Delta
        # Handle NULLs: coalesce to sentinel for comparison
        join_conditions = [
            F.coalesce(df_excel[c], F.lit("__NULL__")) == F.coalesce(df_existing[c], F.lit("__NULL__"))
            for c in MATCH_GRAIN
        ]
        join_expr = join_conditions[0]
        for cond in join_conditions[1:]:
            join_expr = join_expr & cond
        
        df_new = df_excel.join(df_existing, join_expr, "left_anti")
        
        new_count = df_new.count()
        print(f"  Anti-join result: {new_count} new rows to insert")
        
        if new_count > 0:
            df_new.write.mode("append").insertInto(target_table)
            final_total = spark.sql(f"SELECT COUNT(*) FROM {target_table}").collect()[0][0]
            print(f"  ✓ INCREMENTAL: {new_count} inserted (table: {current_count} → {final_total})")
        else:
            print(f"  ✓ UP-TO-DATE: no new rows to insert")

except FileNotFoundError:
    print(f"  ⏭ Output_Table.xlsx not found — skipping")
except Exception as e:
    import traceback
    print(f"  ✗ Error:")
    traceback.print_exc()

# ============================================================
# STEP 6: Summary
# ============================================================
print(f"\n[6/6] Final state")
print(f"{'='*70}")

tables = [
    (f"{CATALOG}.{BRONZE_SCHEMA}.air_monitoring_sites", "sites"),
    (f"{CATALOG}.{BRONZE_SCHEMA}.air_monitoring_output", "output"),
    (f"{CATALOG}.{BRONZE_SCHEMA}.air_monitoring_upload_log", "upload_log"),
]
for t, name in tables:
    try:
        cnt = spark.sql(f"SELECT COUNT(*) FROM {t}").collect()[0][0]
        print(f"  {t}: {cnt} rows")
    except:
        print(f"  {t}: NOT FOUND")

print(f"""
{'='*70}
Done! Catalog: {CATALOG} | Batch: {BATCH_ID}

BEHAVIOR SUMMARY:
  • Sites: UPSERT on site_code (always takes latest from Excel)
  • Output: LEFT ANTI JOIN on expanded grain — inserts only NEW rows
  • Upload_log: untouched (app writes directly, no Excel source)
  
TO ADD MORE DATA LATER:
  1. Export fresh Output_Table.xlsx from V1 SharePoint
  2. Upload to: {MIGRATION_PATH}/Output_Table.xlsx
  3. Re-run: python setup_tables.py {CATALOG}
  4. Only net-new rows inserted (existing rows never touched)
""")
