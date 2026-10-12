"""Company Code, Sales & Distribution and Partner Functions sections."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from portal.constants import EXISTING_ID, NEW_ADDRESS, PARTNER_NAME_MAX_LENGTH, PARTY_GROUPS
from portal.core.rules import is_checkbox
from portal.core.utils import clean, is_yes
from portal.ui.widgets import render_rule_field, spacer

FIELDS_PER_ROW = 3


def render_section(
    *,
    section_fields: pd.DataFrame,
    company_code: str,
    sales_org: str,
    rules: dict[str, pd.DataFrame],
    context: dict[str, str],
) -> dict[str, str]:
    """Render a rules section three fields per row; hidden fields keep defaults."""
    values: dict[str, str] = {}

    if section_fields.empty:
        st.info("No active fields are configured for this section")
        return values

    def render(field: dict) -> None:
        values[clean(field.get("field_key"))] = clean(
            render_rule_field(
                field=field,
                company_code=company_code,
                sales_org=sales_org,
                rules=rules,
                context=context,
            )
        )

    visible_fields = []
    checkbox_fields = []

    for field in section_fields.to_dict("records"):
        if is_yes(field.get("hidden")):
            render(field)
        elif is_checkbox(field):
            checkbox_fields.append(field)
        else:
            visible_fields.append(field)

    # Tick boxes go on their own row(s) below the fields, above the comments
    for group in (visible_fields, checkbox_fields):
        with st.container():
            for start in range(0, len(group), FIELDS_PER_ROW):
                columns = st.columns(FIELDS_PER_ROW, gap="small", vertical_alignment="top")

                for column, field in zip(columns, group[start:start + FIELDS_PER_ROW]):
                    with column:
                        render(field)

    return values


# =============================================================================
# PARTNER FUNCTIONS
# =============================================================================


def _subheading(title: str, description: str) -> None:
    st.markdown(
        f"""
        <div style="margin-bottom:8px;">
            <div style="font-size:1rem;font-weight:600;">
                {title}
            </div>
            <div style="font-size:0.85rem;color:#6B7280;">
                {description}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _name_input(label: str, key: str, placeholder: str) -> str:
    return clean(
        st.text_input(
            label,
            key=key,
            max_chars=PARTNER_NAME_MAX_LENGTH,
            placeholder=placeholder,
        )
    )


def render_partner_functions(
    *,
    section_fields: pd.DataFrame,
    company_code: str,
    sales_org: str,
    rules: dict[str, pd.DataFrame],
    context: dict[str, str],
) -> dict[str, str]:
    values: dict[str, str] = {}

    if section_fields.empty:
        st.info("No active Partner Functions are configured for this combination")
        return values

    field_map = {
        clean(row.get("field_key")): row
        for row in section_fields.to_dict("records")
        if clean(row.get("field_key"))
    }

    def render_key(field_key: str) -> str:
        field = field_map.get(field_key)
        if not field:
            return ""

        value = clean(
            render_rule_field(
                field=field,
                company_code=company_code,
                sales_org=sales_org,
                rules=rules,
                context=context,
            )
        )
        values[field_key] = value
        return value

    def contact_group(code: str, title: str, description: str) -> None:
        """First name, surname and email of one contact person (CP / YL)."""
        _subheading(title, description)

        first_col, last_col, email_col = st.columns([1, 1, 1.25], gap="small")

        with first_col:
            first_name = _name_input(
                "First Name", f"form__partner_{code}_first_name", "Enter first name"
            )
        with last_col:
            last_name = _name_input(
                "Surname", f"form__partner_{code}_last_name", "Enter surname"
            )
        with email_col:
            render_key(f"partner_{code}_email")

        values[f"partner_{code}_first_name"] = first_name
        values[f"partner_{code}_last_name"] = last_name
        values[f"partner_{code}_name"] = clean(
            " ".join(part for part in [first_name, last_name] if part)
        )

    # Invoice contact
    st.markdown("#### Invoice Contact (YF)")

    invoice_contact_col, _ = st.columns([2, 1], gap="small")
    with invoice_contact_col:
        render_key("partner_yf_email")

    spacer(10)

    contact_group(
        "cp",
        "Sales Order Contact (CP)",
        "Person responsible for sales order-related communication",
    )

    spacer(10)

    contact_group(
        "yl",
        "Logistics Contact (YL)",
        "Person responsible for delivery and logistics-related communication",
    )

    spacer(16)

    # Internal responsibility
    st.markdown("#### Internal Responsibility")

    sales_rep_col, customer_service_col, _ = st.columns([1, 1, 1], gap="small")

    with sales_rep_col:
        render_key("partner_yb_employee_id")

    with customer_service_col:
        render_key("partner_yz_employee_id")

    spacer(16)

    # Bill-to, payer and ship-to parties
    st.markdown("#### Bill-to, Payer and Ship-to Party")

    st.markdown(
        """
        <div style="font-size:0.85rem;color:#6B7280;margin-bottom:12px;">
            The current customer ID is shown by default. If another partner is
            required, select an existing partner and enter its ID, or select a
            new partner and enter the full address to be created
        </div>
        """,
        unsafe_allow_html=True,
    )

    # One row per level (titles, modes, details) so each row lines up
    # on its own, whatever the title wrapping or selected modes.
    for column, (_label, title, *_keys) in zip(st.columns(3), PARTY_GROUPS):
        with column:
            st.markdown(f"##### {title}")

    modes: dict[str, str] = {}

    for column, (_label, _title, mode_key, *_keys) in zip(st.columns(3), PARTY_GROUPS):
        with column:
            modes[mode_key] = render_key(mode_key)

    # Skip the empty row when no party needs an ID or address
    if any(mode in {EXISTING_ID, NEW_ADDRESS} for mode in modes.values()):
        detail_columns = st.columns(3)
    else:
        detail_columns = [None] * len(PARTY_GROUPS)

    for column, (_label, _title, mode_key, id_key, address_key) in zip(
        detail_columns,
        PARTY_GROUPS,
    ):
        mode = modes[mode_key]

        if mode == EXISTING_ID:
            with column:
                render_key(id_key)
            values[address_key] = ""

        elif mode == NEW_ADDRESS:
            with column:
                render_key(address_key)
            values[id_key] = ""

        else:
            values[id_key] = ""
            values[address_key] = ""

    return values
