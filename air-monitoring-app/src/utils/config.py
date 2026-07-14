"""
Configuration for Air Monitoring V2 App.
All environment-specific values read from environment variables (set in app.yaml).
This enables the same source code to run in dev/acc/prd without changes.

Medallion Architecture:
  - Bronze: upload_log (raw ingest events), PDF volume storage
  - Silver: (reserved for future transformations)
  - Gold: output_table (curated measurements), sites (dimension/RLS)

Environments:
  - TEST: automation_d (https://adb-7181820732839861.1.azuredatabricks.net/)
  - ACC:  automation_a (https://adb-4796304964978539.19.azuredatabricks.net/)
  - PRD:  automation_p (https://adb-4844910598668398.18.azuredatabricks.net/)
"""
import os

# ============================================================
# Unity Catalog — Medallion Architecture
# Env vars set per environment in app.yaml (automation_d / automation_a / automation_p)
# ============================================================
UNITY_CATALOG = os.environ.get("UNITY_CATALOG", "automation_d")
BRONZE_SCHEMA = os.environ.get("BRONZE_SCHEMA", "bronze")
SILVER_SCHEMA = os.environ.get("SILVER_SCHEMA", "silver")
GOLD_SCHEMA = os.environ.get("GOLD_SCHEMA", "gold")

# Volume for PDF uploads (lives in bronze schema)
VOLUME_NAME = os.environ.get("VOLUME_NAME", "bronze_volume")
VOLUME_SUBFOLDER = "uploaded_reports"  # migrated from old app
IMAGES_SUBFOLDER = "images"  # static assets (logo, etc.)

# ============================================================
# Table references (fully qualified)
# ============================================================
SITES_TABLE = f"{UNITY_CATALOG}.{GOLD_SCHEMA}.air_monitoring_sites"
OUTPUT_TABLE = f"{UNITY_CATALOG}.{GOLD_SCHEMA}.air_monitoring_output"
UPLOAD_LOG_TABLE = f"{UNITY_CATALOG}.{BRONZE_SCHEMA}.air_monitoring_upload_log"

# Volume path for PDF storage
VOLUME_PATH = f"/Volumes/{UNITY_CATALOG}/{BRONZE_SCHEMA}/{VOLUME_NAME}/{VOLUME_SUBFOLDER}"

# ============================================================
# SQL Warehouse — from env var (different per workspace)
# ============================================================
WAREHOUSE_ID = os.environ.get("DATABRICKS_WAREHOUSE_ID", "69ada62b2fb9b9e2")

# ============================================================
# Azure Document Intelligence
# ============================================================
DOC_INTELLIGENCE_ENDPOINT = os.environ.get(
    "DOC_INTELLIGENCE_ENDPOINT",
    "https://we-spoke-mdp-t-formrecogniser.cognitiveservices.azure.com/"
)
DOC_INTELLIGENCE_KEY = os.environ.get(
    "DOC_INTELLIGENCE_KEY",
    "1bdb532656d248bda3c6b58a9b75441f"
)

# ============================================================
# Azure OpenAI
# ============================================================
OPENAI_CONFIG = {
    "endpoint": os.environ.get("OPENAI_ENDPOINT", "https://musta-m830len4-eastus2.cognitiveservices.azure.com/"),
    "api_key": os.environ.get("OPENAI_API_KEY", "CqKjJbBku9Uf2PQLxKvDgaXF5xt3BU5u8yvQJsev3cwfycMxVosuJQQJ99BCACHYHv6XJ3w3AAAAACOGmDfg"),
    "api_version": os.environ.get("OPENAI_API_VERSION", "2024-12-01-preview"),
    "model_name": os.environ.get("OPENAI_MODEL_NAME", "EPD_Pulse_gpt-5.4"),
}

# ============================================================
# Auth Mode: "spn" (app service principal) or "user" (on-behalf-of-user)
# Switch this single value to toggle between auth modes.
# - "spn":  App uses its own service principal identity (all users share same perms)
# - "user": App acts as the logged-in user (Unity Catalog RLS/permissions per user)
# ============================================================
AUTH_MODE = os.environ.get("AUTH_MODE", "spn").lower()  # default: spn

# ============================================================
# High Concentration Threshold (f/ml)
# Change this single value to update threshold everywhere in the app.
# ============================================================
HIGH_CONC_THRESHOLD = float(os.environ.get("HIGH_CONC_THRESHOLD", "0.01"))

# ============================================================
# Duplicate detection grain (same as V1)
# ============================================================
DEDUP_GRAIN = ["Code", "Sample_no", "Sample_Date", "Volume", "Concentration_result"]

# ============================================================
# Legacy compatibility aliases
# (used in older code paths — prefer explicit BRONZE/GOLD references)
# ============================================================
SCHEMA = GOLD_SCHEMA  # backward compat for any old references
