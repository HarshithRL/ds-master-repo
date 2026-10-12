"""Session-state keys and the resets that keep the form consistent."""

from __future__ import annotations

import streamlit as st

from portal.core.utils import clean

LOADED_CUSTOMER_KEY = "loaded_customer_id"
LAST_REQUEST_KEY = "last_submitted_request_id"
RULE_CONTEXT_KEY = "_rule_context_signature"

# Sidebar
SEARCH_INPUT_KEY = "sidebar_customer_search"
SEARCH_RESULTS_KEY = "_customer_search_results"
SEARCH_MESSAGE_KEY = "_customer_search_message"
RECENT_CUSTOMERS_KEY = "_recent_customers"
SESSION_REQUESTS_KEY = "_session_requests"

# Change-request widgets (picker per section and the value inputs)
CHANGE_PICK_PREFIX = "change__pick__"
CHANGE_VALUE_PREFIX = "change__value__"

# Widgets whose values come from the Company Code + Sales Org rules
RULE_DEPENDENT_PREFIXES = (
    "form__",
    "computed_display__",
    "credit__",
    "section_comment__company_code",
    "section_comment__sales_distribution",
    "section_comment__partner_functions",
    "section_comment__credit_management",
    CHANGE_PICK_PREFIX,
    CHANGE_VALUE_PREFIX,
)

# Everything that belongs to one customer's request
FORM_PREFIXES = (
    "form__",
    "computed_display__",
    "credit__",
    "general_data__",
    "section_comment__",
    CHANGE_PICK_PREFIX,
    CHANGE_VALUE_PREFIX,
)


def _delete_keys(prefixes: tuple[str, ...], extra: set[str] = frozenset()) -> None:
    for key in list(st.session_state.keys()):
        if key.startswith(prefixes) or key in extra:
            del st.session_state[key]


def loaded_customer_id() -> str:
    return clean(st.session_state.get(LOADED_CUSTOMER_KEY, ""))


def reset_form_state() -> None:
    """Clear the whole request form, e.g. after loading another customer."""
    _delete_keys(FORM_PREFIXES)


def reset_when_rule_context_changes(signature: str) -> None:
    """Clear rule-driven widgets when request type, Company Code or Sales Org change."""
    if st.session_state.get(RULE_CONTEXT_KEY) != signature:
        _delete_keys(RULE_DEPENDENT_PREFIXES)
        st.session_state[RULE_CONTEXT_KEY] = signature

