"""General Data section: requested field changes and attachments."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from portal.config import MAX_ATTACHMENT_SIZE_BYTES
from portal.core.general_data import (
    bank_details_required,
    current_general_value,
    duplicate_labels,
    field_label,
    process_attachments,
    process_bank_attachments,
    requestable_general_fields,
    required_general_keys,
)
from portal.core.utils import as_int, clean
from portal.core.validation import is_email_field
from portal.ui.widgets import (
    EMAIL_HELP,
    EMAIL_PLACEHOLDER,
    apply_field_state,
    apply_required_upload_state,
)

ROW_COUNT_KEY = "general_data__row_count"
BANK_UPLOAD_KEY = "general_data__bank_attachments"

# Per-file limit shown and enforced by the uploader (portal.config limit in MB)
MAX_FILE_MB = MAX_ATTACHMENT_SIZE_BYTES // (1024 * 1024)
MAX_ROWS = 20

ATTACHMENT_TYPES = ["pdf", "png", "jpg", "jpeg", "doc", "docx", "xls", "xlsx", "csv", "txt"]
BANK_ATTACHMENT_TYPES = ["pdf", "png", "jpg", "jpeg", "doc", "docx"]


def _remove_row_state(index: int) -> None:
    for key in list(st.session_state.keys()):
        if (
            key == f"general_data__field__{index}"
            or key.startswith(f"general_data__value__{index}__")
            or key.startswith(f"general_data__current__{index}__")
            or key.startswith(f"general_data__empty_current__{index}")
            or key.startswith(f"general_data__empty_value__{index}")
        ):
            del st.session_state[key]


def _render_row_controls() -> int:
    """Add / remove buttons; returns the number of rows to show."""
    if ROW_COUNT_KEY not in st.session_state:
        st.session_state[ROW_COUNT_KEY] = 0

    controls = st.columns([1.6, 1.9, 2.5])

    with controls[0]:
        if st.button("＋ Add field", key="general_data__add", width="stretch"):
            st.session_state[ROW_COUNT_KEY] = min(
                int(st.session_state[ROW_COUNT_KEY]) + 1,
                MAX_ROWS,
            )

    with controls[1]:
        if st.button(
            "− Remove last",
            key="general_data__remove",
            width="stretch",
            disabled=(int(st.session_state[ROW_COUNT_KEY]) <= 0),
        ):
            last_index = int(st.session_state[ROW_COUNT_KEY]) - 1
            _remove_row_state(last_index)
            st.session_state[ROW_COUNT_KEY] = max(last_index, 0)

    return int(st.session_state[ROW_COUNT_KEY])


def _render_value_input(config: dict[str, Any], field_key: str, value_key: str) -> str:
    """Requested-value input of one General Data row (always required once shown)."""
    max_length = as_int(config.get("max_length"))

    if (clean(config.get("input_type")).lower() or "text") == "textarea":
        value = st.text_area(
            "Requested value",
            key=value_key,
            max_chars=max_length,
            height=90,
        )
    else:
        value = st.text_input(
            "Requested value",
            key=value_key,
            max_chars=max_length,
            placeholder=EMAIL_PLACEHOLDER if is_email_field(field_key) else None,
            help=EMAIL_HELP if is_email_field(field_key) else None,
        )

    apply_field_state(
        widget_key=value_key,
        value=value,
        required=True,
        email=is_email_field(field_key),
    )
    return value


def _render_required_rows(
    required_keys: list[str],
    field_records: dict[str, Any],
    customer: dict[str, str],
    results: dict[str, dict[str, str]],
) -> None:
    """Fields the rules require for this customer's country: always shown."""
    st.markdown("**Required for this customer**")

    for field_key in required_keys:
        config = field_records[field_key]
        current_value = current_general_value(config, field_key, customer)
        columns = st.columns([1.25, 1, 1.5])

        with columns[0]:
            st.text_input(
                "General Data field",
                value=field_label(config, field_key),
                disabled=True,
                key=f"general_data__required_field__{field_key}",
                help=clean(config.get("notes")) or None,
            )
        with columns[1]:
            st.text_input(
                "Current value",
                value=(current_value or "—"),
                disabled=True,
                key=f"general_data__required_current__{field_key}",
            )
        with columns[2]:
            requested_value = _render_value_input(
                config, field_key, f"general_data__required_value__{field_key}"
            )

        results[field_key] = {
            "field_key": field_key,
            "label": field_label(config, field_key),
            "sap_field": clean(config.get("sap_field")),
            "current_value": current_value,
            "requested_value": clean(requested_value),
        }


def render_general_data_requests(
    *,
    customer: dict[str, str],
    reference_library: dict[str, pd.DataFrame],
    request_type: str = "",
) -> tuple[dict[str, dict[str, str]], list[str], bool]:
    """Returns (requested changes by field, duplicate labels, bank docs needed)."""
    field_records = requestable_general_fields(
        customer=customer,
        reference_library=reference_library,
    )
    required_keys = required_general_keys(field_records, request_type)
    results: dict[str, dict[str, str]] = {}

    if required_keys:
        _render_required_rows(required_keys, field_records, customer, results)
        st.markdown("**Other changes**")

    st.caption(
        "Add only the General Data fields you need. "
        "Select a field, review its current value, "
        "then enter the requested new value"
    )

    # Required fields already have their own row
    field_keys = [key for key in field_records if key not in required_keys]

    row_count = _render_row_controls()

    if row_count == 0:
        st.info("No General Data changes added")

    selected_keys: list[str] = []

    for index in range(row_count):
        columns = st.columns([1.25, 1, 1.5])

        with columns[0]:
            selected_key = st.selectbox(
                "General Data field",
                options=([""] + field_keys),
                key=f"general_data__field__{index}",
                format_func=lambda key: (
                    "Select field..." if not key else field_label(field_records[key], key)
                ),
            )

        if not selected_key:
            with columns[1]:
                st.text_input(
                    "Current value",
                    value="",
                    disabled=True,
                    key=f"general_data__empty_current__{index}",
                )

            with columns[2]:
                st.text_input(
                    "Requested value",
                    value="",
                    disabled=True,
                    key=f"general_data__empty_value__{index}",
                )

            continue

        selected_keys.append(selected_key)
        config = field_records[selected_key]
        current_value = current_general_value(config, selected_key, customer)

        with columns[1]:
            st.text_input(
                "Current value",
                value=(current_value or "—"),
                disabled=True,
                key=f"general_data__current__{index}__{selected_key}",
            )

        # A chosen field needs its new value
        with columns[2]:
            requested_value = _render_value_input(
                config, selected_key, f"general_data__value__{index}__{selected_key}"
            )

        results[selected_key] = {
            "field_key": selected_key,
            "label": field_label(config, selected_key),
            "sap_field": clean(config.get("sap_field")),
            "current_value": current_value,
            "requested_value": clean(requested_value),
        }

    return (
        results,
        duplicate_labels(selected_keys, field_records),
        bank_details_required(selected_keys, field_records),
    )


def render_bank_details_attachment(
    bank_details_required: bool,
) -> tuple[list[dict[str, Any]], list[str]]:
    if not bank_details_required:
        return [], []

    st.markdown("**Supporting bank details documentation** :red[*]")

    st.caption(
        "Supporting documentation is required when requesting "
        "a Bank Account / IBAN change."
    )

    uploaded_files = st.file_uploader(
        "Bank account / IBAN supporting documentation",
        type=BANK_ATTACHMENT_TYPES,
        accept_multiple_files=True,
        max_upload_size=MAX_FILE_MB,
        key=BANK_UPLOAD_KEY,
        help=(
            "Upload supporting documentation for the requested "
            "Bank Account / IBAN change. Maximum 3 MB per file"
        ),
    )

    attachments, errors = process_bank_attachments(uploaded_files)
    apply_required_upload_state(widget_key=BANK_UPLOAD_KEY, has_files=bool(attachments))
    return attachments, errors


def render_attachments() -> tuple[list[dict[str, Any]], list[str]]:
    st.markdown("**Attachments**")

    uploaded_files = st.file_uploader(
        "Supporting documents or images",
        type=ATTACHMENT_TYPES,
        accept_multiple_files=True,
        max_upload_size=MAX_FILE_MB,
        key="general_data__attachments",
        help=(
            "Examples: signed documents or supporting images. "
            "Maximum 3 MB per file and 5 MB total."
        ),
    )

    attachments, errors = process_attachments(uploaded_files)

    if uploaded_files:
        st.caption("Attached: " + ", ".join(clean(file.name) for file in uploaded_files))

    return attachments, errors
