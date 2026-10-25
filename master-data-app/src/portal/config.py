import os
from pathlib import Path

from config import (
    REQUEST_HISTORY_TABLE,
    REQUEST_TABLE,
    REQUEST_WAREHOUSE_ID,
    UNITY_CATALOG,
)

# =============================================================================
# FILE PATHS
# =============================================================================

# Configuration workbooks are not shipped with the app: the setup job reads
# them from the Volume and the app reads the seeded snapshots (core/loaders.py).

BASE_DIR = Path(__file__).resolve().parent.parent

DEMO_REQUESTS_FILE = BASE_DIR / "demo_requests.jsonl"

USER_GUIDE_FILE = BASE_DIR / "docs" / "user_guide.pdf"

# =============================================================================
# ASSETS
# =============================================================================

PAGE_ICON_FILE = "assets/axiom_icon.png"
HEADER_LOGO_FILE = "assets/axiom_logo.svg"

# =============================================================================
# ATTACHMENT LIMITS
# =============================================================================

MAX_ATTACHMENT_SIZE_BYTES = 3 * 1024 * 1024

MAX_ATTACHMENTS_TOTAL_BYTES = 5 * 1024 * 1024

# =============================================================================
# SETTINGS
# =============================================================================

# Tables, warehouse and catalog come from src/config.py (catalog detected
# from the workspace: automation_d / automation_a / automation_p).


def setting(name: str, default: str = "") -> str:
    """Environment-injected settings only (app.yaml env and secret resources)."""
    return os.environ.get(name, default).strip()


def _flag(name: str, default: str) -> bool:
    return setting(name, default).lower() in {"1", "true", "yes", "y"}


# =============================================================================
# ENVIRONMENT (from the workspace's catalog)
# =============================================================================

# test (T, DEV workspace) / acc (A) / prod (P). Test and acc show a coloured
# ribbon so nobody mistakes them for production; prod shows none.
APP_ENV = {"automation_d": "test", "automation_a": "acc", "automation_p": "prod"}[UNITY_CATALOG]

# This bundle is the live app; the demo / training app is deployed separately.
DEMO_MODE = False

# Customer data: "sap" (Business Partner API) or "databricks" (source table
# mapped in General_Data_Fields, read with the visitor's token)
CUSTOMER_SOURCE = setting("CUSTOMER_SOURCE", "sap").lower()

# =============================================================================
# SAP BUSINESS PARTNER API (portal/integrations/sap_business_partner.py)
# =============================================================================

_SAP_API_URL_BY_CATALOG = {
    "automation_d": "https://vhmcosd1ci.sap.etexgroup.com:44300/sap/opu/odata/sap/API_BUSINESS_PARTNER",
    "automation_a": "https://vhmcosd1ci.sap.etexgroup.com:44300/sap/opu/odata/sap/API_BUSINESS_PARTNER",  #
    "automation_p": "https://vhmcosd1ci.sap.etexgroup.com:44300/sap/opu/odata/sap/API_BUSINESS_PARTNER",  
}
SAP_API_URL = setting("SAP_API_URL") or _SAP_API_URL_BY_CATALOG[UNITY_CATALOG]
SAP_CLIENT = setting("SAP_CLIENT")  # sap-client, e.g. 100; empty = the system default
# Technical user from the app's secret resources sap-user / sap-password
SAP_USER = setting("SAP_USER")
SAP_PASSWORD = setting("SAP_PASSWORD")
# Internal certificates: path of the company CA bundle (e.g. assets/etex_ca.pem)
SAP_CA_BUNDLE = str(BASE_DIR / setting("SAP_CA_BUNDLE")) if setting("SAP_CA_BUNDLE") else ""
SAP_VERIFY_TLS = _flag("SAP_VERIFY_TLS", "true")
SAP_TIMEOUT_SECONDS = int(setting("SAP_TIMEOUT_SECONDS", "20") or 20)
# How long one customer's SAP data is reused while a request is filled in
SAP_CACHE_SECONDS = int(setting("SAP_CACHE_SECONDS", "300") or 300)

# An environment without an SAP endpoint or technical user keeps the Databricks
# source instead of failing every lookup.
if CUSTOMER_SOURCE == "sap" and not (SAP_API_URL and SAP_USER and SAP_PASSWORD):
    CUSTOMER_SOURCE = "databricks"

# =============================================================================
# CUSTOMER MASTER WORKBENCH (page "workbench" of this app)
# =============================================================================


def _app_url() -> str:
    """This app's address: ds-master-data-app-<workspace id>.<n>.azure.databricksapps.com."""
    host = setting("DATABRICKS_HOST").replace("https://", "").replace("http://", "").rstrip("/")
    if not host.startswith("adb-") or not host.endswith(".azuredatabricks.net"):
        return ""
    name = setting("DATABRICKS_APP_NAME", "ds-master-data-app")  # set by Databricks Apps
    return "https://" + host.replace("adb-", f"{name}-", 1).replace(
        ".azuredatabricks.net", ".azure.databricksapps.com"
    )


# Teams messages link to WORKBENCH_URL?request=<id> (opens the request directly)
WORKBENCH_URL = setting("WORKBENCH_URL") or (_app_url() + "/workbench" if _app_url() else "")
