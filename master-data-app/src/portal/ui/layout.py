"""Page header and the left-side Request Details card."""

from __future__ import annotations

import html
from dataclasses import dataclass

import pandas as pd
import streamlit as st

from portal.config import HEADER_LOGO_FILE
from portal.constants import CREATE_CUSTOMER, REQUEST_TYPE_LABELS, REQUEST_TYPES
from portal.core.customers import customer_company_code, customer_display_name
from portal.core.rules import (
    get_reference_company_codes,
    get_reference_company_label,
    get_reference_sales_orgs,
)
from portal.ui.state import reset_when_rule_context_changes
from portal.ui.widgets import apply_field_state, render_section_comment

# =============================================================================
# HEADER
# =============================================================================


def render_header(
    *,
    loaded_customer_id: str,
    header_customer: dict[str, str] | None,
) -> None:
    """Logo on the left, the loaded customer on the right."""
    header_customer_name = customer_display_name(header_customer)

    if loaded_customer_id and header_customer_name:
        header_summary = f"{loaded_customer_id} · {header_customer_name}"
    elif loaded_customer_id:
        header_summary = f"Customer {loaded_customer_id}"
    else:
        header_summary = ""

    with st.container(key="axiom_main_header"):
        axiom_logo_col, customer_col = st.columns(
            [3, 2],
            gap="medium",
            vertical_alignment="center",
        )

        with axiom_logo_col:
            st.image(HEADER_LOGO_FILE, width=165)

        with customer_col:
            if loaded_customer_id:
                st.markdown(
                    f"""
                    <div class="header-current-customer">
                        <div class="header-customer-label">
                            CURRENT CUSTOMER
                        </div>
                        <div class="header-customer-value">
                            {html.escape(header_summary)}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )


# =============================================================================
# WELCOME (no customer loaded yet)
# =============================================================================

WELCOME_STEPS = [
    ("1", "Find the customer", "Search by SAP ID, name or VAT number in the sidebar."),
    ("2", "Choose the request", "Create, Extend or Change, plus the Sales Organization."),
    ("3", "Fill in and submit", "Complete the sections. You receive a reference and a confirmation email."),
]


def render_welcome() -> None:
    steps = "".join(
        f"""
        <div class="welcome-step">
            <div class="welcome-step-number">{number}</div>
            <div class="welcome-step-title">{title}</div>
            <div class="welcome-step-text">{text}</div>
        </div>
        """
        for number, title, text in WELCOME_STEPS
    )

    st.markdown(
        f"""
        <div class="welcome-card">
            <div class="header-eyebrow">CUSTOMER REQUEST PORTAL</div>
            <div class="welcome-title">Start a customer master data request</div>
            <div class="welcome-text">Requests go to the Master Data team, who
            process them in SAP. Start by searching for the customer in the sidebar.</div>
            <div class="welcome-steps">{steps}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# =============================================================================
# REQUEST DETAILS
# =============================================================================


@dataclass(frozen=True)
class RequestDetails:
    request_type: str
    company_code: str
    sales_org: str
    comment: str


def render_request_details(
    *,
    reference_library: dict[str, pd.DataFrame],
    customer: dict[str, str] | None = None,
) -> RequestDetails:
    """Request type, Company Code, Sales Organization and a comment."""
    st.markdown(
        """
        <div class="panel-card-title">
            <span>Request Details</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.session_state.get("request__type") not in REQUEST_TYPES:
        st.session_state["request__type"] = CREATE_CUSTOMER

    request_type = st.segmented_control(
        "Request Type",
        options=REQUEST_TYPES,
        format_func=REQUEST_TYPE_LABELS.__getitem__,
        key="request__type",
        label_visibility="collapsed",
        selection_mode="single",
        width="stretch",
    )

    # Create: the customer already belongs to a Company Code (SAP), so it is
    # read from the customer record and only the Sales Organization is picked
    card_company_code = (
        customer_company_code(customer) if request_type == CREATE_CUSTOMER else ""
    )
    company_options = [""] + get_reference_company_codes(reference_library)

    if card_company_code:
        if card_company_code not in company_options:
            company_options.append(card_company_code)
        st.session_state["request__company_code"] = card_company_code

    company_col, sales_org_col = st.columns([1, 1], gap="small")

    with company_col:
        company_code = st.selectbox(
            "Company Code",
            options=company_options,
            key="request__company_code",
            format_func=lambda code: (
                "" if not code else get_reference_company_label(code, reference_library)
            ),
            disabled=bool(card_company_code),
            help=(
                "Read from the customer record. A new customer is always created "
                "in the Company Code it belongs to."
                if card_company_code
                else None
            ),
        )
        if not card_company_code:
            apply_field_state(
                widget_key="request__company_code",
                value=company_code,
                required=True,
            )

    # One Company Code can have several Sales Organizations
    sales_org_options = (
        get_reference_sales_orgs(company_code, reference_library) if company_code else []
    )

    if st.session_state.get("request__sales_org") not in [""] + sales_org_options:
        st.session_state["request__sales_org"] = ""

    with sales_org_col:
        sales_org = st.selectbox(
            "Sales Organization",
            options=[""] + sales_org_options,
            key="request__sales_org",
            disabled=not bool(company_code),
            help="Choose the Sales Organization for the selected Company Code.",
        )
        apply_field_state(
            widget_key="request__sales_org",
            value=sales_org,
            required=True,
        )

    if request_type == CREATE_CUSTOMER and not card_company_code:
        st.caption("This customer has no Company Code in SAP. Choose one.")
    elif company_code and not sales_org_options:
        st.warning(
            f"Company Code {company_code} is not set up in the portal yet "
            "(general_data.xlsx › Company_Sales_Org). Contact the Master Data team."
        )

    reset_when_rule_context_changes(f"{request_type}|{company_code}|{sales_org}")

    return RequestDetails(
        request_type=request_type,
        company_code=company_code,
        sales_org=sales_org,
        comment=render_section_comment("request_information"),
    )
