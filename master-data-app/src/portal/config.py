from pathlib import Path


# =============================================================================
# FILE PATHS
# =============================================================================

# portal/config.py lives inside /portal,
# while /data and /assets live one level above it.
BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"
ASSETS_DIR = BASE_DIR / "assets"


# =============================================================================
# DATA FILES
# =============================================================================

RULES_FILE = DATA_DIR / "customer_form_rules.xlsx"
CREDIT_RULES_FILE = DATA_DIR / "credit_management_rules.xlsx"
ASSIGNMENT_RULES_FILE = DATA_DIR / "assignment_rules.xlsx"
REFERENCE_LIBRARY_FILE = DATA_DIR / "customer_reference_library.xlsx"

# =============================================================================
# ASSETS
# =============================================================================

ETEX_LOGO_FILE = ASSETS_DIR / "etex_logo_clean.png"

AXIOM_LOGO_FILE = ASSETS_DIR / "axiom_etex_logo_clean.png"


# =============================================================================
# ATTACHMENT LIMITS
# =============================================================================

MAX_ATTACHMENT_SIZE_BYTES = 3 * 1024 * 1024

MAX_ATTACHMENTS_TOTAL_BYTES = 5 * 1024 * 1024