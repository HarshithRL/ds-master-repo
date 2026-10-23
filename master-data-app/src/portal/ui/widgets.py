"""Form widgets shared by every section."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from portal.constants import CHECKBOX, EXISTING, FLAG_ON, PARTY_MODE_KEYS, SAME_AS_CUSTOMER
from portal.core.rules import (
    ForcedValue,
    build_select_choices,
    existing_value,
    find_default,
    get_field_options,
    readonly_value,
)
from portal.core.utils import as_int, clean, format_option, is_yes
from portal.core.validation import is_email_field, is_valid_email

COMPLETE_BORDER = ("#5C9461", "rgba(92, 148, 97, 0.18)")  # green
MISSING_BORDER = ("#C62828", "rgba(198, 40, 40, 0.16)")  # red


def spacer(height: int) -> None:
    st.markdown(f"<div style='height:{height}px'></div>", unsafe_allow_html=True)


EMAIL_PLACEHOLDER = "name@company.com"
EMAIL_HELP = "Email address, e.g. name@company.com"
EMAIL_ERROR = "Enter a valid email, e.g. name@company.com"


def apply_field_state(
    *,
    widget_key: str,
    value: Any,
    required: bool,
    email: bool = False,
) -> None:
    """
    Show a field's state with CSS scoped to its widget key.

    - required: red star on the label; red border while empty
    - email: red border and a message under the field while the format is
      wrong; an empty optional email stays neutral
    - green border once a required or email value is filled in and valid
    """
    text = clean(value)
    invalid_email = email and bool(text) and not is_valid_email(text)

    if not required and not (email and text):
        return

    border_color, focus_color = (
        MISSING_BORDER if invalid_email or not text else COMPLETE_BORDER
    )

    widget = f'[data-testid="stMain"] .st-key-{widget_key}'
    # The bordered box is the widget wrapper (see FORM CONTROLS in theme.py)
    box = f'{widget} :is([data-testid="stTextInputRootElement"], [data-testid="stTextAreaRootElement"], .react-aria-ComboBox > [role="group"], div[data-baseweb="select"] > div)'

    rules = f"""
        {box} {{
            border: 1.5px solid {border_color} !important;
            box-shadow: none !important;
            transition:
                border-color 0.15s ease,
                box-shadow 0.15s ease;
        }}

        {box}:focus-within {{
            border-color: {border_color} !important;
            box-shadow: 0 0 0 2px {focus_color} !important;
        }}
    """

    if required:
        rules += f"""
        {widget} [data-testid="stWidgetLabel"] [data-testid="stMarkdownContainer"] p::after {{
            content: " *";
            color: {MISSING_BORDER[0]};
            font-weight: 700;
        }}
        """

    if invalid_email:
        # Message under the field, outside the layout so field rows stay
        # aligned; the row (or the lone field) gets room for it below
        rules += f"""
        {widget} [data-testid="stTextInputRootElement"] {{
            position: relative !important;
            overflow: visible !important;
        }}

        {widget} [data-testid="stTextInputRootElement"]::after {{
            content: "{EMAIL_ERROR}";
            position: absolute;
            left: 2px;
            right: 0;
            top: calc(100% + 4px);
            color: {MISSING_BORDER[0]};
            font-size: 0.72rem;
            line-height: 0.95rem;
            font-weight: 600;
            pointer-events: none;
        }}

        [data-testid="stMain"] div[data-testid="stHorizontalBlock"]:has(.st-key-{widget_key}),
        {widget}:not(div[data-testid="stHorizontalBlock"] *) {{
            margin-bottom: 1.6rem !important;
        }}
        """

    st.markdown(f"<style>{rules}</style>", unsafe_allow_html=True)


def apply_required_upload_state(*, widget_key: str, has_files: bool) -> None:
    """Red star on the label; red dashed drop zone until a file is attached, then green."""
    color = COMPLETE_BORDER[0] if has_files else MISSING_BORDER[0]

    st.markdown(
        f"""
        <style>
        [data-testid="stMain"] .st-key-{widget_key} [data-testid="stFileUploaderDropzone"] {{
            border: 1.5px dashed {color} !important;
            background: {"#F4FAF4" if has_files else "#FFF6F6"} !important;
        }}

        [data-testid="stMain"] .st-key-{widget_key} [data-testid="stWidgetLabel"] [data-testid="stMarkdownContainer"] p::after {{
            content: " *";
            color: {MISSING_BORDER[0]};
            font-weight: 700;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_section_comment(section_key: str) -> str:
    return clean(
        st.text_area(
            "Comments / additional instructions",
            key=f"section_comment__{section_key}",
            height=70,
            label_visibility="visible",
            placeholder="Optional comments for Master Data Team...",
        )
    )


def _text_input(
    label: str,
    *,
    required: bool,
    widget_key: str,
    email: bool = False,
    **kwargs,
) -> str:
    if email:
        kwargs["placeholder"] = kwargs.get("placeholder") or EMAIL_PLACEHOLDER
        kwargs["help"] = kwargs.get("help") or EMAIL_HELP

    value = st.text_input(label, key=widget_key, **kwargs)
    apply_field_state(widget_key=widget_key, value=value, required=required, email=email)
    return value


def render_rule_field(
    *,
    field: dict[str, Any],
    company_code: str,
    sales_org: str,
    rules: dict[str, pd.DataFrame],
    context: dict[str, str],
    customer: dict[str, str] | None = None,
    forced: dict[str, ForcedValue] | None = None,
) -> str:
    """Render one Form_Fields row as its configured widget and return the value."""
    field_key = clean(field.get("field_key"))
    label = clean(field.get("label")) or field_key
    required = is_yes(field.get("required"))
    editable = is_yes(field.get("editable"))
    hidden = is_yes(field.get("hidden"))
    input_type = clean(field.get("input_type")).lower() or "text"
    help_text = clean(field.get("notes")) or None

    # A Field_Dependencies rule sets this field's value (and may lock it)
    rule = (forced or {}).get(field_key)
    if rule:
        st.session_state[f"form__{field_key}"] = rule.value
        editable = editable and not rule.lock
        help_text = rule.reason
    placeholder = clean(field.get("placeholder")) or None
    max_length = as_int(field.get("max_length"))
    # Required fields get their red star from apply_field_state (CSS),
    # so screen readers read the plain label
    display_label = label

    if input_type in {"readonly", EXISTING}:
        value = (
            existing_value(field, customer)
            if input_type == EXISTING
            else readonly_value(field, context)
        )
        if not hidden:
            # Show the option description next to the code, as a dropdown would
            description = next(
                (
                    option["description"]
                    for option in get_field_options(
                        field_key=field_key,
                        company_code=company_code,
                        sales_org=sales_org,
                        rules=rules,
                    )
                    if value and option["value"] == value
                ),
                "",
            )
            _text_input(
                display_label,
                required=required and input_type != EXISTING,
                widget_key=f"form__{field_key}",
                value=format_option(value, description) if value else "",
                disabled=True,
                help=help_text,
                placeholder=placeholder or ("Not set in SAP" if input_type == EXISTING else None),
            )
        return value

    if input_type == "computed":
        copy_from = clean(field.get("copy_from_field"))
        value = clean(st.session_state.get(f"form__{copy_from}", ""))
        if not hidden:
            _text_input(
                display_label,
                required=required,
                widget_key=f"computed_display__{field_key}",
                value=value,
                disabled=True,
                help=help_text,
            )
        return value

    option_rows = get_field_options(
        field_key=field_key,
        company_code=company_code,
        sales_org=sales_org,
        rules=rules,
    )
    default_value = find_default(field, option_rows)
    widget_key = f"form__{field_key}"

    if hidden:
        return default_value

    if input_type == CHECKBOX:
        checked = st.checkbox(
            display_label,
            value=is_yes(default_value),
            key=widget_key,
            disabled=not editable,
            help=help_text,
        )
        return FLAG_ON if checked else ""

    if input_type == "select":
        choices = build_select_choices(
            option_rows=option_rows,
            required=required,
            current_value=clean(st.session_state.get(widget_key, default_value)),
            default_value=default_value,
        )

        if choices is None:
            return clean(
                _text_input(
                    display_label,
                    required=required,
                    widget_key=widget_key,
                    email=editable and is_email_field(field_key),
                    value=default_value,
                    disabled=not editable,
                    max_chars=max_length,
                    help=help_text,
                    placeholder=placeholder,
                )
            )

        customer_id = clean(context.get("customer_id"))

        def format_choice(code: str) -> str:
            if code == "":
                return ""
            # Party modes show the customer ID instead of SAME_AS_CUSTOMER
            if field_key in PARTY_MODE_KEYS and code == SAME_AS_CUSTOMER and customer_id:
                return customer_id
            return format_option(code, choices.descriptions.get(code, ""))

        value = st.selectbox(
            display_label,
            options=choices.options,
            # A rule already put the value in Session State; no second default
            index=None if rule else choices.index,
            key=widget_key,
            disabled=not editable,
            format_func=format_choice,
            help=help_text,
            placeholder="Choose an option",
        )
        apply_field_state(widget_key=widget_key, value=value, required=required)
        return clean(value)

    if input_type == "textarea":
        value = st.text_area(
            display_label,
            value=default_value,
            key=widget_key,
            disabled=not editable,
            height=110,
            max_chars=max_length,
            help=help_text,
            placeholder=placeholder,
        )
        apply_field_state(widget_key=widget_key, value=value, required=required)
        return clean(value)

    return clean(
        _text_input(
            display_label,
            required=required,
            widget_key=widget_key,
            email=editable and is_email_field(field_key),
            value=default_value,
            disabled=not editable,
            max_chars=max_length,
            help=help_text,
            placeholder=placeholder,
        )
    )
