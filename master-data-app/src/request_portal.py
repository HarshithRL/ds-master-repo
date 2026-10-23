"""AXIOM customer request portal page: page setup and top-level flow."""

from __future__ import annotations

import streamlit as st

from portal.config import DEMO_MODE, PAGE_ICON_FILE
from portal.constants import CHANGE_CUSTOMER
from portal.core.customers import test_customer_rows
from portal.core.identity import is_master_data_member, requester_email
from portal.core.loaders import (
    load_assignment_rules,
    load_credit_rules,
    load_customer_database,
    load_form_rules,
    load_reference_library,
)
from portal.core.rules import fields_for_request, get_form_fields
from portal.core.utils import clean
from portal.integrations.customer_lookup import find_customer
from portal.integrations.sap_business_partner import SapError
from portal.ui.customer_card import render_customer_information
from portal.ui.layout import (
    environment_label,
    render_environment_banner,
    render_header,
    render_request_details,
    render_welcome,
)
from portal.ui.pages import (
    RequestContext,
    render_change_request,
    render_standard_request,
    render_waiting_sections,
)
from portal.ui.sidebar import render_sidebar
from portal.ui.test_customers import render_test_customers
from portal.ui.state import loaded_customer_id
from portal.ui.theme import apply_theme

# =========================================================================
# PAGE
# =========================================================================

st.set_page_config(
    page_title=f"AXIOM {environment_label()} | Master Data Management".replace("  ", " "),
    page_icon=PAGE_ICON_FILE,
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_theme()
render_environment_banner()

try:
    db = load_customer_database()
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
except SapError as exc:
    st.error(f"The customer could not be read from SAP. {exc}")
    st.stop()
except Exception as exc:
    st.error("Customer search failed")
    st.exception(exc)
    st.stop()

# Test customers are listed in the demo only
test_customers = test_customer_rows(db, reference_library) if DEMO_MODE else []

render_sidebar(
    customer=customer,
    reference_library=reference_library,
    test_customers=test_customers,
)

render_header(
    loaded_customer_id=customer_id,
    header_customer=customer,
    show_workbench_link=is_master_data_member(requester_email(st.context.headers), assignment_rules),
)

if not customer_id:
    render_welcome()
    if test_customers:
        render_test_customers(test_customers)
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

# From SAP, company-code and sales-area values follow the chosen scope
if not DEMO_MODE and details.company_code:
    try:
        customer = find_customer(
            customer_id,
            reference_library,
            st.context.headers,
            company_code=details.company_code,
            sales_org=details.sales_org,
        ) or customer
    except SapError as exc:
        st.error(f"The customer could not be read from SAP. {exc}")
        st.stop()

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
    fields=fields_for_request(
        get_form_fields(
            company_code=details.company_code,
            sales_org=details.sales_org,
            rules=rules,
        ),
        details.request_type,
        clean(customer.get("country")),
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
