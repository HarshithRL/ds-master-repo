from __future__ import annotations

from typing import Any
import re

import pandas as pd

from .utils import clean, is_yes


EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


def _required_missing(
    section_fields: pd.DataFrame,
    values: dict[str, Any],
) -> list[str]:
    missing: list[str] = []

    for _, row in section_fields.iterrows():
        field = row.to_dict()

        if not is_yes(field.get("required")):
            continue

        field_key = clean(field.get("field_key"))
        if field_key and not clean(values.get(field_key, "")):
            missing.append(field_key)

    return missing


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
    submit_attempted: bool,
) -> dict[str, str]:
    company_missing = _required_missing(
        company_fields,
        company_values,
    )
    sales_missing = _required_missing(
        sales_fields,
        sales_values,
    )
    partner_missing = _required_missing(
        partner_fields,
        partner_values,
    )
    credit_missing = _required_missing(
        credit_fields,
        credit_values,
    )

    for mode_key, id_key, address_key in [
        (
            "bill_to_party_mode",
            "bill_to_party_id",
            "bill_to_party_address",
        ),
        (
            "payer_mode",
            "payer_id",
            "payer_address",
        ),
        (
            "ship_to_party_mode",
            "ship_to_party_id",
            "ship_to_party_address",
        ),
    ]:
        mode = clean(partner_values.get(mode_key, ""))

        if mode == "EXISTING_ID" and not clean(partner_values.get(id_key, "")):
            partner_missing.append(id_key)

        if mode == "NEW_ADDRESS" and not clean(partner_values.get(address_key, "")):
            partner_missing.append(address_key)

    for email_key in [
        "partner_yf_email",
        "partner_cp_email",
        "partner_yl_email",
    ]:
        value = clean(partner_values.get(email_key, ""))
        if value and not re.match(EMAIL_PATTERN, value):
            partner_missing.append(email_key)

    collection_email = clean(credit_values.get("collection_contact_email", ""))
    if collection_email and not re.match(
        EMAIL_PATTERN,
        collection_email,
    ):
        credit_missing.append("collection_contact_email")

    general_started = bool(general_data_values or bank_attachments or attachments)
    general_problem = bool(
        general_data_duplicates
        or bank_attachment_errors
        or attachment_errors
        or any(
            not clean(item.get("requested_value", ""))
            for item in general_data_values.values()
        )
    )

    def status(
        *,
        problem: bool,
        optional_untouched: bool = False,
    ) -> str:
        if optional_untouched:
            return "neutral"
        if problem:
            return "error" if submit_attempted else "attention"
        return "complete"

    return {
        "general_data": status(
            problem=general_problem,
            optional_untouched=not general_started,
        ),
        "company_code": status(problem=bool(company_missing)),
        "sales_distribution": status(problem=bool(sales_missing)),
        "partner_functions": status(problem=bool(partner_missing)),
        "credit_management": status(problem=bool(credit_missing)),
    }


def general_data_status(
    *,
    general_data_values: dict[str, dict[str, str]],
    general_data_duplicates: list[str],
    bank_attachments: list[dict[str, Any]],
    attachments: list[dict[str, Any]],
    bank_attachment_errors: list[str],
    attachment_errors: list[str],
) -> str:
    started = bool(general_data_values or bank_attachments or attachments)

    problem = bool(
        general_data_duplicates
        or bank_attachment_errors
        or attachment_errors
        or any(
            not clean(item.get("requested_value", ""))
            for item in general_data_values.values()
        )
    )

    if not started:
        return "neutral"

    return "attention" if problem else "complete"


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
    missing: list[str] = []
    extra_errors: list[str] = []

    if general_data_duplicates:
        extra_errors.append(
            "General Data fields cannot be added twice: "
            + ", ".join(general_data_duplicates)
        )

    for item in general_data_values.values():
        if not clean(item.get("requested_value")):
            missing.append(
                "General Data — "
                + (clean(item.get("label")) or clean(item.get("field_key")))
            )

    extra_errors.extend(attachment_errors)
    extra_errors.extend(bank_attachment_errors)

    for _, row in fields.iterrows():
        field = row.to_dict()

        if not is_yes(field.get("required")):
            continue

        section = clean(field.get("section"))
        field_key = clean(field.get("field_key"))

        if section == "Company Code":
            value = company_values.get(field_key, "")
        elif section == "Sales & Distribution":
            value = sales_values.get(field_key, "")
        elif section == "Partner Functions":
            value = partner_values.get(field_key, "")
        else:
            value = ""

        if not clean(value):
            missing.append(clean(field.get("label")) or field_key)

    for _, row in credit_fields.iterrows():
        field = row.to_dict()

        if not is_yes(field.get("required")):
            continue

        field_key = clean(field.get("field_key"))
        value = credit_values.get(field_key, "")

        if not clean(value):
            missing.append(clean(field.get("label")) or field_key)

    for party_label, mode_key, id_key, address_key in [
        (
            "Bill-to Party",
            "bill_to_party_mode",
            "bill_to_party_id",
            "bill_to_party_address",
        ),
        (
            "Payer",
            "payer_mode",
            "payer_id",
            "payer_address",
        ),
        (
            "Ship-to Party",
            "ship_to_party_mode",
            "ship_to_party_id",
            "ship_to_party_address",
        ),
    ]:
        mode = clean(partner_values.get(mode_key, ""))

        if mode == "EXISTING_ID" and not clean(partner_values.get(id_key, "")):
            missing.append(f"{party_label} Existing ID")

        if mode == "NEW_ADDRESS" and not clean(partner_values.get(address_key, "")):
            missing.append(f"{party_label} New Address")

    invalid_emails: list[str] = []

    for field_key, label in [
        ("partner_yf_email", "Invoice Email Address (YF)"),
        ("partner_cp_email", "Contact Person Email (CP)"),
        ("partner_yl_email", "Logistics Contact Email (YL)"),
    ]:
        value = clean(partner_values.get(field_key, ""))
        if value and not re.match(EMAIL_PATTERN, value):
            invalid_emails.append(label)

    collection_email = clean(credit_values.get("collection_contact_email"))
    if collection_email and not re.fullmatch(
        EMAIL_PATTERN,
        collection_email,
    ):
        invalid_emails.append("Collection Contact Email")

    messages: list[str] = []

    if missing:
        messages.append("Please complete the required fields: " + ", ".join(missing))

    messages.extend(extra_errors)

    if invalid_emails:
        messages.append(
            "Please enter a valid email address for: " + ", ".join(invalid_emails)
        )

    return messages
