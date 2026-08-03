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
# Secret Retrieval — Lazy Loading via User Token
# ============================================================
# Secrets are stored in Azure Key Vault, accessed through Databricks
# Secret Scopes. The user's forwarded access token is used to read
# from the scope at RUNTIME (not import time).
#
# Flow: User logs in → x-forwarded-access-token available
#       → WorkspaceClient(token=user_token)
#       → secrets.get_secret(scope, key)
#       → value decoded from base64
#
# Scope names per environment:
#   DEV: WE-SPOKE-MDP-AUT-T-KV
#   ACC: WE-SPOKE-MDP-AUT-A-KV
#   PRD: WE-SPOKE-MDP-AUT-P-KV
# ============================================================

_SCOPE_MAP = {
    "7181820732839861": "WE-SPOKE-MDP-AUT-T-KV",   # DEV
    "4796304964978539": "WE-SPOKE-MDP-AUT-A-KV",   # ACC
    "4844910598668398": "WE-SPOKE-MDP-AUT-P-KV",   # PRD
}

_SECRET_SCOPE = "WE-SPOKE-MDP-AUT-T-KV"  # default
for _ws_id, _scope_name in _SCOPE_MAP.items():
    if _ws_id in _host:
        _SECRET_SCOPE = _scope_name
        break

# Secret KEY names per environment (from Azure Key Vault)
_SECRET_KEYS = {
    "7181820732839861": {  # DEV
        "doc_endpoint": "ds-we-spoke-mdp-formrecogniser-endpoint",
        "doc_key": "ds-we-spoke-mdp-t-formrecogniser-key1",
        "openai": "ds-we-spoke-mdp-openai",
    },
    "4796304964978539": {  # ACC
        "doc_endpoint": "ds-we-spoke-mdp-formrecogniser-endpoint",
        "doc_key": "ds-we-spoke-mdp-formrecogniser-key",
        "openai": "ds-we-spoke-mdp-openai",
    },
    "4844910598668398": {  # PRD
        "doc_endpoint": "ds-we-spoke-mdp-formrecogniser-endpoint",
        "doc_key": "ds-we-spoke-mdp-formrecogniser-key",
        "openai": "ds-we-spoke-mdp-openai",
    },
}

# Default to DEV keys
_KEYS = _SECRET_KEYS.get("7181820732839861")
for _ws_id, _keys in _SECRET_KEYS.items():
    if _ws_id in _host:
        _KEYS = _keys
        break


# Cache for loaded secrets (per app lifetime)
_secret_cache = {}


def get_secret(key_name: str, env_var_fallback: str = "", default: str = "") -> str:
    """
    Retrieve a secret from Databricks Secret Scope using the logged-in user's token.

    Priority:
      1. Cache (already loaded this session)
      2. Environment variable (if set in app.yaml)
      3. Databricks Secret Scope (via user's x-forwarded-access-token)
      4. Default value

    Args:
        key_name: The secret key name in the Databricks scope (= KV secret name)
        env_var_fallback: Env var to check first (platform may inject via valueFrom)
        default: Last-resort default value
    """
    # Check cache first
    if key_name in _secret_cache:
        return _secret_cache[key_name]

    # Check env var (in case valueFrom works or manual override)
    if env_var_fallback:
        env_val = os.environ.get(env_var_fallback)
        if env_val:
            _secret_cache[key_name] = env_val
            logger.info(f"Secret '{key_name}' loaded from env var '{env_var_fallback}'")
            return env_val

    # Try Databricks Secret Scope with user's token
    try:
        import streamlit as st
        import base64
        from databricks.sdk import WorkspaceClient

        user_token = st.context.headers.get("x-forwarded-access-token")
        if user_token:
            # Clear SPN env vars to avoid "more than one auth method" conflict
            _saved_cid = os.environ.pop("DATABRICKS_CLIENT_ID", None)
            _saved_csec = os.environ.pop("DATABRICKS_CLIENT_SECRET", None)
            try:
                w = WorkspaceClient(
                    host=os.environ.get("DATABRICKS_HOST"),
                    token=user_token
                )
                result = w.secrets.get_secret(scope=_SECRET_SCOPE, key=key_name)
                if result.value:
                    if isinstance(result.value, bytes):
                        decoded = base64.b64decode(result.value).decode("utf-8")
                    else:
                        decoded = base64.b64decode(result.value.encode()).decode("utf-8")
                    _secret_cache[key_name] = decoded
                    logger.info(f"Secret '{key_name}' loaded from scope '{_SECRET_SCOPE}'")
                    return decoded
            except Exception as e:
                logger.warning(f"Could not fetch '{key_name}' from scope '{_SECRET_SCOPE}': {e}")
            finally:
                if _saved_cid:
                    os.environ["DATABRICKS_CLIENT_ID"] = _saved_cid
                if _saved_csec:
                    os.environ["DATABRICKS_CLIENT_SECRET"] = _saved_csec
    except Exception as e:
        logger.debug(f"Streamlit context not available for secret '{key_name}': {e}")

    if default:
        return default
    logger.warning(f"Secret '{key_name}' could not be loaded from any source")
    return ""


# ============================================================
# Lazy-loaded secret properties (fetched on first access)
# ============================================================
class _LazySecret:
    """Descriptor that fetches a secret on first access (when user context is available)."""
    def __init__(self, key_name: str, env_fallback: str = "", default: str = ""):
        self.key_name = key_name
        self.env_fallback = env_fallback
        self.default = default
        self._value = None

    def get(self) -> str:
        if self._value is None:
            self._value = get_secret(self.key_name, self.env_fallback, self.default)
        return self._value


_doc_endpoint = _LazySecret(_KEYS["doc_endpoint"], "DOC_INTELLIGENCE_ENDPOINT")
_doc_key = _LazySecret(_KEYS["doc_key"], "DOC_INTELLIGENCE_KEY")
_openai_key = _LazySecret(_KEYS["openai"], "OPENAI_API_KEY")


def get_doc_intelligence_endpoint() -> str:
    return _doc_endpoint.get()

def get_doc_intelligence_key() -> str:
    return _doc_key.get()

def get_openai_api_key() -> str:
    return _openai_key.get()


# Legacy module-level variables (empty at import, populated on first call)
# Code that reads these directly will get empty string until get_*() is called
DOC_INTELLIGENCE_ENDPOINT = ""
DOC_INTELLIGENCE_KEY = ""

# ============================================================
# Azure OpenAI
# Secrets fetched from Key Vault at runtime; env var as fallback.
# Key Vault secret names: openai-endpoint, openai-api-key
# ============================================================
def get_openai_config() -> dict:
    """Get OpenAI config with lazy-loaded API key from Key Vault."""
    return {
        "endpoint": os.environ.get("OPENAI_ENDPOINT", "https://musta-m830len4-eastus2.cognitiveservices.azure.com/"),
        "api_key": get_openai_api_key(),
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
