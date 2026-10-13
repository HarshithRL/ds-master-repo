import os
from pathlib import Path

from config import REQUEST_HISTORY_TABLE, REQUEST_TABLE, REQUEST_WAREHOUSE_ID

# =============================================================================
# MODE
# =============================================================================

# True: requests are stored in demo_requests.jsonl and customers come from
# the demo workbook. False: requests go to the Databricks table read by the
# Customer Master Workbench (portal/integrations/workbench.py).
# Notifications (Power Automate) are sent in both modes when a flow URL is set.
DEMO_MODE = False

# =============================================================================
# FILE PATHS
# =============================================================================

BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"
ASSETS_DIR = BASE_DIR / "assets"

# =============================================================================
# DATA FILES
# =============================================================================

CUSTOMER_DB_FILE = DATA_DIR / "customer_demo_database.xlsx"
RULES_FILE = DATA_DIR / "customer_form_rules.xlsx"
CREDIT_RULES_FILE = DATA_DIR / "credit_management_rules.xlsx"
ASSIGNMENT_RULES_FILE = DATA_DIR / "assignment_rules.xlsx"
REFERENCE_LIBRARY_FILE = DATA_DIR / "general_data.xlsx"

DEMO_REQUESTS_FILE = BASE_DIR / "demo_requests.jsonl"

USER_GUIDE_FILE = BASE_DIR / "docs" / "user_guide.pdf"

# =============================================================================
# ASSETS
# =============================================================================

PAGE_ICON_FILE = "assets/axiom_icon.png"
HEADER_LOGO_FILE = "assets/axiom_logo.png"

# =============================================================================
# ATTACHMENT LIMITS
# =============================================================================

MAX_ATTACHMENT_SIZE_BYTES = 3 * 1024 * 1024

MAX_ATTACHMENTS_TOTAL_BYTES = 5 * 1024 * 1024

# =============================================================================
# ENVIRONMENT SETTINGS
# =============================================================================


def setting(name: str, default: str = "") -> str:
    """Use environment-injected settings; never read demo credentials from YAML."""
    return os.environ.get(name, default).strip()


# =============================================================================
# CUSTOMER MASTER WORKBENCH (shared Databricks tables)
# =============================================================================

