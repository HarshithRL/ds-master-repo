"""AXIOM customer request portal: page setup and top-level flow."""

from __future__ import annotations

import streamlit as st

from portal.config import PAGE_ICON_FILE
from portal.constants import CHANGE_CUSTOMER
from portal.core.loaders import (
    load_assignment_rules,
    load_credit_rules,
    load_form_rules,
    load_reference_library,
)
from portal.core.rules import get_form_fields
from portal.integrations.customer_lookup import find_customer
from portal.ui.customer_card import render_customer_information
from portal.ui.layout import render_header, render_request_details, render_welcome
from portal.ui.pages import (
    RequestContext,
    render_change_request,
    render_standard_request,
    render_waiting_sections,
)
from portal.ui.sidebar import render_sidebar
from portal.ui.state import loaded_customer_id
from portal.ui.theme import apply_theme

# =========================================================================
# PAGE
# =========================================================================

st.set_page_config(
    page_title="AXIOM | Master Data Management",
    page_icon=PAGE_ICON_FILE,
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_theme()

try:
    reference_library = load_reference_library()
    rules = load_form_rules()
    credit_rules = load_credit_rules()
    assignment_rules = load_assignment_rules()

except Exception as exc:
    st.error("The app could not load its configuration files.")
    st.exception(exc)
    st.stop()

# =========================================================================
# HEADER / CUSTOMER SEARCH
# =========================================================================

customer_id = loaded_customer_id()

try:
    customer = (
        find_customer(customer_id, reference_library, st.context.headers)
        if customer_id
        else None
    )
except Exception as exc:
    st.error("Customer search failed")
    st.exception(exc)
    st.stop()

render_sidebar(customer=customer, reference_library=reference_library)

render_header(loaded_customer_id=customer_id, header_customer=customer)

if not customer_id:
    render_welcome()
    st.stop()

if customer is None:
    st.error(f"Customer {customer_id} was not found in the customer data")
    st.stop()

# =========================================================================
# TWO-PANEL LAYOUT
# =========================================================================

left_panel, right_panel = st.columns(
    [1, 1.35],
    gap="small",
    vertical_alignment="top",
)

with left_panel:
    render_customer_information(customer, reference_library)

    st.markdown('<div style="height: 8px;"></div>', unsafe_allow_html=True)

    with st.container(border=True, key="request_details_card"):
        details = render_request_details(
            reference_library=reference_library,
            customer=customer,
        )

# Company Code + Sales Org decide which rules apply
if not details.sales_org:
    render_waiting_sections(right_panel)
    st.stop()

context = RequestContext(
    request_type=details.request_type,
    customer_id=customer_id,
    customer=customer,
    company_code=details.company_code,
    sales_org=details.sales_org,
    request_comment=details.comment,
    fields=get_form_fields(
        company_code=details.company_code,
        sales_org=details.sales_org,
        rules=rules,
    ),
    rules=rules,
    credit_rules=credit_rules,
    assignment_rules=assignment_rules,
    reference_library=reference_library,
)

if details.request_type == CHANGE_CUSTOMER:
    render_change_request(right_panel, context)
else:
    render_standard_request(right_panel, context)
