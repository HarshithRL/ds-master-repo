"""
Configuration for Air Monitoring V2 App.
All environment-specific values read from environment variables (set in app.yaml).
Secrets are fetched at runtime from Azure Key Vault (no hardcoded keys).

Architecture:
  - Bronze: all tables (output, sites, upload_log) + PDF volume storage

Environments:
  - TEST: automation_d (https://adb-7181820732839861.1.azuredatabricks.net/)
  - ACC:  automation_a (https://adb-4796304964978539.19.azuredatabricks.net/)
  - PRD:  automation_p (https://adb-4844910598668398.18.azuredatabricks.net/)

Secret Management:
  - Secrets stored in Azure Key Vault (WE-SPOKE-MDP-AUT-{T,A,P}-KV)
  - App authenticates via DefaultAzureCredential (service principal or managed identity)
  - AZURE_KEYVAULT_URL env var points to the correct vault per environment
  - Fallback: env vars for local development (never commit real values)
"""
import os
import logging

logger = logging.getLogger(__name__)


# ============================================================
# Environment Auto-Detection
# ============================================================
# DATABRICKS_HOST is ALWAYS set by the platform (default env var).
# If app.yaml has stale/wrong values (e.g. TEST warehouse on ACC workspace),
# this detection overrides them with the correct per-environment config.
# This makes the app self-healing regardless of app.yaml state.
# ============================================================
_host = os.environ.get("DATABRICKS_HOST", "")

_ENV_OVERRIDES = {
    # DEV/TEST workspace — WE-SPOKE-MDP-AUT-T-KV
    "7181820732839861": {
        "catalog": "automation_d",
        "warehouse": "69ada62b2fb9b9e2",
        "auth_mode": "user",
    },
    # ACC workspace — dedicated automation KV
    "4796304964978539": {
        "catalog": "automation_a",
        "warehouse": "fe5f9b40ac3a9b6e",
        "auth_mode": "user",
    },
    # PRD workspace — dedicated automation KV
    "4844910598668398": {
        "catalog": "automation_p",
        "warehouse": "83294e3f6b44f138",
        "auth_mode": "user",
    },
}

_detected_env = None
for _ws_id, _cfg in _ENV_OVERRIDES.items():
    if _ws_id in _host:
        _detected_env = _cfg
        logger.info(f"Environment detected from DATABRICKS_HOST: catalog={_cfg['catalog']}")
        break

if _detected_env is None:
    logger.info("Environment: DEV/TEST (using env vars or defaults)")


# ============================================================
# Unity Catalog — All tables in Bronze
# Priority: auto-detected env > app.yaml env var > hardcoded default
# ============================================================
UNITY_CATALOG = _detected_env["catalog"] if _detected_env else os.environ.get("UNITY_CATALOG", "automation_d")
BRONZE_SCHEMA = os.environ.get("BRONZE_SCHEMA", "bronze")
SILVER_SCHEMA = os.environ.get("SILVER_SCHEMA", "silver")
VOLUME_NAME = os.environ.get("VOLUME_NAME", "bronze_volume")
VOLUME_SUBFOLDER = os.environ.get("VOLUME_SUBFOLDER", "uploaded_reports")
AIR_MONITORING_FOLDER = "air_monitoring"
VOLUME_PATH = f"/Volumes/{UNITY_CATALOG}/{BRONZE_SCHEMA}/{VOLUME_NAME}/{AIR_MONITORING_FOLDER}/{VOLUME_SUBFOLDER}"

# Table names
OUTPUT_TABLE = f"{UNITY_CATALOG}.{BRONZE_SCHEMA}.air_monitoring_output"
SITES_TABLE = f"{UNITY_CATALOG}.{BRONZE_SCHEMA}.air_monitoring_sites"
UPLOAD_LOG_TABLE = f"{UNITY_CATALOG}.{BRONZE_SCHEMA}.air_monitoring_upload_log"

# SQL Warehouse
WAREHOUSE_ID = _detected_env["warehouse"] if _detected_env else os.environ.get("DATABRICKS_WAREHOUSE_ID", "69ada62b2fb9b9e2")


# ============================================================
# Secret Retrieval
# ============================================================
# Secrets come from Azure Key Vault via Databricks Secret Scopes.
# The platform injects them as environment variables through the
# app.yaml valueFrom mechanism (requires app SPN to have READ ACL
# on the scope).
#
# Architecture:
#   Azure Key Vault → Databricks Secret Scope → app.yaml resource
#   → valueFrom → env var → os.environ.get()
# ============================================================

def get_secret(env_var_name: str, default: str = "") -> str:
    """Read a secret from environment variable (injected by platform from KV)."""
    value = os.environ.get(env_var_name, default)
    if not value:
        logger.warning(f"Secret env var '{env_var_name}' not set")
    return value


DOC_INTELLIGENCE_ENDPOINT = get_secret("DOC_INTELLIGENCE_ENDPOINT")
DOC_INTELLIGENCE_KEY = get_secret("DOC_INTELLIGENCE_KEY")

# ============================================================
# Azure OpenAI
# Secrets fetched from Key Vault at runtime; env var as fallback.
# Key Vault secret names: openai-endpoint, openai-api-key
# ============================================================
OPENAI_CONFIG = {
    "endpoint": os.environ.get("OPENAI_ENDPOINT", "https://musta-m830len4-eastus2.cognitiveservices.azure.com/"),
    "api_key": get_secret("OPENAI_API_KEY"),
    "api_version": os.environ.get("OPENAI_API_VERSION", "2024-12-01-preview"),
    "model_name": os.environ.get("OPENAI_MODEL_NAME", "EPD_Pulse_gpt-5.4"),
}

# ============================================================
# Auth Mode: "spn" (app service principal) or "user" (on-behalf-of-user)
# Auto-detected for ACC/PRD (always "user"); env var for DEV.
# ============================================================
AUTH_MODE = (_detected_env["auth_mode"] if _detected_env else os.environ.get("AUTH_MODE", "spn")).lower()

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
SCHEMA = BRONZE_SCHEMA  # all tables now in bronze
