from __future__ import annotations

from typing import Any
import html

import pandas as pd
import streamlit as st

from .utils import active_rows, clean


def apply_required_widget_state(
    *,
    widget_key: str,
    value: Any,
    required: bool,
) -> None:
    """Change the actual widget border based on required-field status."""
    if not required:
        return

    complete = bool(clean(value))

    submit_attempted = bool(
        st.session_state.get(
            "_submit_attempted",
            False,
        )
    )

    if complete:
        border_color = "#5C9461"  # green
        focus_color = "rgba(92, 148, 97, 0.18)"

    elif submit_attempted:
        border_color = "#C62828"  # red
        focus_color = "rgba(198, 40, 40, 0.16)"

    else:
        border_color = "#D9A441"  # yellow
        focus_color = "rgba(217, 164, 65, 0.16)"

    st.markdown(
        f"""
        <style>
        .st-key-{widget_key} div[data-baseweb="input"] > div,
        .st-key-{widget_key} div[data-baseweb="select"] > div,
        .st-key-{widget_key} textarea {{
            border: 1.5px solid {border_color} !important;
            box-shadow: none !important;
            transition:
                border-color 0.15s ease,
                box-shadow 0.15s ease;
        }}

        .st-key-{widget_key} div[data-baseweb="input"]:focus-within > div,
        .st-key-{widget_key} div[data-baseweb="select"]:focus-within > div,
        .st-key-{widget_key} textarea:focus {{
            border-color: {border_color} !important;
            box-shadow: 0 0 0 2px {focus_color} !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_customer_information(
    customer: dict[str, str],
    reference_library: dict[str, pd.DataFrame],
) -> None:
    display_fields = active_rows(
        reference_library["general_data_fields"]
    ).copy()

    rows: list[tuple[str, str]] = []

    for _, config in display_fields.iterrows():
        field_key = clean(config.get("field_key"))
        label = clean(config.get("label")) or field_key

        if not field_key:
            continue

        value = clean(customer.get(field_key))

        rows.append(
            (
                label,
                value,
            )
        )

    if not rows:
        st.info("No active customer display fields are configured.")
        return

    items = []

    for label, value in rows:
        items.append(
            '<div class="customer-card-item">'
            f'<span class="customer-card-label">{html.escape(str(label))}</span>'
            f'<span class="customer-card-value">{html.escape(str(value or "—"))}</span>'
            "</div>"
        )

    st.markdown(
        """
        <div class="customer-card">
            <div class="customer-card-title">
                <span>Existing Customer Information</span>
            </div>
            <div class="customer-card-grid axiom-customer-grid">
        """
        + "".join(items)
        + """
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_section_comment(section_key: str) -> str:
    st.markdown("**Comments / additional instructions**")
    return clean(
        st.text_area(
            "Comments / additional instructions",
            key=f"section_comment__{section_key}",
            height=70,
            label_visibility="collapsed",
            placeholder="Optional comments for Master Data...",
        )
    )
