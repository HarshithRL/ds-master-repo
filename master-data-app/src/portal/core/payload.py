"""Build the request payload and original values sent to Master Data."""

from __future__ import annotations

from typing import Any

from portal.constants import CREDIT_MANAGEMENT
from portal.core.validation import ChangeEntry


def request_information(
    *,
    request_type: str,
    customer_id: str,
    company_code: str,
    sales_org: str,
) -> dict[str, str]:
    return {
        "request_type": request_type,
        "customer_id": customer_id,
        "company_code": company_code,
        "sales_org": sales_org,
    }


def _credit_context(
    company_code: str,
    credit_mapping: dict[str, str] | None,
) -> dict[str, str]:
    mapping = credit_mapping or {}
    return {
        "company_code": company_code,
        "ps4": mapping.get("ps4", ""),
        "mapping_id": mapping.get("mapping_id", ""),
        "company_name": mapping.get("company_name", ""),
    }


def build_request_payload(
    *,
    request_info: dict[str, str],
    customer: dict[str, str],
    general_data_values: dict[str, dict[str, str]],
    section_values: dict[str, dict[str, str]],
    section_comments: dict[str, str],
    attachments: list[dict[str, Any]],
    credit_mapping: dict[str, str] | None,
) -> dict[str, Any]:
    """Create / Extend payload; section_values is keyed like SECTION_KEYS."""
    return {
        "request_information": request_info,
        "general_data": general_data_values,
        "existing_customer": customer,
        "company_code": section_values["company_code"],
        "sales_distribution": section_values["sales_distribution"],
        "partner_functions": section_values["partner_functions"],
        "credit_management": section_values["credit_management"],
        "section_comments": section_comments,
        "attachments": attachments,
        "credit_management_context": _credit_context(
            request_info["company_code"],
            credit_mapping,
        ),
    }


def build_original_defaults(
    rule_defaults: dict[str, dict[str, str]],
    credit_defaults: dict[str, str],
) -> dict[str, dict[str, str]]:
    return {**rule_defaults, CREDIT_MANAGEMENT: credit_defaults}


# =============================================================================
# CHANGE REQUESTS
# =============================================================================


def build_change_payload(
    *,
    request_info: dict[str, str],
    customer: dict[str, str],
    general_data_values: dict[str, dict[str, str]],
    entries: list[ChangeEntry],
    section_comments: dict[str, str],
    attachments: list[dict[str, Any]],
    credit_mapping: dict[str, str] | None,
) -> dict[str, Any]:
    """
    Same shape as a Create / Extend payload, holding only the chosen fields,
    plus a "change_request" list describing each change.
    """
    section_values: dict[str, dict[str, str]] = {
        "company_code": {},
        "sales_distribution": {},
        "partner_functions": {},
        "credit_management": {},
    }

    for entry in entries:
        section_values[entry.section_key][entry.field_key] = entry.requested_value

    payload = build_request_payload(
        request_info=request_info,
        customer=customer,
        general_data_values=general_data_values,
        section_values=section_values,
        section_comments=section_comments,
        attachments=attachments,
        credit_mapping=credit_mapping,
    )

    payload["change_request"] = [
        {
            "section": entry.section,
            "field_key": entry.field_key,
            "field_label": entry.label,
            "current_value": entry.current_value,
            "requested_value": entry.requested_value,
        }
        for entry in entries
    ]

    return payload


def build_change_original_defaults(
    entries: list[ChangeEntry],
) -> dict[str, dict[str, str]]:
    """{section: {field_key: current value}} for the chosen fields."""
    result: dict[str, dict[str, str]] = {}

    for entry in entries:
        result.setdefault(entry.section, {})[entry.field_key] = entry.current_value

    return result
