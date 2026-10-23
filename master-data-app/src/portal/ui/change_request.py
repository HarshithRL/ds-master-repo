"""
Change request sections.

Each section lists the fields that can be changed; the requester picks the
ones they need and enters only those values. Nothing is mandatory.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import pandas as pd
import streamlit as st

from portal.constants import (
    CHECKBOX,
    CREDIT_LABELS,
    FLAG_ON,
    PARTNER_LABELS,
    PARTNER_NAME_FIELDS,
    PARTNER_NAME_MAX_LENGTH,
    PARTY_MODE_KEYS,
    SAME_AS_CUSTOMER,
)
from portal.core.rules import OptionRow, changeable_fields, get_field_options
from portal.core.utils import as_int, clean, format_option, is_yes
from portal.core.validation import ChangeEntry, is_email_field
from portal.ui.state import CHANGE_PICK_PREFIX, CHANGE_VALUE_PREFIX
from portal.ui.widgets import EMAIL_HELP, EMAIL_PLACEHOLDER, apply_field_state

FIELDS_PER_ROW = 3

PICKER_HELP = (
    "Pick only the fields you want to change. "
    "Each one appears below for you to enter the new value."
)


@dataclass(frozen=True)
class ChangeField:
    """A field the requester can pick in the Change form."""

    field_key: str
    label: str
    input_type: str = "text"
    max_length: int | None = None
    options: list[OptionRow] = field(default_factory=list)


# =============================================================================
# CANDIDATE FIELDS
# =============================================================================


def _unique_labels(fields: list[ChangeField]) -> list[ChangeField]:
    """Replace labels used twice in a section with the readable field key."""
    counts = Counter(item.label for item in fields)
    return [
        item
        if counts[item.label] == 1
        else ChangeField(
            item.field_key,
            item.field_key.replace("_", " ").title(),
            item.input_type,
            item.max_length,
            item.options,
        )
        for item in fields
    ]


def rule_change_fields(
    section_df: pd.DataFrame,
    *,
    company_code: str,
    sales_org: str,
    rules: dict[str, pd.DataFrame],
    include_partner_names: bool = False,
) -> list[ChangeField]:
    fields = []

    for record in changeable_fields(section_df):
        field_key = clean(record.get("field_key"))
        input_type = clean(record.get("input_type")).lower() or "text"
        fields.append(
            ChangeField(
                field_key=field_key,
                label=PARTNER_LABELS.get(field_key)
                or clean(record.get("label"))
                or field_key,
                input_type=input_type,
                max_length=as_int(record.get("max_length")),
                options=get_field_options(
                    field_key=field_key,
                    company_code=company_code,
                    sales_org=sales_org,
                    rules=rules,
                )
                if input_type == "select"
                else [],
            )
        )

    if include_partner_names and fields:
        fields += [
            ChangeField(key, label, max_length=PARTNER_NAME_MAX_LENGTH)
            for key, label in PARTNER_NAME_FIELDS
        ]

    return _unique_labels(fields)


def credit_change_fields(field_map: dict[str, dict]) -> list[ChangeField]:
    return _unique_labels(
        [
            ChangeField(
                field_key,
                CREDIT_LABELS.get(field_key) or clean(record.get("label")) or field_key,
            )
            for field_key, record in field_map.items()
        ]
    )


# =============================================================================
# RENDERING
# =============================================================================


def _render_value_input(
    item: ChangeField,
    *,
    section_key: str,
    current_value: str,
    customer_id: str,
) -> str:
    """Empty input for the new value; the current value is shown as a hint."""
    widget_key = f"{CHANGE_VALUE_PREFIX}{section_key}__{item.field_key}"
    current_hint = f"Current value: {current_value or '—'}"
    option_values = list(
        dict.fromkeys(option["value"] for option in item.options if option["value"])
    )

    if option_values:
        descriptions = {option["value"]: option["description"] for option in item.options}

        def format_choice(code: str) -> str:
            if code == "":
                return ""
            if item.field_key in PARTY_MODE_KEYS and code == SAME_AS_CUSTOMER and customer_id:
                return customer_id
            return format_option(code, descriptions.get(code, ""))

        return clean(
            st.selectbox(
                item.label,
                options=[""] + option_values,
                key=widget_key,
                format_func=format_choice,
                help=current_hint,
            )
        )

    if item.input_type == CHECKBOX:
        # Picked to change it, so the box starts opposite to the current value
        checked = st.checkbox(
            item.label,
            value=not is_yes(current_value),
            key=widget_key,
            help=f"{current_hint}. Ticked = {FLAG_ON}, unticked = empty.",
        )
        return FLAG_ON if checked else ""

    if item.input_type == "textarea":
        return clean(
            st.text_area(
                item.label,
                key=widget_key,
                height=110,
                max_chars=item.max_length,
                placeholder=current_hint,
                help=current_hint,
            )
        )

    if is_email_field(item.field_key):
        value = st.text_input(
            item.label,
            key=widget_key,
            max_chars=item.max_length,
            placeholder=EMAIL_PLACEHOLDER,
            help=f"{EMAIL_HELP}. {current_hint}",
        )
        apply_field_state(widget_key=widget_key, value=value, required=False, email=True)
        return clean(value)

    return clean(
        st.text_input(
            item.label,
            key=widget_key,
            max_chars=item.max_length,
            placeholder=current_hint,
            help=current_hint,
        )
    )


def render_change_section(
    *,
    section_key: str,
    section_title: str,
    fields: list[ChangeField],
    customer: dict[str, str],
) -> list[ChangeEntry]:
    """Field picker plus inputs for the picked fields; returns the changes."""
    if not fields:
        st.info("No changeable fields are configured for this section")
        return []

    by_key = {item.field_key: item for item in fields}

    picked = st.multiselect(
        "Fields to change",
        options=list(by_key),
        format_func=lambda key: by_key[key].label,
        key=f"{CHANGE_PICK_PREFIX}{section_key}",
        placeholder="Choose the fields you want to change",
        help=PICKER_HELP,
    )

    entries: list[ChangeEntry] = []

    # As in Create / Extend, tick boxes get their own row below the other fields
    rows = [
        [key for key in picked if by_key[key].input_type != CHECKBOX],
        [key for key in picked if by_key[key].input_type == CHECKBOX],
    ]
    chunks = [
        group[start:start + FIELDS_PER_ROW]
        for group in rows
        for start in range(0, len(group), FIELDS_PER_ROW)
    ]

    for chunk in chunks:
        columns = st.columns(FIELDS_PER_ROW, gap="small", vertical_alignment="top")

        for column, field_key in zip(columns, chunk):
            item = by_key[field_key]
            current_value = clean(customer.get(field_key))

            with column:
                requested_value = _render_value_input(
                    item,
                    section_key=section_key,
                    current_value=current_value,
                    customer_id=clean(customer.get("customer_id")),
                )

            entries.append(
                ChangeEntry(
                    section_key=section_key,
                    section=section_title,
                    field_key=field_key,
                    label=item.label,
                    current_value=current_value,
                    requested_value=requested_value,
                    allow_empty=item.input_type == CHECKBOX,
                )
            )

    return entries
