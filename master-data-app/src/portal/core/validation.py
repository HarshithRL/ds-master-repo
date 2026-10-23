"""Section status colours and submit-time validation messages."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Collection

import pandas as pd

from portal.constants import (
    CHECKBOX,
    COMPANY_CODE,
    EMAIL_PATTERN,
    EXISTING_ID,
    NEW_ADDRESS,
    PARTNER_EMAIL_FIELDS,
    PARTNER_FUNCTIONS,
    PARTY_GROUPS,
    SALES_DISTRIBUTION,
)
from portal.core.utils import clean, is_yes

COLLECTION_EMAIL = ("collection_contact_email", "Collection Contact Email")

# =============================================================================
# SHARED CHECKS
# =============================================================================


def is_valid_email(value: str) -> bool:
    return bool(re.match(EMAIL_PATTERN, value))


def is_email_field(field_key: str) -> bool:
    """Fields whose value must be an email address (by naming convention)."""
    return field_key == "email_address" or field_key.endswith("_email")


def _required_missing(
    section_fields: pd.DataFrame,
    values: dict[str, Any],
) -> list[str]:
    """Keys of required fields in the section that have no value."""
    return [
        clean(field.get("field_key"))
        for field in section_fields.to_dict("records")
        if is_yes(field.get("required"))
        # Tick boxes are never empty; computed fields copy a field that is checked itself
        and clean(field.get("input_type")).lower() not in {CHECKBOX, "computed"}
        and clean(field.get("field_key"))
        and not clean(values.get(clean(field.get("field_key")), ""))
    ]


def _party_gaps(partner_values: dict[str, Any]) -> list[tuple[str, str]]:
    """(missing field key, message label) for each incomplete party choice."""
    gaps = []

    for party_label, _title, mode_key, id_key, address_key in PARTY_GROUPS:
        mode = clean(partner_values.get(mode_key, ""))

        if mode == EXISTING_ID and not clean(partner_values.get(id_key, "")):
            gaps.append((id_key, f"{party_label} Existing ID"))

        if mode == NEW_ADDRESS and not clean(partner_values.get(address_key, "")):
            gaps.append((address_key, f"{party_label} New Address"))

    return gaps


def _invalid_emails(
    partner_values: dict[str, Any],
    credit_values: dict[str, Any],
) -> list[tuple[str, str]]:
    """(field key, message label) for filled email fields with a bad format."""
    checks = [(partner_values, key, label) for key, label in PARTNER_EMAIL_FIELDS]
    checks.append((credit_values, *COLLECTION_EMAIL))

    return [
        (key, label)
        for values, key, label in checks
        if clean(values.get(key, "")) and not is_valid_email(clean(values.get(key, "")))
    ]


def _general_data_invalid_emails(general_data_values: dict[str, dict[str, str]]) -> list[str]:
    """Labels of General Data email rows whose requested value is not an email."""
    return [
        "General Data — " + (clean(item.get("label")) or clean(item.get("field_key")))
        for item in general_data_values.values()
        if is_email_field(clean(item.get("field_key")))
        and clean(item.get("requested_value"))
        and not is_valid_email(clean(item.get("requested_value")))
    ]


def _general_data_missing(general_data_values: dict[str, dict[str, str]]) -> list[str]:
    return [
        "General Data — " + (clean(item.get("label")) or clean(item.get("field_key")))
        for item in general_data_values.values()
        if not clean(item.get("requested_value"))
    ]


def _general_data_state(
    *,
    general_data_values: dict[str, dict[str, str]],
    general_data_duplicates: list[str],
    bank_attachments: list[dict[str, Any]],
    attachments: list[dict[str, Any]],
    bank_attachment_errors: list[str],
    attachment_errors: list[str],
) -> SectionStatus:
    """General Data is optional: grey until something is added."""
    return section_status(
        started=bool(general_data_values or bank_attachments or attachments),
        missing=len(_general_data_missing(general_data_values)) + len(bank_attachment_errors),
        invalid=len(general_data_duplicates)
        + len(attachment_errors)
        + len(_general_data_invalid_emails(general_data_values)),
    )


@dataclass(frozen=True)
class SectionStatus:
    """Colour of a section plus the short note shown in its header."""

    state: str  # neutral / error / check / complete
    note: str = ""


def section_status(
    *,
    missing: int = 0,
    invalid: int = 0,
    started: bool = True,
    reviewed: bool = True,
    done_note: str = "Complete",
    missing_note: str = "required missing",
) -> SectionStatus:
    """
    neutral   optional section, nothing entered yet (grey)
    error     a required value is missing or a value is invalid (red)
    check     nothing missing, but the requester has not opened the section
              yet to check the pre-filled values (purple)
    complete  everything required is filled in and valid (green)
    """
    if not started:
        return SectionStatus("neutral", "Optional")

    if missing or invalid:
        parts = []
        if missing:
            parts.append(f"{missing} {missing_note}")
        if invalid:
            parts.append(f"{invalid} invalid")
        return SectionStatus("error", " · ".join(parts))

    if not reviewed:
        return SectionStatus("check", "To check")

    return SectionStatus("complete", f"✓ {done_note}")


def _messages(
    missing: list[str],
    extra_errors: list[str],
    invalid_emails: list[str],
    *,
    missing_prefix: str,
) -> list[str]:
    messages: list[str] = []

    if missing:
        messages.append(missing_prefix + ", ".join(missing))

    messages.extend(extra_errors)

    if invalid_emails:
        messages.append(
            "Please enter a valid email address for: " + ", ".join(invalid_emails)
        )

    return messages


def _general_data_errors(
    general_data_duplicates: list[str],
    attachment_errors: list[str],
    bank_attachment_errors: list[str],
) -> list[str]:
    errors: list[str] = []

    if general_data_duplicates:
        errors.append(
            "General Data fields cannot be added twice: "
            + ", ".join(general_data_duplicates)
        )

    errors.extend(attachment_errors)
    errors.extend(bank_attachment_errors)
    return errors


# =============================================================================
# CREATE / EXTEND REQUESTS
# =============================================================================


def build_section_statuses(
    *,
    general_data_values: dict[str, dict[str, str]],
    general_data_duplicates: list[str],
    bank_attachments: list[dict[str, Any]],
    attachments: list[dict[str, Any]],
    bank_attachment_errors: list[str],
    attachment_errors: list[str],
    company_fields: pd.DataFrame,
    company_values: dict[str, Any],
    sales_fields: pd.DataFrame,
    sales_values: dict[str, Any],
    partner_fields: pd.DataFrame,
    partner_values: dict[str, Any],
    credit_fields: pd.DataFrame,
    credit_values: dict[str, Any],
    reviewed: Collection[str] = (),
) -> dict[str, SectionStatus]:
    """
    Red while a required value is missing or invalid. Once nothing is
    missing, "To check" until the requester has opened the section (reviewed
    holds the opened section keys), then green.
    """
    invalid = [key for key, _label in _invalid_emails(partner_values, credit_values)]
    credit_invalid = [key for key in invalid if key == COLLECTION_EMAIL[0]]

    return {
        "general_data": _general_data_state(
            general_data_values=general_data_values,
            general_data_duplicates=general_data_duplicates,
            bank_attachments=bank_attachments,
            attachments=attachments,
            bank_attachment_errors=bank_attachment_errors,
            attachment_errors=attachment_errors,
        ),
        "company_code": section_status(
            missing=len(_required_missing(company_fields, company_values)),
            reviewed="company_code" in reviewed,
        ),
        "sales_distribution": section_status(
            missing=len(_required_missing(sales_fields, sales_values)),
            reviewed="sales_distribution" in reviewed,
        ),
        "partner_functions": section_status(
            missing=len(_required_missing(partner_fields, partner_values))
            + len(_party_gaps(partner_values)),
            invalid=len(invalid) - len(credit_invalid),
            reviewed="partner_functions" in reviewed,
        ),
        "credit_management": section_status(
            missing=len(_required_missing(credit_fields, credit_values)),
            invalid=len(credit_invalid),
            reviewed="credit_management" in reviewed,
        ),
    }


def collect_validation_errors(
    *,
    fields: pd.DataFrame,
    company_values: dict[str, Any],
    sales_values: dict[str, Any],
    partner_values: dict[str, Any],
    credit_fields: pd.DataFrame,
    credit_values: dict[str, Any],
    general_data_values: dict[str, dict[str, str]],
    general_data_duplicates: list[str],
    attachment_errors: list[str],
    bank_attachment_errors: list[str],
) -> list[str]:
    values_by_section = {
        COMPANY_CODE: company_values,
        SALES_DISTRIBUTION: sales_values,
        PARTNER_FUNCTIONS: partner_values,
    }

    missing = _general_data_missing(general_data_values)

    for field in fields.to_dict("records"):
        if not is_yes(field.get("required")) or clean(field.get("input_type")).lower() == "computed":
            continue

        field_key = clean(field.get("field_key"))
        section_values = values_by_section.get(clean(field.get("section")), {})

        if not clean(section_values.get(field_key, "")):
            missing.append(clean(field.get("label")) or field_key)

    for field in credit_fields.to_dict("records"):
        if not is_yes(field.get("required")):
            continue

        field_key = clean(field.get("field_key"))

        if not clean(credit_values.get(field_key, "")):
            missing.append(clean(field.get("label")) or field_key)

    missing += [label for _key, label in _party_gaps(partner_values)]

    return _messages(
        missing,
        _general_data_errors(
            general_data_duplicates, attachment_errors, bank_attachment_errors
        ),
        _general_data_invalid_emails(general_data_values)
        + [label for _key, label in _invalid_emails(partner_values, credit_values)],
        missing_prefix="Please complete the required fields: ",
    )


# =============================================================================
# CHANGE REQUESTS
# =============================================================================


@dataclass(frozen=True)
class ChangeEntry:
    """One field the requester chose to change."""

    section_key: str
    section: str
    field_key: str
    label: str
    current_value: str
    requested_value: str
    # Tick boxes: an unticked box ("") is a valid new value
    allow_empty: bool = False

    @property
    def missing(self) -> bool:
        return not self.requested_value and not self.allow_empty


def _change_email_problems(entries: list[ChangeEntry]) -> list[ChangeEntry]:
    return [
        entry
        for entry in entries
        if is_email_field(entry.field_key)
        and entry.requested_value
        and not is_valid_email(entry.requested_value)
    ]


def build_change_section_statuses(
    *,
    general_data_values: dict[str, dict[str, str]],
    general_data_duplicates: list[str],
    bank_attachments: list[dict[str, Any]],
    attachments: list[dict[str, Any]],
    bank_attachment_errors: list[str],
    attachment_errors: list[str],
    entries_by_section: dict[str, list[ChangeEntry]],
) -> dict[str, SectionStatus]:
    """Nothing is required: a section is grey until a field is picked."""
    statuses = {
        "general_data": _general_data_state(
            general_data_values=general_data_values,
            general_data_duplicates=general_data_duplicates,
            bank_attachments=bank_attachments,
            attachments=attachments,
            bank_attachment_errors=bank_attachment_errors,
            attachment_errors=attachment_errors,
        )
    }

    for section_key, entries in entries_by_section.items():
        statuses[section_key] = section_status(
            started=bool(entries),
            missing=sum(entry.missing for entry in entries),
            invalid=len(_change_email_problems(entries)),
            done_note=f"{len(entries)} change" + ("" if len(entries) == 1 else "s"),
            missing_note="value missing" if sum(entry.missing for entry in entries) == 1 else "values missing",
        )

    return statuses


def collect_change_errors(
    *,
    general_data_values: dict[str, dict[str, str]],
    general_data_duplicates: list[str],
    attachment_errors: list[str],
    bank_attachment_errors: list[str],
    entries: list[ChangeEntry],
) -> list[str]:
    if not general_data_values and not entries:
        return ["Select at least one field to change before submitting."]

    missing = _general_data_missing(general_data_values)
    missing += [entry.label for entry in entries if entry.missing]

    return _messages(
        missing,
        _general_data_errors(
            general_data_duplicates, attachment_errors, bank_attachment_errors
        ),
        _general_data_invalid_emails(general_data_values)
        + [entry.label for entry in _change_email_problems(entries)],
        missing_prefix="Please enter a value for the fields you selected: ",
    )
