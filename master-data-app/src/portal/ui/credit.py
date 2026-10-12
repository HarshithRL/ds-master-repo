"""Credit Management section."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from portal.core.credit import (
    finalize_credit_values,
    get_credit_fields,
    get_credit_initial_value,
    get_credit_mapping,
    plan_credit_form,
)
from portal.core.utils import clean, is_yes
from portal.core.validation import is_email_field
from portal.ui.widgets import EMAIL_HELP, EMAIL_PLACEHOLDER, apply_field_state

# (heading, caption, column widths, [(field_key, placeholder) or None per column])
# Fields missing from the rules leave their column empty.
CREDIT_LAYOUT = [
    (
        "Collection Contact",
        "Person or department responsible for collection-related enquiries "
        "and outstanding invoices",
        [1, 1.25, 0.85],
        [
            ("collection_contact_name", "Enter name"),
            ("collection_contact_email", EMAIL_PLACEHOLDER),
            ("collection_contact_phone", "Enter phone"),
        ],
    ),
    (
        "Requested Credit Limit",
        None,
        [1, 1, 1],
        [("credit_limit", "Enter amount"), ("credit_currency", "Enter currency"), None],
    ),
    (
        "Credit Responsibility",
        None,
        [1, 1, 1],
        [("credit_controller", None), ("collection_specialist", None), ("credit_analyst", None)],
    ),
    (
        None,
        None,
        [1, 1, 1],
        [("accounting_clerk", None), ("accounting_clerk_phone", None), ("accounting_clerk_email", None)],
    ),
    (
        "Credit & Dunning Configuration",
        None,
        [1, 1, 1],
        [("dunning_procedure", None), ("dunning_clerk", None), ("risk_class", None)],
    ),
    (
        None,
        None,
        [1, 1, 1],
        [("check_rule", None), ("mig_rule", None), None],
    ),
]


def render_credit_management(
    *,
    company_code: str,
    sales_org: str,
    customer: dict[str, str],
    credit_rules: dict[str, pd.DataFrame],
) -> tuple[dict[str, str], dict[str, str], pd.DataFrame, dict[str, str] | None]:
    """Returns (values, starting values, displayed fields, credit mapping)."""
    fields = get_credit_fields(credit_rules)
    mapping = get_credit_mapping(company_code=company_code, credit_rules=credit_rules)

    if mapping is None:
        st.warning(
            "No active Credit Management mapping is configured for "
            f"Company Code {company_code}"
        )

    plan = plan_credit_form(fields=fields, customer=customer, mapping=mapping)

    values: dict[str, str] = {}
    defaults: dict[str, str] = {}
    rendered_keys: set[str] = set()

    def render_credit_field(field_key: str, placeholder: str | None = None) -> None:
        field = plan.field_map.get(field_key)
        if not field:
            return

        label = clean(field.get("label")) or field_key
        required = is_yes(field.get("required"))
        input_type = clean(field.get("input_type")).lower() or "text"
        initial_value = get_credit_initial_value(field=field, customer=customer, mapping=mapping)
        widget_key = f"credit__{field_key}"
        disabled = True if input_type == "readonly" else not is_yes(field.get("editable"))
        email = not disabled and is_email_field(field_key)

        defaults[field_key] = initial_value

        value = st.text_input(
            label,
            value=initial_value,
            disabled=disabled,
            key=widget_key,
            help=clean(field.get("notes")) or (EMAIL_HELP if email else None),
            placeholder=placeholder,
        )
        apply_field_state(widget_key=widget_key, value=value, required=required, email=email)

        values[field_key] = clean(value)
        rendered_keys.add(field_key)

    for heading, caption, widths, row in CREDIT_LAYOUT:
        if heading:
            st.markdown(f"##### {heading}")
        if caption:
            st.caption(caption)

        for column, cell in zip(st.columns(widths, gap="small"), row):
            if cell:
                with column:
                    render_credit_field(*cell)

    remaining_keys = [key for key in plan.field_map if key not in rendered_keys]

    if remaining_keys:
        st.markdown("##### Additional Credit Information")
        for start in range(0, len(remaining_keys), 3):
            for column, field_key in zip(
                st.columns(3, gap="small"), remaining_keys[start:start + 3]
            ):
                with column:
                    render_credit_field(field_key)

    finalize_credit_values(plan, values, defaults)

    return values, defaults, plan.display_fields, mapping
