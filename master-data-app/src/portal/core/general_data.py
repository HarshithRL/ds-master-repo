"""General Data change rows and attachment checks."""

from __future__ import annotations

import base64
from typing import Any, Iterable, Protocol

import pandas as pd

from portal.config import MAX_ATTACHMENT_SIZE_BYTES, MAX_ATTACHMENTS_TOTAL_BYTES
from portal.core.customers import tax_number_labels
from portal.constants import CHANGE_CUSTOMER
from portal.core.utils import active_rows, clean, country_rows, is_yes, lowercase_columns

FieldRecord = dict[str, Any]

TAX_FIELD_KEYS = {f"tax_number_{number}" for number in range(1, 7)}
BANK_FIELD_KEYS = {"bank_account", "iban", "bank_account_iban"}
BANK_FIELD_LABEL = "bank account / iban"

# =============================================================================
# REQUESTABLE FIELDS
# =============================================================================


def requestable_general_fields(
    *,
    customer: dict[str, str],
    reference_library: dict[str, pd.DataFrame],
) -> dict[str, FieldRecord]:
    """
    {field_key: config} for fields with can_request_change=Y, sorted by label.

    Only fields for the customer's country (countries column). Tax number
    labels use the customer's country (Tax_Details) when set.
    """
    library = lowercase_columns(active_rows(reference_library["general_data_fields"]))

    if "can_request_change" in library.columns:
        library = library[
            library["can_request_change"].astype(str).str.strip().str.upper().eq("Y")
        ].copy()

    country = clean(customer.get("country", "")).upper()
    library = country_rows(library, country)
    tax_labels = tax_number_labels(reference_library, country)

    records: list[FieldRecord] = []

    for row in library.to_dict("records"):
        field_key = clean(row.get("field_key")).lower()

        if not field_key:
            continue

        record = dict(row)
        record["field_key"] = field_key

        if field_key in TAX_FIELD_KEYS and field_key in tax_labels:
            record["label"] = tax_labels[field_key]

        records.append(record)

    if records:
        library = (
            pd.DataFrame(records)
            .sort_values("label", kind="stable")
            .reset_index(drop=True)
        )
    else:
        library = pd.DataFrame(columns=library.columns)

    return {
        clean(row.get("field_key")): row
        for row in library.to_dict("records")
        if clean(row.get("field_key"))
    }


def required_general_keys(
    field_records: dict[str, FieldRecord],
    request_type: str,
) -> list[str]:
    """
    Fields with required=Y must be filled on Create / Extend (for the
    countries they apply to). Change requests stay pick-what-you-need.
    """
    if request_type == CHANGE_CUSTOMER:
        return []

    return [key for key, config in field_records.items() if is_yes(config.get("required"))]


def field_label(config: FieldRecord, field_key: str) -> str:
    return clean(config.get("label")) or field_key


def current_general_value(
    config: FieldRecord,
    field_key: str,
    customer: dict[str, str],
) -> str:
    """The customer's current value for a General Data field."""
    source_field = clean(config.get("customer_source_field"))
    value = clean(customer.get(source_field, "")) if source_field else ""

    # Otherwise the customer record's value of the same field (SAP mapping)
    if not value:
        value = clean(customer.get(field_key, ""))

    return value


def duplicate_labels(
    selected_keys: list[str],
    field_records: dict[str, FieldRecord],
) -> list[str]:
    """Labels of fields chosen in more than one General Data row."""
    duplicates: list[str] = []
    seen: set[str] = set()

    for field_key in selected_keys:
        if field_key in seen:
            duplicates.append(field_label(field_records[field_key], field_key))
        seen.add(field_key)

    return duplicates


def bank_details_required(
    selected_keys: list[str],
    field_records: dict[str, FieldRecord],
) -> bool:
    """A Bank Account / IBAN change needs supporting documentation."""
    return any(
        clean(field_records[field_key].get("label")).casefold() == BANK_FIELD_LABEL
        or clean(field_key).casefold() in BANK_FIELD_KEYS
        for field_key in selected_keys
        if field_key in field_records
    )


# =============================================================================
# ATTACHMENTS
# =============================================================================


class UploadedFile(Protocol):
    name: str
    type: str

    def getvalue(self) -> bytes: ...


def _attachment(uploaded_file: UploadedFile, file_bytes: bytes) -> dict[str, Any]:
    return {
        "name": clean(uploaded_file.name),
        "mime_type": clean(uploaded_file.type),
        "size_bytes": len(file_bytes),
        "content_base64": base64.b64encode(file_bytes).decode("ascii"),
    }


def _too_large(uploaded_file: UploadedFile) -> str:
    return f"{uploaded_file.name} " "is larger than 3 MB."


def process_bank_attachments(
    uploaded_files: Iterable[UploadedFile] | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    attachments: list[dict[str, Any]] = []
    errors: list[str] = []

    for uploaded_file in uploaded_files or []:
        file_bytes = uploaded_file.getvalue()

        if len(file_bytes) > MAX_ATTACHMENT_SIZE_BYTES:
            errors.append(_too_large(uploaded_file))
            continue

        attachments.append(
            {**_attachment(uploaded_file, file_bytes), "attachment_type": "bank_details"}
        )

    if not attachments:
        errors.append(
            "Supporting bank details documentation is required "
            "for a Bank Account / IBAN change."
        )

    return attachments, errors


def process_attachments(
    uploaded_files: Iterable[UploadedFile] | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    attachments: list[dict[str, Any]] = []
    errors: list[str] = []
    total_size = 0

    for uploaded_file in uploaded_files or []:
        file_bytes = uploaded_file.getvalue()
        total_size += len(file_bytes)

        if len(file_bytes) > MAX_ATTACHMENT_SIZE_BYTES:
            errors.append(_too_large(uploaded_file))
            continue

        attachments.append(_attachment(uploaded_file, file_bytes))

    if total_size > MAX_ATTACHMENTS_TOTAL_BYTES:
        errors.append("The total attachment size " "is larger than 5 MB.")

    return attachments, errors
