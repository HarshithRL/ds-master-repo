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
from functools import lru_cache

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
    # DEV/TEST workspace — uses shared WE-SPOKE-KV with "-t-" secret names
    "7181820732839861": {
        "catalog": "automation_d",
        "warehouse": "69ada62b2fb9b9e2",
        "keyvault": "https://WE-SPOKE-KV.vault.azure.net/",
        "auth_mode": "user",
        "secret_doc_endpoint": "ds-we-spoke-mdp-t-formrecogniser-endpoint",
        "secret_doc_key": "ds-we-spoke-mdp-t-formrecogniser-key1",
        "secret_openai": "ds-we-spoke-mdp-t-openai",
    },
    # ACC workspace — dedicated automation KV
    "4796304964978539": {
        "catalog": "automation_a",
        "warehouse": "fe5f9b40ac3a9b6e",
        "keyvault": "https://WE-SPOKE-MDP-AUT-A-KV.vault.azure.net/",
        "auth_mode": "user",
        "secret_doc_endpoint": "ds-we-spoke-mdp-formrecogniser-endpoint",
        "secret_doc_key": "ds-we-spoke-mdp-formrecogniser-key",
        "secret_openai": "ds-we-spoke-mdp-openai",
    },
    # PRD workspace — dedicated automation KV
    "4844910598668398": {
        "catalog": "automation_p",
        "warehouse": "83294e3f6b44f138",
        "keyvault": "https://WE-SPOKE-MDP-AUT-P-KV.vault.azure.net/",
        "auth_mode": "user",
        "secret_doc_endpoint": "ds-we-spoke-mdp-formrecogniser-endpoint",
        "secret_doc_key": "ds-we-spoke-mdp-formrecogniser-key",
        "secret_openai": "ds-we-spoke-mdp-openai",
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
# Key Vault Secret Retrieval
# ============================================================
# If we detected a non-DEV environment, override AZURE_KEYVAULT_URL
if _detected_env and _detected_env.get("keyvault"):
    os.environ.setdefault("AZURE_KEYVAULT_URL", _detected_env["keyvault"])


@lru_cache(maxsize=1)
def _get_keyvault_client():
    """Lazily initialise the Key Vault SecretClient (cached for app lifetime)."""
    try:
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient
    except ImportError:
        logger.warning(
            "azure-identity or azure-keyvault-secrets not installed. "
            "Falling back to environment variables for secrets."
        )
        return None

    vault_url = os.environ.get("AZURE_KEYVAULT_URL")
    if not vault_url:
        logger.warning(
            "AZURE_KEYVAULT_URL not set. Falling back to environment variables for secrets."
        )
        return None

    try:
        credential = DefaultAzureCredential()
        client = SecretClient(vault_url=vault_url, credential=credential)
        return client
    except Exception as e:
        logger.error(f"Failed to initialise Key Vault client: {e}")
        return None


def get_secret(secret_name: str, env_var_fallback: str, default: str = "") -> str:
    """
    Retrieve a secret from Azure Key Vault, falling back to an env var.

    Priority:
      1. Azure Key Vault (via AZURE_KEYVAULT_URL)
      2. Environment variable (env_var_fallback)
      3. default (empty string — forces explicit configuration)

    Args:
        secret_name: Name of the secret in Key Vault (e.g. 'openai-api-key')
        env_var_fallback: Environment variable name to check if Key Vault is unavailable
        default: Last-resort default (should be empty for secrets, URL for endpoints)
    """
    # Try Key Vault first
    client = _get_keyvault_client()
    if client:
        try:
            secret = client.get_secret(secret_name)
            return secret.value
        except Exception as e:
            logger.warning(f"Could not fetch '{secret_name}' from Key Vault: {e}")

    # Fallback to environment variable
    return os.environ.get(env_var_fallback, default)

# ============================================================
# Unity Catalog — All tables in Bronze
# Priority: auto-detected env > app.yaml env var > hardcoded default
# ============================================================
UNITY_CATALOG = _detected_env["catalog"] if _detected_env else os.environ.get("UNITY_CATALOG", "automation_d")
BRONZE_SCHEMA = os.environ.get("BRONZE_SCHEMA", "bronze")
SILVER_SCHEMA = os.environ.get("SILVER_SCHEMA", "silver")
GOLD_SCHEMA = os.environ.get("GOLD_SCHEMA", "gold")

# Volume for PDF uploads (lives in bronze schema)
VOLUME_NAME = os.environ.get("VOLUME_NAME", "bronze_volume")
VOLUME_SUBFOLDER = "uploaded_reports"
IMAGES_SUBFOLDER = "images"  # static assets (logo, etc.)
AIR_MONITORING_FOLDER = "air_monitoring"  # subfolder within volume for all app data

# ============================================================
# Table references (fully qualified)
# ============================================================
SITES_TABLE = f"{UNITY_CATALOG}.{BRONZE_SCHEMA}.air_monitoring_sites"
OUTPUT_TABLE = f"{UNITY_CATALOG}.{BRONZE_SCHEMA}.air_monitoring_output"
UPLOAD_LOG_TABLE = f"{UNITY_CATALOG}.{BRONZE_SCHEMA}.air_monitoring_upload_log"

# Volume path for PDF storage
VOLUME_PATH = f"/Volumes/{UNITY_CATALOG}/{BRONZE_SCHEMA}/{VOLUME_NAME}/{AIR_MONITORING_FOLDER}/{VOLUME_SUBFOLDER}"

# ============================================================
# SQL Warehouse — from env var (different per workspace)
# Auto-detection overrides stale app.yaml values
# ============================================================
WAREHOUSE_ID = _detected_env["warehouse"] if _detected_env else os.environ.get("DATABRICKS_WAREHOUSE_ID", "69ada62b2fb9b9e2")

# ============================================================
# Azure Document Intelligence
# Secrets fetched from Key Vault at runtime; env var as fallback.
# Key Vault secret names: ds-we-spoke-mdp-formrecogniser-endpoint, ds-we-spoke-mdp-formrecogniser-key
# ============================================================
_doc_endpoint_secret = _detected_env["secret_doc_endpoint"] if _detected_env else "ds-we-spoke-mdp-t-formrecogniser-endpoint"
_doc_key_secret = _detected_env["secret_doc_key"] if _detected_env else "ds-we-spoke-mdp-t-formrecogniser-key1"

DOC_INTELLIGENCE_ENDPOINT = get_secret(
    _doc_endpoint_secret,
    "DOC_INTELLIGENCE_ENDPOINT"
)
DOC_INTELLIGENCE_KEY = get_secret(
    _doc_key_secret,
    "DOC_INTELLIGENCE_KEY"
)

# ============================================================
# Azure OpenAI
# Secrets fetched from Key Vault at runtime; env var as fallback.
# Key Vault secret names: openai-endpoint, openai-api-key
# ============================================================
OPENAI_CONFIG = {
    "endpoint": get_secret("openai-endpoint", "OPENAI_ENDPOINT"),
    "api_key": get_secret(_detected_env["secret_openai"] if _detected_env else "ds-we-spoke-mdp-t-openai", "OPENAI_API_KEY"),
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
