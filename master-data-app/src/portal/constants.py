"""Names and fixed lists shared by the logic and UI layers."""

from __future__ import annotations

# =============================================================================
# GENERIC
# =============================================================================

# Values treated as "yes" in every Excel flag column (active, required, ...)
YES_VALUES = frozenset({"Y", "YES", "TRUE", "1", "X"})

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

# Form_Fields input_type shown as a tick box; ticked sends the SAP flag "X"
CHECKBOX = "checkbox"
FLAG_ON = "X"

# =============================================================================
# REQUEST TYPES
# =============================================================================

CREATE_CUSTOMER = "Create Customer"
CHANGE_CUSTOMER = "Change Customer"
EXTEND_CUSTOMER = "Extend Customer"

REQUEST_TYPES = [
    CREATE_CUSTOMER,
    CHANGE_CUSTOMER,
    EXTEND_CUSTOMER,
]

REQUEST_TYPE_LABELS = {
    CREATE_CUSTOMER: "⊕ Create",
    CHANGE_CUSTOMER: "✎ Change",
    EXTEND_CUSTOMER: "⇄ Extend",
}

# =============================================================================
# FORM SECTIONS
# =============================================================================

COMPANY_CODE = "Company Code"
SALES_DISTRIBUTION = "Sales & Distribution"
PARTNER_FUNCTIONS = "Partner Functions"
CREDIT_MANAGEMENT = "Credit Management"

# (payload / status key, expander title) in display order
SECTIONS = [
    ("general_data", "General Data"),
    ("company_code", COMPANY_CODE),
    ("sales_distribution", SALES_DISTRIBUTION),
    ("partner_functions", PARTNER_FUNCTIONS),
    ("credit_management", CREDIT_MANAGEMENT),
]

SECTION_KEYS = [key for key, _title in SECTIONS]

# Sections whose fields come from customer_form_rules.xlsx
RULE_SECTIONS = {
    "company_code": COMPANY_CODE,
    "sales_distribution": SALES_DISTRIBUTION,
    "partner_functions": PARTNER_FUNCTIONS,
}

PREREQUISITE_TEXT = (
    "Choose a Sales Organization in Request Details "
    "to configure this section"
)

# =============================================================================
# PARTNER FUNCTIONS
# =============================================================================

# (validation label, section title, mode key, existing-ID key, new-address key)
PARTY_GROUPS = [
    (
        "Bill-to Party",
        "Bill-to Party (BP)",
        "bill_to_party_mode",
        "bill_to_party_id",
        "bill_to_party_address",
    ),
    (
        "Payer",
        "Payer (PY)",
        "payer_mode",
        "payer_id",
        "payer_address",
    ),
    (
        "Ship-to Party",
        "Ship-to Party (SH)",
        "ship_to_party_mode",
        "ship_to_party_id",
        "ship_to_party_address",
    ),
]

PARTY_MODE_KEYS = {mode_key for _label, _title, mode_key, _id, _address in PARTY_GROUPS}

SAME_AS_CUSTOMER = "SAME_AS_CUSTOMER"
EXISTING_ID = "EXISTING_ID"
NEW_ADDRESS = "NEW_ADDRESS"

PARTNER_EMAIL_FIELDS = [
    ("partner_yf_email", "Invoice Email Address (YF)"),
    ("partner_cp_email", "Contact Person Email (CP)"),
    ("partner_yl_email", "Logistics Contact Email (YL)"),
]

# Readable names for partner keys (emails and the Change form)
PARTNER_LABELS = {
    "partner_yf_email": "Invoice Email Address (YF)",
    "partner_cp_email": "Contact Person Email (CP)",
    "partner_cp_name": "Contact Person Name (CP)",
    "partner_yl_email": "Logistics Contact Email (YL)",
    "partner_yl_name": "Logistics Contact Name (YL)",
    "partner_yb_employee_id": "Sales Rep Employee ID (YB)",
    "partner_yz_employee_id": "Customer Service Employee ID (YZ)",
    "bill_to_party_mode": "Bill-to Party (BP)",
    "bill_to_party_id": "Bill-to Party ID (BP)",
    "bill_to_party_address": "Bill-to Party Address (BP)",
    "payer_mode": "Payer (PY)",
    "payer_id": "Payer ID (PY)",
    "payer_address": "Payer Address (PY)",
    "ship_to_party_mode": "Ship-to Party (SH)",
    "ship_to_party_id": "Ship-to Party ID (SH)",
    "ship_to_party_address": "Ship-to Party Address (SH)",
}

# Contact name fields rendered by the app itself (not in the rules workbook)
PARTNER_NAME_FIELDS = [
    ("partner_cp_first_name", "Sales Order Contact (CP) First Name"),
    ("partner_cp_last_name", "Sales Order Contact (CP) Surname"),
    ("partner_yl_first_name", "Logistics Contact (YL) First Name"),
    ("partner_yl_last_name", "Logistics Contact (YL) Surname"),
]

PARTNER_NAME_MAX_LENGTH = 60

# =============================================================================
# CREDIT MANAGEMENT
# =============================================================================

# Readable names for credit fields whose form labels rely on their heading
CREDIT_LABELS = {
    "collection_contact_name": "Collection Contact Name",
    "collection_contact_email": "Collection Contact Email",
    "collection_contact_phone": "Collection Contact Phone",
    "accounting_clerk_phone": "Accounting Clerk Phone",
    "accounting_clerk_email": "Accounting Clerk Email",
}

COLLECTION_CONTACT_KEYS = (
    "collection_contact_name",
    "collection_contact_email",
    "collection_contact_phone",
)
