"""Section status colours and submit-time validation messages."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

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
        and clean(field.get("input_type")).lower() != CHECKBOX
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
) -> tuple[bool, bool]:
    """(started, has_problem) for the optional General Data section."""
    started = bool(general_data_values or bank_attachments or attachments)
    problem = bool(
        general_data_duplicates
        or bank_attachment_errors
        or attachment_errors
        or _general_data_missing(general_data_values)
        or _general_data_invalid_emails(general_data_values)
    )
    return started, problem


def section_status(
    *,
    problem: bool,
    optional_untouched: bool = False,
) -> str:
    """neutral (optional, untouched) / error (required value missing or invalid) / complete."""
    if optional_untouched:
        return "neutral"
    return "error" if problem else "complete"


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
) -> dict[str, str]:
    partner_missing = _required_missing(partner_fields, partner_values)
    partner_missing += [key for key, _label in _party_gaps(partner_values)]
    credit_missing = _required_missing(credit_fields, credit_values)

    for key, _label in _invalid_emails(partner_values, credit_values):
        if key == COLLECTION_EMAIL[0]:
            credit_missing.append(key)
        else:
            partner_missing.append(key)

    general_started, general_problem = _general_data_state(
        general_data_values=general_data_values,
        general_data_duplicates=general_data_duplicates,
        bank_attachments=bank_attachments,
        attachments=attachments,
        bank_attachment_errors=bank_attachment_errors,
        attachment_errors=attachment_errors,
    )

    def status(problem: bool, optional_untouched: bool = False) -> str:
        return section_status(problem=problem, optional_untouched=optional_untouched)

    return {
        "general_data": status(general_problem, optional_untouched=not general_started),
        "company_code": status(bool(_required_missing(company_fields, company_values))),
        "sales_distribution": status(bool(_required_missing(sales_fields, sales_values))),
        "partner_functions": status(bool(partner_missing)),
        "credit_management": status(bool(credit_missing)),
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
        if not is_yes(field.get("required")):
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
) -> dict[str, str]:
    """Nothing is required: a section is neutral until a field is picked."""
    general_started, general_problem = _general_data_state(
        general_data_values=general_data_values,
        general_data_duplicates=general_data_duplicates,
        bank_attachments=bank_attachments,
        attachments=attachments,
        bank_attachment_errors=bank_attachment_errors,
        attachment_errors=attachment_errors,
    )

    statuses = {
        "general_data": section_status(
            problem=general_problem,
            optional_untouched=not general_started,
        )
    }

    for section_key, entries in entries_by_section.items():
        statuses[section_key] = section_status(
            problem=bool(
                any(entry.missing for entry in entries)
                or _change_email_problems(entries)
            ),
            optional_untouched=not entries,
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
