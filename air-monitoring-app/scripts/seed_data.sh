#!/bin/bash
# ============================================================
# Seed data from automation_d (TEST) to target environment
# Usage: ./scripts/seed_data.sh <env>
#   env: acc | prd
#
# Prerequisites:
#   - DATABRICKS_HOST and auth configured for BOTH source (T) and target workspace
#   - init_tables.sql already run on target
#   - This copies: sites (essential for RLS), output_table, upload_log
# ============================================================

set -euo pipefail

ENV=${1:-acc}

case $ENV in
  acc) TARGET_CATALOG="automation_a" ;;
  prd) TARGET_CATALOG="automation_p" ;;
  *)   echo "ERROR: Use acc or prd"; exit 1 ;;
esac

SOURCE_CATALOG="automation_d"

echo "========================================"
echo " Seeding data: $SOURCE_CATALOG → $TARGET_CATALOG"
echo "========================================"

# Sites (essential for app to work — RLS)
echo ""
echo "[1/3] Seeding sites..."
databricks sql execute --warehouse-id $DATABRICKS_WAREHOUSE_ID --sql "
  INSERT INTO ${TARGET_CATALOG}.gold.air_monitoring_sites
  SELECT * FROM ${SOURCE_CATALOG}.gold.air_monitoring_sites
  WHERE NOT EXISTS (
    SELECT 1 FROM ${TARGET_CATALOG}.gold.air_monitoring_sites t
    WHERE t.site_code = ${SOURCE_CATALOG}.gold.air_monitoring_sites.site_code
  )
"

# Output table 
echo ""
echo "[2/3] Seeding output_table..."
databricks sql execute --warehouse-id $DATABRICKS_WAREHOUSE_ID --sql "
  INSERT INTO ${TARGET_CATALOG}.gold.air_monitoring_output
  (Site_name, Code, Site_Address, upload_date, Document_name, Report_number,
   Sample_no, Pump_Location, Lab_name, Project_Name, Building, Sample_Date,
   Analysis_method, Followed_Norm, Volume, Concentration_result, Concentration_unit,
   Concentration_result_in_f_ml, Frozen_Docs, PDF_URL, Flag_EM_Concentration,
   Flag_High_Concentration, Delete_docs, row_status, removal_reason, status_updated_at,
   row_id, uploaded_by, upload_batch_id, modified_by)
  SELECT 
   Site_name, Code, Site_Address, upload_date, Document_name, Report_number,
   Sample_no, Pump_Location, Lab_name, Project_Name, Building, Sample_Date,
   Analysis_method, Followed_Norm, Volume, Concentration_result, Concentration_unit,
   Concentration_result_in_f_ml, Frozen_Docs, PDF_URL, Flag_EM_Concentration,
   Flag_High_Concentration, Delete_docs, row_status, removal_reason, status_updated_at,
   row_id, uploaded_by, upload_batch_id, modified_by
  FROM ${SOURCE_CATALOG}.gold.air_monitoring_output
  WHERE NOT EXISTS (
    SELECT 1 FROM ${TARGET_CATALOG}.gold.air_monitoring_output t
    WHERE t.row_id = ${SOURCE_CATALOG}.gold.air_monitoring_output.row_id
  )
"

# Upload log
echo ""
echo "[3/3] Seeding upload_log..."
databricks sql execute --warehouse-id $DATABRICKS_WAREHOUSE_ID --sql "
  INSERT INTO ${TARGET_CATALOG}.bronze.air_monitoring_upload_log
  SELECT * FROM ${SOURCE_CATALOG}.bronze.air_monitoring_upload_log
  WHERE NOT EXISTS (
    SELECT 1 FROM ${TARGET_CATALOG}.bronze.air_monitoring_upload_log t
    WHERE t.upload_id = ${SOURCE_CATALOG}.bronze.air_monitoring_upload_log.upload_id
  )
"

echo ""
echo "✅ Seed complete for $TARGET_CATALOG"
