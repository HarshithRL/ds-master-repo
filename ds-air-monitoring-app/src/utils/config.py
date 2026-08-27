"""
Configuration for Air Monitoring V2 App.
All environment-specific values read from environment variables (set in app.yaml).

Secret Management:
  - Primary: Environment variables defined in app.yaml (works immediately)
  - Secondary (optional): Azure Key Vault via ClientSecretCredential
    Set USE_KEYVAULT=true in app.yaml to enable KV lookup.
    Requires app SPN to have Access Policy on the vault.
"""
import os
import logging

logger = logging.getLogger(__name__)


# ============================================================
# Environment Auto-Detection
# ============================================================
_host = os.environ.get("DATABRICKS_HOST", "")

_ENV_OVERRIDES = {
    "7181820732839861": {
        "catalog": "automation_d",
        "auth_mode": "user",
        "keyvault_url": "https://we-spoke-mdp-aut-t-kv.vault.azure.net",
    },
    "4796304964978539": {
        "catalog": "automation_a",
        "auth_mode": "user",
        "keyvault_url": "https://we-spoke-mdp-aut-a-kv.vault.azure.net",
    },
    "4844910598668398": {
        "catalog": "automation_p",
        "auth_mode": "user",
        "keyvault_url": "https://we-spoke-mdp-aut-p-kv.vault.azure.net",
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
# SQL_WAREHOUSE_ID is injected by app.yaml (valueFrom: sql-warehouse)
WAREHOUSE_ID = os.environ.get("SQL_WAREHOUSE_ID") or os.environ.get("DATABRICKS_WAREHOUSE_ID", "69ada62b2fb9b9e2")


# ============================================================
# Secret Retrieval
# ============================================================
# Mode 1 (default): Read from environment variables (set in app.yaml)
# Mode 2 (optional): Azure Key Vault via ClientSecretCredential
#   To enable: set USE_KEYVAULT=true in app.yaml and ensure app SPN
#   has Access Policy on the vault.
# ============================================================

_USE_KEYVAULT = os.environ.get("USE_KEYVAULT", "false").lower() == "true"
_kv_client = None

# Key Vault secret name mapping per environment
_SECRET_KEYS = {
    "7181820732839861": {  # TEST
        "DOC_INTELLIGENCE_ENDPOINT": "ds-we-spoke-mdp-formrecogniser-endpoint",
        "DOC_INTELLIGENCE_KEY": "ds-we-spoke-mdp-t-formrecogniser-key1",
        "OPENAI_API_KEY": "ds-we-spoke-mdp-openai",
    },
    "4796304964978539": {  # ACC
        "DOC_INTELLIGENCE_ENDPOINT": "ds-we-spoke-mdp-formrecogniser-endpoint",
        "DOC_INTELLIGENCE_KEY": "ds-we-spoke-mdp-formrecogniser-key",
        "OPENAI_API_KEY": "ds-we-spoke-mdp-openai",
    },
    "4844910598668398": {  # PRD
        "DOC_INTELLIGENCE_ENDPOINT": "ds-we-spoke-mdp-formrecogniser-endpoint",
        "DOC_INTELLIGENCE_KEY": "ds-we-spoke-mdp-formrecogniser-key",
        "OPENAI_API_KEY": "ds-we-spoke-mdp-openai",
    },
}

if _USE_KEYVAULT:
    try:
        from azure.identity import ClientSecretCredential
        from azure.keyvault.secrets import SecretClient

        _vault_url = _detected_env["keyvault_url"] if _detected_env else os.environ.get(
            "AZURE_KEYVAULT_URL", "https://we-spoke-mdp-aut-t-kv.vault.azure.net"
        )
        _client_id = os.environ.get("DATABRICKS_CLIENT_ID", "")
        _client_secret = os.environ.get("DATABRICKS_CLIENT_SECRET", "")
        _tenant_id = os.environ.get("AZURE_TENANT_ID", "e23c7299-f64d-4de4-a6a1-b40d3145528c")

        if _client_id and _client_secret and _tenant_id:
            _credential = ClientSecretCredential(
                tenant_id=_tenant_id, client_id=_client_id, client_secret=_client_secret
            )
            _kv_client = SecretClient(vault_url=_vault_url, credential=_credential)
            logger.info(f"Key Vault enabled: {_vault_url}")
        else:
            logger.warning("USE_KEYVAULT=true but missing SPN credentials")
    except ImportError:
        logger.warning("USE_KEYVAULT=true but azure-keyvault-secrets not installed")
    except Exception as e:
        logger.error(f"Failed to initialize Key Vault client: {e}")


def _get_secret_key(env_var_name: str) -> str:
    """Map logical env var name to the Key Vault secret name."""
    for ws_id, keys in _SECRET_KEYS.items():
        if ws_id in _host:
            return keys.get(env_var_name, "")
    return _SECRET_KEYS.get("7181820732839861", {}).get(env_var_name, "")


def get_secret(env_var_name: str, default: str = "") -> str:
    """Fetch a secret: env var first, then optionally Key Vault.

    With USE_KEYVAULT=false (default): reads only from env vars.
    With USE_KEYVAULT=true: tries Key Vault if env var is empty.
    """
    # 1. Environment variable (always checked first)
    value = os.environ.get(env_var_name, "")
    if value:
        return value

    # 2. Azure Key Vault (only if enabled)
    if _kv_client:
        kv_name = _get_secret_key(env_var_name)
        if kv_name:
            try:
                secret = _kv_client.get_secret(kv_name)
                if secret.value:
                    logger.info(f"Fetched '{kv_name}' from Key Vault for {env_var_name}")
                    return secret.value
            except Exception as e:
                logger.error(f"Key Vault fetch failed for '{kv_name}': {e}")

    if not default:
        logger.warning(f"Secret '{env_var_name}' not found in env vars" +
                      (" or Key Vault" if _USE_KEYVAULT else ""))
    return default


# ============================================================
# Secret values (read from env vars set in app.yaml)
# ============================================================
DOC_INTELLIGENCE_ENDPOINT = get_secret("DOC_INTELLIGENCE_ENDPOINT")
DOC_INTELLIGENCE_KEY = get_secret("DOC_INTELLIGENCE_KEY")

# ============================================================
# Azure OpenAI
# ============================================================
OPENAI_ENDPOINT = os.environ.get("OPENAI_ENDPOINT", "https://musta-m830len4-eastus2.cognitiveservices.azure.com/")
OPENAI_API_VERSION = os.environ.get("OPENAI_API_VERSION", "2024-12-01-preview")
OPENAI_MODEL_NAME = os.environ.get("OPENAI_MODEL_NAME", "EPD_Pulse_gpt-5.4")

OPENAI_CONFIG = {
    "endpoint": OPENAI_ENDPOINT,
    "api_key": get_secret("OPENAI_API_KEY"),
    "api_version": OPENAI_API_VERSION,
    "model_name": OPENAI_MODEL_NAME,
}


def get_openai_config() -> dict:
    """Get OpenAI config (same as OPENAI_CONFIG but re-reads api_key)."""
    return {
        "endpoint": OPENAI_ENDPOINT,
        "api_key": get_secret("OPENAI_API_KEY") or OPENAI_CONFIG["api_key"],
        "api_version": OPENAI_API_VERSION,
        "model_name": OPENAI_MODEL_NAME,
    }


# ============================================================
# Auth Mode
# ============================================================
AUTH_MODE = (_detected_env["auth_mode"] if _detected_env else os.environ.get("AUTH_MODE", "spn")).lower()

# ============================================================
# High Concentration Threshold (f/ml)
# ============================================================
HIGH_CONC_THRESHOLD = float(os.environ.get("HIGH_CONC_THRESHOLD", "0.01"))

# ============================================================
# Duplicate detection grain (same as V1)
# ============================================================
DEDUP_GRAIN = ["Code", "Sample_no", "Sample_Date", "Volume", "Concentration_result"]

# ============================================================
# Legacy compatibility aliases
# ============================================================
SCHEMA = BRONZE_SCHEMA  # all tables now in bronze
