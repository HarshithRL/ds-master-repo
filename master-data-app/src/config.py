from __future__ import annotations

import os

# =============================================================================
# TABLE ACCESS
# =============================================================================

_CATALOG_BY_WORKSPACE = {
    "7181820732839861": "automation_d",
    "4796304964978539": "automation_a",
    "4844910598668398": "automation_p",
}

_workspace_host = os.environ.get("DATABRICKS_HOST", "")
_detected_catalog = next(
    (
        catalog
        for workspace_id, catalog in _CATALOG_BY_WORKSPACE.items()
        if workspace_id in _workspace_host
    ),
    None,
)
_catalog_override = os.environ.get("MASTER_DATA_CATALOG", "").strip()
if _detected_catalog and _catalog_override and _catalog_override != _detected_catalog:
    raise RuntimeError("MASTER_DATA_CATALOG does not match the Databricks workspace environment")
if not _detected_catalog and not _catalog_override:
    raise RuntimeError("Could not determine the Master Data catalog for this workspace")

UNITY_CATALOG = _catalog_override or _detected_catalog
if UNITY_CATALOG not in set(_CATALOG_BY_WORKSPACE.values()):
    raise ValueError(f"Unsupported Master Data catalog: {UNITY_CATALOG}")

BRONZE_SCHEMA = "bronze"
REQUEST_WAREHOUSE_ID = (
    os.environ.get("SQL_WAREHOUSE_ID")
    or os.environ.get("DATABRICKS_WAREHOUSE_ID", "")
).strip()
REQUEST_TABLE = f"{UNITY_CATALOG}.{BRONZE_SCHEMA}.master_data_app_requests"
REQUEST_HISTORY_TABLE = f"{UNITY_CATALOG}.{BRONZE_SCHEMA}.master_data_app_request_history"
CONFIGURATION_TABLE = f"{UNITY_CATALOG}.{BRONZE_SCHEMA}.master_data_app_configuration"

# =============================================================================
# THEME COLOURS
# =============================================================================

ETEX_ORANGE = "#EB6910"
ETEX_BLACK = "#26333D"
ETEX_DARK = "#24313A"
ETEX_LIGHT = "#F5F5F3"
ETEX_BORDER = "#D9D9D6"
