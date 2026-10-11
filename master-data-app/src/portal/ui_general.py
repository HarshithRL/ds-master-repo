from __future__ import annotations

from typing import Any
import base64

import pandas as pd
import streamlit as st

from .config import (
    MAX_ATTACHMENT_SIZE_BYTES,
    MAX_ATTACHMENTS_TOTAL_BYTES,
)
from .utils import active_rows, as_int, clean


# =============================================================================
# GENERAL DATA
# =============================================================================


def render_general_data_requests(
    *,
    customer: dict[str, str],
    reference_library: dict[str, pd.DataFrame],
) -> tuple[dict[str, dict[str, str]], list[str], bool,]:
    st.caption(
        "Add only the General Data fields you need. "
        "Select a field, review its current value, "
        "then enter the requested new value."
    )

    # -------------------------------------------------------------------------
    # GENERAL DATA FIELD CONFIGURATION
    # -------------------------------------------------------------------------

    field_library = active_rows(reference_library["general_data_fields"]).copy()

    # Normalize Excel column names.
    field_library.columns = [clean(column).lower() for column in field_library.columns]

    # Only fields explicitly marked as requestable.
    if "can_request_change" in field_library.columns:
        field_library = field_library[
            field_library["can_request_change"]
            .astype(str)
            .str.strip()
            .str.upper()
            .eq("Y")
        ].copy()

    # -------------------------------------------------------------------------
    # COUNTRY-SPECIFIC TAX CONFIGURATION
    # -------------------------------------------------------------------------

    customer_country = clean(
        customer.get(
            "country",
            "",
        )
    ).upper()

    tax_field_keys = {f"tax_number_{number}" for number in range(1, 7)}

    tax_labels: dict[str, str] = {}

    tax_details = reference_library.get("tax_details")

    if tax_details is not None and not tax_details.empty and customer_country:
        tax_details = tax_details.copy()

        tax_details.columns = [clean(column).lower() for column in tax_details.columns]

        if "cust_country" in tax_details.columns:
            country_tax_rows = tax_details[
                tax_details["cust_country"]
                .astype(str)
                .str.strip()
                .str.upper()
                .eq(customer_country)
            ]

            if not country_tax_rows.empty:
                tax_row = country_tax_rows.iloc[0]

                for number in range(1, 7):
                    field_key = f"tax_number_{number}"

                    if field_key not in tax_row.index:
                        continue

                    country_label = clean(tax_row.get(field_key))

                    if country_label:
                        tax_labels[field_key] = country_label

    # -------------------------------------------------------------------------
    # BUILD FINAL FIELD LIST
    # -------------------------------------------------------------------------

    final_records: list[dict[str, Any]] = []

    for row in field_library.to_dict("records"):
        field_key = clean(row.get("field_key")).lower()

        if not field_key:
            continue

        record = dict(row)
        record["field_key"] = field_key

        # Use the country-specific tax label when one is available.
        # Otherwise keep the generic Tax Number label from General_Data_Fields.
        if field_key in tax_field_keys and field_key in tax_labels:
            record["label"] = tax_labels[field_key]

        final_records.append(record)

    if final_records:
        field_library = pd.DataFrame(final_records)

        field_library = field_library.sort_values(
            "label",
            kind="stable",
        ).reset_index(drop=True)

    else:
        field_library = pd.DataFrame(columns=field_library.columns)

    field_records = {
        clean(row.get("field_key")): row
        for row in field_library.to_dict("records")
        if clean(row.get("field_key"))
    }

    field_keys = list(field_records.keys())

    # -------------------------------------------------------------------------
    # DYNAMIC ROW COUNT
    # -------------------------------------------------------------------------

    count_key = "general_data__row_count"

    if count_key not in st.session_state:
        st.session_state[count_key] = 0

    controls = st.columns([1.65, 1.85, 2.5])

    with controls[0]:
        if st.button(
            "Add field",
            key="general_data__add",
            use_container_width=True,
        ):
            st.session_state[count_key] = min(
                int(st.session_state[count_key]) + 1,
                20,
            )

    with controls[1]:
        if st.button(
            "Remove last",
            key="general_data__remove",
            use_container_width=True,
            disabled=(int(st.session_state[count_key]) <= 0),
        ):
            last_index = int(st.session_state[count_key]) - 1

            for key in list(st.session_state.keys()):
                if (
                    key == ("general_data__field__" f"{last_index}")
                    or key.startswith("general_data__value__" f"{last_index}__")
                    or key.startswith("general_data__current__" f"{last_index}__")
                    or key.startswith("general_data__empty_current__" f"{last_index}")
                    or key.startswith("general_data__empty_value__" f"{last_index}")
                ):
                    del st.session_state[key]

            st.session_state[count_key] = max(
                last_index,
                0,
            )

    row_count = int(st.session_state[count_key])

    if row_count == 0:
        st.info("No General Data changes added.")

    results: dict[
        str,
        dict[str, str],
    ] = {}

    selected_keys: list[str] = []

    # -------------------------------------------------------------------------
    # RENDER GENERAL DATA ROWS
    # -------------------------------------------------------------------------

    for index in range(row_count):
        columns = st.columns([1.25, 1, 1.5])

        with columns[0]:
            selected_key = st.selectbox(
                "General Data field",
                options=([""] + field_keys),
                key=("general_data__field__" f"{index}"),
                format_func=lambda key: (
                    "Select field..."
                    if not key
                    else (clean(field_records[key].get("label")) or key)
                ),
            )

        if not selected_key:
            with columns[1]:
                st.text_input(
                    "Current value",
                    value="",
                    disabled=True,
                    key=("general_data__empty_current__" f"{index}"),
                )

            with columns[2]:
                st.text_input(
                    "Requested value",
                    value="",
                    disabled=True,
                    key=("general_data__empty_value__" f"{index}"),
                )

            continue

        selected_keys.append(selected_key)

        config = field_records[selected_key]

        label = clean(config.get("label")) or selected_key

        source_field = clean(config.get("customer_source_field"))

        current_value = (
            clean(
                customer.get(
                    source_field,
                    "",
                )
            )
            if source_field
            else ""
        )

        # If actual tax-number values later exist directly
        # on the customer object, use them automatically.
        if not current_value and selected_key in tax_field_keys:
            current_value = clean(
                customer.get(
                    selected_key,
                    "",
                )
            )

        with columns[1]:
            st.text_input(
                "Current value",
                value=(current_value or "—"),
                disabled=True,
                key=("general_data__current__" f"{index}__" f"{selected_key}"),
            )

        max_length = as_int(config.get("max_length"))

        input_type = clean(config.get("input_type")).lower() or "text"

        with columns[2]:
            if input_type == "textarea":
                requested_value = st.text_area(
                    "Requested value",
                    key=("general_data__value__" f"{index}__" f"{selected_key}"),
                    max_chars=(max_length),
                    height=90,
                )

            else:
                requested_value = st.text_input(
                    "Requested value",
                    key=("general_data__value__" f"{index}__" f"{selected_key}"),
                    max_chars=(max_length),
                )

        results[selected_key] = {
            "field_key": selected_key,
            "label": label,
            "sap_field": clean(config.get("sap_field")),
            "current_value": current_value,
            "requested_value": clean(requested_value),
        }

    # -------------------------------------------------------------------------
    # DUPLICATE-FIELD VALIDATION
    # -------------------------------------------------------------------------

    duplicate_labels: list[str] = []

    seen_fields: set[str] = set()

    for field_key in selected_keys:
        if field_key in seen_fields:
            duplicate_labels.append(
                clean(field_records[field_key].get("label")) or field_key
            )

        seen_fields.add(field_key)

    # -------------------------------------------------------------------------
    # BANK DETAILS REQUIREMENT
    # -------------------------------------------------------------------------

    bank_details_required = any(
        (
            clean(field_records[field_key].get("label")).casefold()
            == "bank account / iban"
        )
        or (
            clean(field_key).casefold()
            in {
                "bank_account",
                "iban",
                "bank_account_iban",
            }
        )
        for field_key in selected_keys
        if field_key in field_records
    )

    return (
        results,
        duplicate_labels,
        bank_details_required,
    )


# =============================================================================
# BANK DETAILS ATTACHMENT
# =============================================================================


def render_bank_details_attachment(
    bank_details_required: bool,
) -> tuple[list[dict[str, Any]], list[str],]:
    if not bank_details_required:
        return [], []

    st.markdown("**Supporting bank details documentation**")

    st.caption(
        "Supporting documentation is required when requesting "
        "a Bank Account / IBAN change."
    )

    uploaded_files = st.file_uploader(
        "Bank account / IBAN supporting documentation",
        type=[
            "pdf",
            "png",
            "jpg",
            "jpeg",
            "doc",
            "docx",
        ],
        accept_multiple_files=True,
        key=("general_data__bank_attachments"),
        help=(
            "Upload supporting documentation for the requested "
            "Bank Account / IBAN change. Maximum 3 MB per file."
        ),
    )

    attachments: list[dict[str, Any]] = []

    errors: list[str] = []

    for uploaded_file in uploaded_files or []:
        file_bytes = uploaded_file.getvalue()

        file_size = len(file_bytes)

        if file_size > MAX_ATTACHMENT_SIZE_BYTES:
            errors.append(f"{uploaded_file.name} " "is larger than 3 MB.")
            continue

        attachments.append(
            {
                "name": clean(uploaded_file.name),
                "mime_type": clean(uploaded_file.type),
                "size_bytes": file_size,
                "content_base64": base64.b64encode(file_bytes).decode("ascii"),
                "attachment_type": "bank_details",
            }
        )

    if not attachments:
        errors.append(
            "Supporting bank details documentation is required "
            "for a Bank Account / IBAN change."
        )

    return (
        attachments,
        errors,
    )


# =============================================================================
# GENERAL ATTACHMENTS
# =============================================================================


def render_attachments() -> tuple[
    list[dict[str, Any]],
    list[str],
]:
    st.markdown("**Attachments**")

    uploaded_files = st.file_uploader(
        "Supporting documents or images",
        type=[
            "pdf",
            "png",
            "jpg",
            "jpeg",
            "doc",
            "docx",
            "xls",
            "xlsx",
            "csv",
            "txt",
        ],
        accept_multiple_files=True,
        key=("general_data__attachments"),
        help=(
            "Examples: signed documents or supporting images. "
            "Maximum 3 MB per file and 5 MB total."
        ),
    )

    attachments: list[dict[str, Any]] = []

    errors: list[str] = []

    total_size = 0

    for uploaded_file in uploaded_files or []:
        file_bytes = uploaded_file.getvalue()

        file_size = len(file_bytes)

        total_size += file_size

        if file_size > MAX_ATTACHMENT_SIZE_BYTES:
            errors.append(f"{uploaded_file.name} " "is larger than 3 MB.")
            continue

        attachments.append(
            {
                "name": clean(uploaded_file.name),
                "mime_type": clean(uploaded_file.type),
                "size_bytes": file_size,
                "content_base64": base64.b64encode(file_bytes).decode("ascii"),
            }
        )

    if total_size > MAX_ATTACHMENTS_TOTAL_BYTES:
        errors.append("The total attachment size " "is larger than 5 MB.")

    if uploaded_files:
        st.caption(
            "Attached: " + ", ".join(clean(file.name) for file in uploaded_files)
        )

    return (
        attachments,
        errors,
    )
