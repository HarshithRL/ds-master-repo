"""
HTML body of the requester's confirmation email (sent by the Power Automate flow).

AXIOM colours, table-based layout with inline styles so Outlook (desktop,
web and mobile) renders it the same way as other mail clients. Requesters do
not use the Workbench, so the email has no Workbench link.
"""

from __future__ import annotations

import html
from typing import Any

from portal.constants import (
    PARTNER_LABELS,
    PARTNER_NAME_FIELDS,
    PARTY_MODE_KEYS,
    SAME_AS_CUSTOMER,
)
from portal.core.utils import clean

# AXIOM palette (see portal/ui/theme.py)
NAVY = "#182033"
PURPLE = "#663BFF"
PURPLE_SOFT = "#F3EFFF"
PURPLE_LIGHT = "#B9AEFF"
PAGE = "#F7F8FA"
BORDER = "#E4E7EC"
TEXT = "#182033"
MUTED = "#667085"

FONT = "font-family:Segoe UI,Arial,Helvetica,sans-serif;"
TABLE = "role='presentation' cellpadding='0' cellspacing='0' border='0'"
CELL = f"{FONT}font-size:14px;line-height:20px;padding:8px 12px;border-bottom:1px solid {BORDER};vertical-align:top;"

PARTNER_ROW_LABELS = {**PARTNER_LABELS, **dict(PARTNER_NAME_FIELDS)}

STATUS_LABEL = "Needs review"  # how the Workbench shows a new (ASSIGNED) request


def _section(title: str, header_cells: list[str] | None, rows: list[list[str]]) -> str:
    """A titled table; cells are already-escaped HTML strings."""
    if not rows:
        return ""

    header = ""
    if header_cells:
        header = "<tr>" + "".join(
            f"<td style='{CELL}font-size:12px;font-weight:700;color:{MUTED};"
            f"text-transform:uppercase;letter-spacing:.04em;background:{PAGE};'>{cell}</td>"
            for cell in header_cells
        ) + "</tr>"

    body = "".join(
        "<tr>"
        + f"<td style='{CELL}font-weight:600;width:38%;color:{TEXT};'>{row[0]}</td>"
        + "".join(f"<td style='{CELL}color:{TEXT};'>{cell}</td>" for cell in row[1:])
        + "</tr>"
        for row in rows
    )

    return (
        f"<tr><td style='padding:22px 0 8px 0;{FONT}font-size:16px;font-weight:700;color:{NAVY};'>"
        f"{html.escape(title)}</td></tr>"
        f"<tr><td><table {TABLE} width='100%' style='border-collapse:collapse;"
        f"border:1px solid {BORDER};'>{header}{body}</table></td></tr>"
    )


def _key_value_section(title: str, values: dict[str, Any]) -> str:
    if not isinstance(values, dict):
        return ""

    rows = []

    for key, value in values.items():
        if isinstance(value, dict) or clean(value) == "":
            continue

        label = str(key).replace("_", " ").strip().title()
        if title == "Partner Functions":
            label = PARTNER_ROW_LABELS.get(str(key), label)

        rows.append([html.escape(label), html.escape(clean(value))])

    return _section(title, None, rows)


def _changes_section(change_request: Any) -> str:
    if not isinstance(change_request, list):
        return ""

    rows = [
        [
            html.escape(clean(item.get("field_label")) or clean(item.get("field_key")))
            + f"<br><span style='font-weight:400;font-size:12px;color:{MUTED};'>"
            + html.escape(clean(item.get("section")))
            + "</span>",
            html.escape(clean(item.get("current_value")) or "—"),
            f"<b style='color:{PURPLE};'>"
            + html.escape(clean(item.get("requested_value")) or "—")
            + "</b>",
        ]
        for item in change_request
        if isinstance(item, dict)
    ]

    return _section("Requested changes", ["Field", "Current value", "Requested value"], rows)


def _general_data_summary(general_data: Any) -> dict[str, str]:
    summary: dict[str, str] = {}

    if isinstance(general_data, dict):
        for item in general_data.values():
            if not isinstance(item, dict):
                continue
            label = clean(item.get("label")) or clean(item.get("field_key"))
            requested_value = clean(item.get("requested_value"))
            if label and requested_value:
                summary[label] = requested_value

    return summary


def build_confirmation_email_html(
    *,
    payload: dict[str, Any],
    request_id: str,
    assigned_to: str,
    requester_name: str,
) -> str:
    request_info = payload.get("request_information", {})
    change_request = payload.get("change_request")
    is_change = isinstance(change_request, list)

    # Show the customer ID instead of the SAME_AS_CUSTOMER code
    partner_data = dict(payload.get("partner_functions", {}))
    current_customer_id = clean(request_info.get("customer_id", ""))
    for mode_key in PARTY_MODE_KEYS:
        if clean(partner_data.get(mode_key, "")) == SAME_AS_CUSTOMER and current_customer_id:
            partner_data[mode_key] = current_customer_id

    credit_data = {
        key: value
        for key, value in payload.get("credit_management", {}).items()
        if key != "collection_contact"
    }

    comments = {
        str(key).replace("_", " ").title(): clean(value)
        for key, value in (payload.get("section_comments") or {}).items()
        if clean(value)
    }

    attachments = payload.get("attachments", [])
    files = ", ".join(
        clean(item.get("name"))
        for item in attachments
        if isinstance(item, dict) and clean(item.get("name"))
    ) if isinstance(attachments, list) else ""

    sections = _key_value_section("Request Information", request_info)

    if is_change:
        # The chosen fields, with their current values
        sections += _changes_section(change_request)

    sections += _key_value_section("General Data Requests", _general_data_summary(payload.get("general_data")))
    sections += _key_value_section("Existing Customer", payload.get("existing_customer", {}))

    if not is_change:
        sections += _key_value_section("Company Code", payload.get("company_code", {}))
        sections += _key_value_section("Sales & Distribution", payload.get("sales_distribution", {}))
        sections += _key_value_section("Partner Functions", partner_data)
        sections += _key_value_section("Credit Management", credit_data)

    sections += _key_value_section("Section Comments", comments)
    sections += _key_value_section("Attachments", {"Files": files})

    return (
        f"<table {TABLE} width='100%' bgcolor='{PAGE}' style='background:{PAGE};'>"
        f"<tr><td align='center' style='padding:24px 12px;'>"
        f"<table {TABLE} width='640' style='width:640px;max-width:640px;background:#FFFFFF;"
        f"border:1px solid {BORDER};border-collapse:separate;'>"
        # Header
        f"<tr><td bgcolor='{NAVY}' style='background:{NAVY};padding:22px 28px;"
        f"border-bottom:4px solid {PURPLE};'>"
        f"<div style='{FONT}font-size:12px;font-weight:700;letter-spacing:.2em;color:{PURPLE_LIGHT};'>AXIOM</div>"
        f"<div style='{FONT}font-size:22px;line-height:28px;font-weight:700;color:#FFFFFF;'>"
        f"Customer Master Data Request</div></td></tr>"
        # Body
        f"<tr><td style='padding:26px 28px 28px 28px;'>"
        f"<table {TABLE} width='100%'>"
        f"<tr><td style='{FONT}font-size:16px;color:{TEXT};padding-bottom:6px;'>"
        f"Hi {html.escape(requester_name)},</td></tr>"
        f"<tr><td style='{FONT}font-size:14px;line-height:21px;color:{TEXT};padding-bottom:18px;'>"
        f"Your customer master data request was submitted successfully.</td></tr>"
        # Request card
        f"<tr><td bgcolor='{PURPLE_SOFT}' style='background:{PURPLE_SOFT};"
        f"border-left:4px solid {PURPLE};padding:16px 18px;'>"
        f"<div style='{FONT}font-size:11px;font-weight:700;color:{MUTED};"
        f"text-transform:uppercase;letter-spacing:.08em;'>Request number</div>"
        f"<div style='{FONT}font-size:20px;line-height:28px;font-weight:700;color:{NAVY};'>"
        f"{html.escape(request_id)}</div>"
        f"<div style='{FONT}font-size:14px;color:{TEXT};padding-top:6px;'>"
        f"Status: <b>{STATUS_LABEL}</b> &nbsp;·&nbsp; Assigned to: <b>{html.escape(assigned_to)}</b>"
        f"</div></td></tr>"
        + sections
        + f"<tr><td style='{FONT}font-size:12px;line-height:18px;color:{MUTED};padding-top:26px;'>"
        f"This is an automated confirmation from the AXIOM Customer Request Portal."
        f"</td></tr>"
        f"</table></td></tr></table></td></tr></table>"
    )
