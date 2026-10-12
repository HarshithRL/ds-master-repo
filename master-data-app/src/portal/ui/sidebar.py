"""Sidebar: customer search, current and recent customers, my requests, help."""

from __future__ import annotations

import html
from typing import Any

import pandas as pd
import streamlit as st

from portal.config import DEMO_MODE, USER_GUIDE_FILE
from portal.core.identity import requester_email, requester_user
from portal.core.storage import demo_requests_for
from portal.core.utils import clean, normalize_customer_id
from portal.integrations.customer_lookup import search_customers_anywhere
from portal.integrations.workbench import list_my_requests
from portal.ui.state import (
    LOADED_CUSTOMER_KEY,
    RECENT_CUSTOMERS_KEY,
    SEARCH_INPUT_KEY,
    SEARCH_MESSAGE_KEY,
    SEARCH_RESULTS_KEY,
    SESSION_REQUESTS_KEY,
    reset_form_state,
)

# Background gradient, decorative sweeps, titles and collapse button
SIDEBAR_CSS = """
        <style>

        /* =============================================================
        AXIOM SIDEBAR
        ============================================================= */

        section[data-testid="stSidebar"] {
            background:
                radial-gradient(
                    circle at 10% 82%,
                    rgba(111, 76, 255, 0.28) 0%,
                    rgba(111, 76, 255, 0.10) 24%,
                    transparent 48%
                ),
                linear-gradient(
                    180deg,
                    #202747 0%,
                    #252653 52%,
                    #29235C 100%
                ) !important;

            border-right: 1px solid rgba(255,255,255,0.06) !important;
        }

        section[data-testid="stSidebar"] > div {
            background: transparent !important;
        }

        section[data-testid="stSidebar"]
        [data-testid="stSidebarContent"] {
            background: transparent !important;
            overflow-y: auto !important;
            overflow-x: hidden !important;
        }

        /* =============================================================
        AXIOM DECORATIVE SIDEBAR ACCENT
        ============================================================= */
        
        section[data-testid="stSidebar"] {
            position: relative !important;
        }
        
        /* Soft purple sweep at bottom */
        section[data-testid="stSidebar"]::before {
            content: "";
            position: absolute;
        
            left: -110px;
            bottom: -115px;
        
            width: 360px;
            height: 300px;
        
            background: linear-gradient(
                135deg,
                rgba(112, 76, 255, 0.00) 15%,
                rgba(112, 76, 255, 0.12) 48%,
                rgba(112, 76, 255, 0.38) 100%
            );
        
            border-radius: 50% 50% 0 0;
        
            transform: rotate(27deg);
        
            pointer-events: none;
            z-index: 0;
        }
        
        /* Smaller secondary sweep */
        section[data-testid="stSidebar"]::after {
            content: "";
            position: absolute;
        
            left: -150px;
            bottom: -175px;
        
            width: 390px;
            height: 310px;
        
            background: linear-gradient(
                135deg,
                transparent 30%,
                rgba(139, 104, 250, 0.18) 70%,
                rgba(99, 45, 250, 0.30) 100%
            );
        
            border-radius: 50% 50% 0 0;
        
            transform: rotate(42deg);
        
            pointer-events: none;
            z-index: 0;
        }
        
        /* Keep actual sidebar widgets above decoration */
        section[data-testid="stSidebar"]
        [data-testid="stSidebarContent"] {
            position: relative !important;
            z-index: 1 !important;
        }
        /* =============================================================
        SIDEBAR CONTENT
        ============================================================= */

        section[data-testid="stSidebar"] .block-container {
            box-sizing: border-box !important;
            width: 100% !important;
            max-width: none !important;
            min-height: 0 !important;

            padding-top: 1.6rem !important;
            padding-left: 1.15rem !important;
            padding-right: 1.15rem !important;
            padding-bottom: 1rem !important;

            margin: 0 !important;
        }

        /* =============================================================
        CUSTOMER SEARCH TITLE
        ============================================================= */

        .sidebar-search-title {
            margin: 0 0 0.8rem 0;

            color: #B9B8D5;

            font-size: 0.67rem;
            line-height: 0.9rem;
            font-weight: 700;

            letter-spacing: 0.11em;
        }


        /* =============================================================
        FIELD LABEL
        ============================================================= */

        .sidebar-field-label {
            margin: 0 0 0.45rem 0;

            color: #F5F4FC;

            font-size: 0.80rem;
            line-height: 1rem;
            font-weight: 600;
        }

        section[data-testid="stSidebar"]
        [data-testid="stWidgetLabel"] p {
            color: #F5F4FC !important;
            font-size: 0.80rem !important;
            font-weight: 600 !important;
        }


        /* =============================================================
        SAP CUSTOMER ID INPUT
        ============================================================= */

        section[data-testid="stSidebar"]
        div[data-baseweb="base-input"] {
            background: rgba(255,255,255,0.075) !important;

            border: 1px solid rgba(189,174,255,0.28) !important;
            border-radius: 8px !important;

            overflow: hidden !important;
            box-shadow: none !important;

            transition:
                border-color 0.15s ease,
                background 0.15s ease,
                box-shadow 0.15s ease;
        }

        section[data-testid="stSidebar"]
        div[data-baseweb="base-input"]:hover {
            background: rgba(255,255,255,0.10) !important;
            border-color: rgba(189,174,255,0.55) !important;
        }

        section[data-testid="stSidebar"]
        div[data-baseweb="input"]:focus-within
        div[data-baseweb="base-input"] {
            background: rgba(255,255,255,0.11) !important;

            border-color: #8D6CFF !important;

            box-shadow:
                0 0 0 2px rgba(141,108,255,0.18) !important;
        }

        section[data-testid="stSidebar"] input {
            color: #182033 !important;
            -webkit-text-fill-color: #182033 !important;
            caret-color: #663BFF !important;
            background: transparent !important;
        }

        section[data-testid="stSidebar"] input::placeholder {
            color: #AAAAC3 !important;
            opacity: 1 !important;
        }

        /* =============================================================
        CUSTOMER FORM NAVIGATION
        ============================================================= */

        .sidebar-menu-spacing {
            height: 1.5rem;
        }

        .sidebar-customer-form {
            box-sizing: border-box;

            display: flex;
            align-items: center;

            width: 100%;
            min-height: 48px;

            gap: 10px;
            padding: 8px 10px;

            color: #FFFFFF;

            background: rgba(119,82,255,0.20);

            border-left: 3px solid #8B68FA;
            border-radius: 8px;
        }

        .sidebar-form-label {
            color: #FFFFFF;

            font-size: 14px;
            line-height: 20px;
            font-weight: 600;

            white-space: nowrap;
        }


        /* =============================================================
        AXIOM LOADING BAR
        ============================================================= */

        .axiom-loading-track {
            width: 100%;
            height: 3px;

            margin-top: 6px;

            overflow: hidden;
            border-radius: 999px;

            background: rgba(255,255,255,0.12);
        }

        .axiom-loading-bar {
            width: 35%;
            height: 100%;

            border-radius: 999px;

            background: #8B68FA;

            animation: axiom-loading 1s ease-in-out infinite;
        }

        @keyframes axiom-loading {
            0% {
                transform: translateX(-120%);
            }

            100% {
                transform: translateX(320%);
            }
        }


        /* =============================================================
        SIDEBAR COLLAPSE BUTTON
        ============================================================= */

        section[data-testid="stSidebar"]
        [data-testid="stSidebarCollapseButton"] {
            color: #C8C5DB !important;
        }

        section[data-testid="stSidebar"]
        [data-testid="stSidebarCollapseButton"] svg {
            fill: #C8C5DB !important;
        }

        </style>
        """

# Search box, cards and lists (the base CSS above handles background and titles)
SIDEBAR_EXTRA_CSS = """
<style>
section[data-testid="stSidebar"] [data-testid="stTextInputRootElement"] {
    background: #FFFFFF !important;
    border: 1px solid rgba(189,174,255,0.45) !important;
    border-radius: 8px !important;
    min-height: 40px !important;
}

section[data-testid="stSidebar"] [data-testid="stTextInputRootElement"]:focus-within {
    border-color: #8D6CFF !important;
    box-shadow: 0 0 0 2px rgba(141,108,255,0.35) !important;
}

section[data-testid="stSidebar"] [data-testid="stTextInputRootElement"] input {
    background: transparent !important;
    border: 0 !important;
    padding-left: 12px !important;
}

section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
    gap: 0.45rem !important;
}

section[data-testid="stSidebar"] [data-testid="stElementContainer"]:has(> [data-testid="stMarkdown"] style):not(
    :has([data-testid="stMarkdownContainer"] > :not(style))
) {
    display: none !important;
}

section[data-testid="stSidebar"] button {
    min-height: 0 !important;
    padding: 0.42rem 0.7rem !important;
    background: rgba(255,255,255,0.07) !important;
    border: 1px solid rgba(189,174,255,0.28) !important;
    border-radius: 8px !important;
    justify-content: flex-start !important;
    text-align: left !important;
}

section[data-testid="stSidebar"] button > div,
section[data-testid="stSidebar"] button [data-testid="stMarkdownContainer"] {
    width: 100% !important;
    justify-content: flex-start !important;
    text-align: left !important;
}

section[data-testid="stSidebar"] button:hover {
    background: rgba(119,82,255,0.30) !important;
    border-color: #8B68FA !important;
}

section[data-testid="stSidebar"] button p,
section[data-testid="stSidebar"] button span {
    color: #F5F4FC !important;
    font-size: 0.78rem !important;
    line-height: 1.1rem !important;
    text-align: left !important;
}

section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {
    margin-bottom: 0 !important;
}

section[data-testid="stSidebar"] {
    overflow: hidden !important;
}

.sidebar-section {
    padding: 0.75rem 0 0 0;
    margin: 0;
    color: #B9B8D5;
    font-size: 0.64rem;
    line-height: 0.9rem;
    font-weight: 700;
    letter-spacing: 0.11em;
}

.sidebar-hint {
    color: #AAAAC3;
    font-size: 0.72rem;
    line-height: 1.05rem;
}

.sidebar-hint b { color: #F5F4FC; }

.sidebar-card {
    background: rgba(119,82,255,0.20);
    border-left: 3px solid #8B68FA;
    border-radius: 8px;
    padding: 0.6rem 0.7rem;
}

.sidebar-card-label {
    color: #B9B8D5;
    font-size: 0.6rem;
    font-weight: 700;
    letter-spacing: 0.1em;
}

.sidebar-card-title {
    color: #FFFFFF;
    font-size: 0.86rem;
    font-weight: 700;
    line-height: 1.15rem;
    margin-top: 0.1rem;
    overflow-wrap: anywhere;
}

.sidebar-card-meta {
    color: #D5D2EC;
    font-size: 0.72rem;
    margin-top: 0.1rem;
}

.sidebar-request {
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(189,174,255,0.18);
    border-radius: 8px;
    padding: 0.5rem 0.6rem;
}

.sidebar-request-id {
    color: #FFFFFF;
    font-size: 0.72rem;
    font-weight: 700;
    font-family: Consolas, monospace;
}

.sidebar-request-meta {
    color: #C9C6E2;
    font-size: 0.7rem;
    line-height: 1rem;
    margin-top: 0.1rem;
    overflow-wrap: anywhere;
}

.sidebar-status {
    display: inline-block;
    margin-top: 0.25rem;
    padding: 0.05rem 0.45rem;
    border-radius: 999px;
    background: rgba(255,255,255,0.14);
    color: #FFFFFF;
    font-size: 0.64rem;
    font-weight: 650;
}

/* More specific than the main panel's expander and status colours */
section[data-testid="stSidebar"] div[data-testid="stExpander"] {
    background: rgba(255,255,255,0.05) !important;
    border: 1px solid rgba(189,174,255,0.22) !important;
    border-radius: 10px !important;
    box-shadow: none !important;
}

section[data-testid="stSidebar"] div[data-testid="stExpander"] details > summary,
section[data-testid="stSidebar"] div[data-testid="stExpander"] div[data-testid="stExpanderDetails"] {
    background: transparent !important;
    border-bottom-color: rgba(189,174,255,0.18) !important;
}

section[data-testid="stSidebar"] [data-testid="stExpander"] p,
section[data-testid="stSidebar"] [data-testid="stExpander"] li,
section[data-testid="stSidebar"] [data-testid="stExpander"] span {
    color: #E7E5F5 !important;
    font-size: 0.76rem !important;
    line-height: 1.15rem !important;
}

section[data-testid="stSidebar"] [data-testid="stExpander"] svg {
    color: #C8C5DB !important;
    fill: #C8C5DB !important;
}
</style>
"""

DEMO_STATUS = "Submitted"
MY_REQUESTS_SLOT_KEY = "_sidebar_my_requests_slot"
MAX_RECENT = 5


# =============================================================================
# ACTIONS (button / Enter callbacks)
# =============================================================================


def load_customer(customer_id: str) -> None:
    """Open a customer: clear the form and the search."""
    st.session_state[LOADED_CUSTOMER_KEY] = customer_id
    st.session_state.pop(SEARCH_RESULTS_KEY, None)
    st.session_state.pop(SEARCH_MESSAGE_KEY, None)
    st.session_state[SEARCH_INPUT_KEY] = ""
    reset_form_state()


def _clear_customer() -> None:
    st.session_state.pop(LOADED_CUSTOMER_KEY, None)
    reset_form_state()


def _run_search(reference_library: dict[str, pd.DataFrame]) -> None:
    """One match (or an exact SAP ID) opens the customer; several are listed."""
    query = clean(st.session_state.get(SEARCH_INPUT_KEY))
    st.session_state.pop(SEARCH_RESULTS_KEY, None)
    st.session_state.pop(SEARCH_MESSAGE_KEY, None)

    if not query:
        return

    try:
        matches = search_customers_anywhere(query, reference_library, st.context.headers)
    except Exception as exc:
        st.session_state[SEARCH_MESSAGE_KEY] = f"Customer search failed: {exc}"
        return

    exact = [
        match
        for match in matches
        if normalize_customer_id(match.get("customer_id")) == normalize_customer_id(query)
    ]

    if len(exact) == 1 or len(matches) == 1:
        load_customer(clean((exact or matches)[0].get("customer_id")))
    elif matches:
        st.session_state[SEARCH_RESULTS_KEY] = matches
    else:
        st.session_state[SEARCH_MESSAGE_KEY] = f"No customer matches “{query}”."


def _remember(customer: dict[str, str]) -> None:
    entry = {key: clean(customer.get(key)) for key in ("customer_id", "name_1", "city", "country")}
    recent = [
        item
        for item in st.session_state.get(RECENT_CUSTOMERS_KEY, [])
        if item["customer_id"] != entry["customer_id"]
    ]
    st.session_state[RECENT_CUSTOMERS_KEY] = [entry, *recent][: MAX_RECENT + 1]


# =============================================================================
# DATA FOR THE PANELS
# =============================================================================


def my_requests(request_headers) -> tuple[list[dict[str, Any]], str]:
    """(requests, note) for the My requests panel."""
    email = requester_email(request_headers)
    session_only = list(reversed(st.session_state.get(SESSION_REQUESTS_KEY, [])))

    if DEMO_MODE:
        if email:
            return demo_requests_for(email), ""
        return session_only, "Showing this session only (no requester email is known)."

    try:
        return list_my_requests(email or requester_user(request_headers), request_headers), ""
    except Exception:
        return session_only, "Status is unavailable right now; showing this session only."


def _place(customer: dict[str, str]) -> str:
    return ", ".join(part for part in (clean(customer.get("city")), clean(customer.get("country"))) if part)


def _customer_label(customer: dict[str, str]) -> str:
    label = f"{clean(customer.get('name_1')) or 'Unnamed customer'} · {clean(customer.get('customer_id'))}"
    return f"{label} · {_place(customer)}" if _place(customer) else label


def _section(title: str) -> None:
    st.markdown(f'<div class="sidebar-section">{title}</div>', unsafe_allow_html=True)


def _hint(text_html: str) -> None:
    st.markdown(f'<div class="sidebar-hint">{text_html}</div>', unsafe_allow_html=True)


# =============================================================================
# SIDEBAR
# =============================================================================


def render_sidebar(
    *,
    customer: dict[str, str] | None,
    reference_library: dict[str, pd.DataFrame],
) -> None:
    st.markdown(SIDEBAR_CSS, unsafe_allow_html=True)
    st.markdown(SIDEBAR_EXTRA_CSS, unsafe_allow_html=True)

    headers = st.context.headers

    if customer:
        _remember(customer)

    with st.sidebar:
        _render_search(reference_library)

        if customer:
            _render_current_customer(customer)

        _render_recent(clean(customer.get("customer_id")) if customer else "")
        st.session_state[MY_REQUESTS_SLOT_KEY] = st.empty()
        refresh_my_requests()

        _section("HELP")
        _render_help(headers)


def _render_search(reference_library: dict[str, pd.DataFrame]) -> None:
    st.markdown('<div class="sidebar-search-title">CUSTOMER SEARCH</div>', unsafe_allow_html=True)

    st.text_input(
        "Search customer",
        key=SEARCH_INPUT_KEY,
        placeholder="SAP ID, name or VAT number",
        label_visibility="collapsed",
        on_change=_run_search,
        args=(reference_library,),
    )

    message = st.session_state.get(SEARCH_MESSAGE_KEY)
    _hint(html.escape(message) if message else "Type and press <b>Enter</b>.")

    results = st.session_state.get(SEARCH_RESULTS_KEY) or []
    if results:
        _section(f"{len(results)} MATCHES — CHOOSE ONE")
        for match in results:
            st.button(
                _customer_label(match),
                key=f"sidebar__match__{match.get('customer_id')}",
                on_click=load_customer,
                args=(clean(match.get("customer_id")),),
                use_container_width=True,
            )


def _render_current_customer(customer: dict[str, str]) -> None:
    _section("CURRENT CUSTOMER")
    st.markdown(
        f"""
        <div class="sidebar-card">
            <div class="sidebar-card-label">SAP {html.escape(clean(customer.get("customer_id")))}</div>
            <div class="sidebar-card-title">{html.escape(clean(customer.get("name_1")) or "Unnamed customer")}</div>
            <div class="sidebar-card-meta">{html.escape(_place(customer))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.button(
        "✕  Clear customer",
        key="sidebar__clear",
        on_click=_clear_customer,
        use_container_width=True,
    )


def _render_recent(current_id: str) -> None:
    recent = [
        item
        for item in st.session_state.get(RECENT_CUSTOMERS_KEY, [])
        if item["customer_id"] != current_id
    ][:MAX_RECENT]

    if not recent:
        return

    _section("RECENT CUSTOMERS")
    for item in recent:
        st.button(
            _customer_label(item),
            key=f"sidebar__recent__{item['customer_id']}",
            on_click=load_customer,
            args=(item["customer_id"],),
            use_container_width=True,
        )


def refresh_my_requests() -> None:
    """(Re)draw My requests, e.g. right after a submit in the same run."""
    slot = st.session_state.get(MY_REQUESTS_SLOT_KEY)
    if slot is None:
        return

    with slot.container():
        _render_my_requests(st.context.headers)


def _render_my_requests(headers) -> None:
    requests_list, note = my_requests(headers)
    _section("MY REQUESTS")

    if not requests_list:
        _hint("Requests you submit appear here with their reference.")

    for item in requests_list[:5]:
        st.markdown(
            f"""
            <div class="sidebar-request">
                <div class="sidebar-request-id">{html.escape(item.get("request_id", ""))}</div>
                <div class="sidebar-request-meta">{html.escape(item.get("request_type", ""))} ·
                {html.escape(item.get("customer_name") or item.get("customer_id", ""))}<br>
                {html.escape(item.get("requested_at", ""))}</div>
                <span class="sidebar-status">{html.escape(item.get("status") or DEMO_STATUS)}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if note:
        _hint(html.escape(note))


def _render_help(headers) -> None:
    with st.expander("How it works", expanded=False):
        st.markdown(
            "1. Search the customer and open it.\n"
            "2. In **Request Details** choose the request type and the Sales "
            "Organization. For Create the Company Code comes from the customer; "
            "for Extend and Change you choose it.\n"
            "3. Fill in the sections on the right. Fields marked * are "
            "required; a red border means still empty.\n"
            "4. Press **Submit to Master Data**. You get a request reference "
            "and a confirmation email; the Master Data team is notified."
        )
        st.markdown(
            "**Create**: set the customer up in a Sales Org of its own Company Code.  \n"
            "**Extend**: existing customer into another sales area.  \n"
            "**Change**: pick only the fields to change and enter the new values."
        )

    email = requester_email(headers)
    if email:
        _hint(f"Confirmation emails go to <b>{html.escape(email)}</b>.")
    else:
        _hint("No email address is known for you, so no confirmation email can be sent.")

    if USER_GUIDE_FILE.exists():
        st.download_button(
            "⤓  User guide (PDF)",
            data=USER_GUIDE_FILE.read_bytes(),
            file_name="AXIOM_Customer_Request_Portal_User_Guide.pdf",
            mime="application/pdf",
            key="sidebar__guide",
            use_container_width=True,
        )
