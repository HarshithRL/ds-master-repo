from __future__ import annotations

from typing import Any
import html

import pandas as pd
import streamlit as st
from pathlib import Path

from .data import (
    get_reference_company_codes,
    get_reference_company_label,
    get_reference_sales_orgs,
)

from .ui_common import apply_required_widget_state, render_section_comment
from .utils import clean


def render_header(
    *,
    loaded_customer_id: str,
    header_customer: dict[str, str] | None,
) -> None:
    """Render the application header."""
 
    header_customer_name = ""
 
    if header_customer:
        header_customer_name = (
            clean(header_customer.get("name_1", ""))
            or clean(header_customer.get("customer_name", ""))
            or clean(header_customer.get("name", ""))
        )
 
    if loaded_customer_id and header_customer_name:
        header_summary = f"{loaded_customer_id} · {header_customer_name}"
    elif loaded_customer_id:
        header_summary = f"Customer {loaded_customer_id}"
    else:
        header_summary = ""
 
    # =====================================================================
    # HEADER CSS
    # =====================================================================
 
    st.markdown(
        """
        <style>

        /* =============================================================
        AXIOM HEADER
        ============================================================= */
        
        .axiom-header-title {
            white-space: nowrap;
        }

        .axiom-header-description {
            white-space: nowrap;
        }

        .axiom-header-title {
            color: #182033;
            font-size: 1.45rem;
            line-height: 1.65rem;
            font-weight: 700;
            letter-spacing: -0.025em;
            margin: 0;
        }
        
        .axiom-header-description {
            color: #7B8195;
            font-size: 0.78rem;
            line-height: 1.15rem;
            font-weight: 400;
            margin-top: 0.18rem;
        }
        
        /* Small divider between AXIOM and page name */
        .axiom-brand-divider {
            width: 1px;
            height: 42px;
            margin: auto;
            background: #D8D4E6;
        }
        
        /* Current customer */
        .header-current-customer {
            text-align: right;
            margin-left: auto;
            padding: .65rem .85rem;
            border-radius: 12px;
            background: #F2F3FF;
            border: 1px solid #E4E6FF;
            width: fit-content;
            max-width: 100%;
        }
        
        .header-customer-label {
            color: #98A2B3;
            font-size: 0.60rem;
            line-height: 0.85rem;
            font-weight: 700;
            letter-spacing: 0.10em;
            margin-bottom: 0.18rem;
        }
        
        .header-customer-value {
            color: #344054;
            font-size: 0.78rem;
            line-height: 1.1rem;
            font-weight: 600;
        }
        
        /* Line underneath whole header */
        .axiom-header-bottom-line {
            width: 100%;
            height: 1px;
        
            margin-top: 0.65rem;
            margin-bottom: 1.15rem;
        
            background: linear-gradient(
                90deg,
                #7654FF 0%,
                rgba(118,84,255,0.28) 30%,
                #E9E7F0 65%,
                transparent 100%
            );
        }
        
        </style>
        """,
        unsafe_allow_html=True,
    )
 
    # =====================================================================
    # HEADER
    # =====================================================================
 
    header_container = st.container()
 
    with header_container:
 
        # One single horizontal row:
        #
        # AXIOM | Customer Master Data ........ Customer .... ETEX
 
        (
            axiom_logo_col,
            divider_col,
            title_col,
            spacer_col,
            customer_col,
            etex_logo_col,
        ) = st.columns(
            [1.6, 0.18, 2.8, 1.6, 1.7, 0.15],
            gap="small",
            vertical_alignment="center",
        )
 
        # -------------------------------------------------------------
        # AXIOM LOGO
        # -------------------------------------------------------------
 
        with axiom_logo_col:
            st.image(
                "assets/axiom_logo.svg",
                width=160,
            )
 
        # -------------------------------------------------------------
        # PAGE IDENTITY
        # -------------------------------------------------------------
 
        with title_col:
            st.markdown(
                '<div class="axiom-header-title">'
                'Customer Master Data'
                '</div>'
                '<div class="axiom-header-description">'
                'Create and manage customer master data requests.'
                '</div>',
                unsafe_allow_html=True,
            )
 
        # -------------------------------------------------------------
        # CURRENT CUSTOMER
        # -------------------------------------------------------------
 
        with customer_col:
            if loaded_customer_id:
                st.markdown(
                    f"""
                    <div class="header-current-customer">
                        <div class="header-customer-label">CURRENT CUSTOMER</div>
                        <div class="header-customer-value">{html.escape(header_summary)}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
 
        # -------------------------------------------------------------
        # ETEX LOGO
        # -------------------------------------------------------------
 
        # with etex_logo_col:
        #    st.image(
        #        "assets/etex_logo.png",
        #        width=72,
        #    )
 
        # -------------------------------------------------------------
        # BOTTOM ACCENT
        # -------------------------------------------------------------
 
        st.markdown(
            '<div class="axiom-header-bottom-line"></div>',
            unsafe_allow_html=True,
        )

def render_request_details(
    *,
    loaded_customer_id: str,
    reference_library: dict[str, pd.DataFrame],
) -> tuple[str, str, str, str]:
    """Render the left-side Request Details card."""

    st.markdown(
        """
        <div class="panel-card-title">
            <span>Request Details</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ---------------------------------------------------------------------
    # REQUEST TYPE: separate full-width row inside the existing left panel.
    # SVG images are rendered directly, not as CSS backgrounds on buttons.
    # ---------------------------------------------------------------------
    st.markdown('<div class="axiom-request-label">Request Type <span>*</span></div>', unsafe_allow_html=True)
    choices = (("Create Customer", "create"), ("Change Customer", "change"), ("Extend Customer", "extend"))
    if st.session_state.get("request__type") not in [item[0] for item in choices]:
        st.session_state["request__type"] = "Create Customer"
    request_type = st.session_state["request__type"]
    # Render real SVG assets, independent of Streamlit's generated CSS classes.
    # Callbacks update state before the next normal Streamlit script pass.
    def _select_request_type(value: str) -> None:
        st.session_state["request__type"] = value

    for column, (label, slug) in zip(st.columns(3, gap="small"), choices):
        with column:
            st.button(
                label.split()[0],
                key=f"axiom_request_card_{slug}",
                type="primary" if request_type == label else "secondary",
                use_container_width=True,
                help=label,
                on_click=_select_request_type,
                args=(label,),
            )
    apply_required_widget_state(widget_key="request__type", value=request_type, required=True)

    # Customer ID is on its own row, before company code and sales organization.
    st.text_input("Customer ID *", value=loaded_customer_id, disabled=True,
                  key="request__customer_id")
    apply_required_widget_state(widget_key="request__customer_id",
                                value=loaded_customer_id, required=True)

    # ---------------------------------------------------------------------
    # COMPANY CODE / SALES ORGANIZATION
    # ---------------------------------------------------------------------

    company_sales_cols = st.columns(
        [1, 1],
        gap="small",
    )

    company_code_options = get_reference_company_codes(
        reference_library
    )

    # Company Code
    with company_sales_cols[0]:
        company_code = st.selectbox(
            "Company Code *",
            options=[""] + company_code_options,
            key="request__company_code",
            format_func=lambda code: (
                ""
                if not code
                else get_reference_company_label(
                    code,
                    reference_library,
                )
            ),
        )

        apply_required_widget_state(
            widget_key="request__company_code",
            value=company_code,
            required=True,
        )

    # Get Sales Organizations belonging to selected Company Code.
    #
    # This already supports multiple Sales Organizations for one
    # Company Code because every matching row is returned.
    sales_org_options = (
        get_reference_sales_orgs(
            company_code,
            reference_library,
        )
        if company_code
        else []
    )

    # Sales Organization
    with company_sales_cols[1]:
        selected_sales_org = st.selectbox(
            "Sales Organization *",
            options=[""] + sales_org_options,
            key="request__sales_org",
            disabled=not bool(company_code),
            help=(
                "Choose the Sales Organization "
                "for the selected Company Code."
            ),
        )

        apply_required_widget_state(
            widget_key="request__sales_org",
            value=selected_sales_org,
            required=True,
        )

    # ---------------------------------------------------------------------
    # RESET DEPENDENT FORM STATE WHEN CONTEXT CHANGES
    # ---------------------------------------------------------------------

    rule_context_signature = (
        f"{request_type}|{company_code}|{selected_sales_org}"
    )

    previous_rule_context = st.session_state.get(
        "_rule_context_signature"
    )

    if previous_rule_context != rule_context_signature:
        for key in list(st.session_state.keys()):
            if (
                key.startswith("form__")
                or key.startswith("computed_display__")
                or key.startswith("credit__")
                or key.startswith("section_comment__company_code")
                or key.startswith("section_comment__sales_distribution")
                or key.startswith("section_comment__partner_functions")
                or key.startswith("section_comment__credit_management")
            ):
                del st.session_state[key]

        st.session_state["_rule_context_signature"] = (
            rule_context_signature
        )

    # ---------------------------------------------------------------------
    # REQUEST COMMENT
    # ---------------------------------------------------------------------

    request_information_comment = render_section_comment(
        "request_information"
    )

    return (
        request_type,
        company_code,
        selected_sales_org,
        request_information_comment,
    )