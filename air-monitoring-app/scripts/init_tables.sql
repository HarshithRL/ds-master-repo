-- ============================================================
-- Air Monitoring V2 — Table Initialization & Data Seed
-- Run once per environment during first deployment.
-- The UNITY_CATALOG env var determines which catalog to target.
-- Usage: databricks sql execute --warehouse-id $WAREHOUSE_ID --file scripts/init_tables.sql
-- ============================================================

-- 1. Bronze: Upload Log
CREATE TABLE IF NOT EXISTS ${UNITY_CATALOG}.bronze.air_monitoring_upload_log (
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
) USING DELTA
COMMENT 'Air Monitoring V2 - Upload log tracking all PDF uploads';

-- 2. Gold: Sites (dimension / RLS)
CREATE TABLE IF NOT EXISTS ${UNITY_CATALOG}.gold.air_monitoring_sites (
    site_name STRING,
    site_code STRING,
    address STRING,
    allowed_users STRING
) USING DELTA
COMMENT 'Air Monitoring V2 - Sites dimension with RLS allowed_users';

-- 3. Gold: Output (main fact table)
CREATE TABLE IF NOT EXISTS ${UNITY_CATALOG}.gold.air_monitoring_output (
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
    row_id STRING,
    uploaded_by STRING,
    upload_batch_id STRING,
    modified_by STRING
) USING DELTA
COMMENT 'Air Monitoring V2 - Main output table with sample measurements';
