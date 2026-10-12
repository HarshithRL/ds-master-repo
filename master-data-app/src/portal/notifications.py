from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import html
import os
import random
import uuid
import json

import pandas as pd
import requests
import streamlit as st

from .utils import active_rows, clean

from config import REQUEST_TABLE
from sql_client import execute_sql_statement


def _current_request_user() -> str:
    """Best-effort user label for audit fields."""
    headers = st.context.headers

    for header_name in (
        "x-forwarded-email",
        "x-forwarded-preferred-username",
        "x-forwarded-user",
    ):
        value = clean(headers.get(header_name))
        if value:
            return value

    return "Databricks App User"


def _current_request_email() -> str:
    """Return the logged-in requester's email when Databricks provides it."""
    headers = st.context.headers

    for header_name in (
        "x-forwarded-email",
        "x-forwarded-preferred-username",
    ):
        value = clean(headers.get(header_name))
        if "@" in value:
            return value

    user_value = _current_request_user()
    return user_value if "@" in user_value else ""


def _current_request_name() -> str:
    """Friendly fallback name for notification content."""
    email = _current_request_email()
    if email:
        local_part = email.split("@", 1)[0]
        return local_part.replace(".", " ").replace("_", " ").title()

    return _current_request_user()


def _email_rows(title: str, values: dict[str, Any]) -> str:
    if not isinstance(values, dict) or not values:
        return ""

    rows: list[str] = []

    for key, value in values.items():
        if isinstance(value, dict):
            continue

        value_text = clean(value)
        if value_text == "":
            continue

        label = str(key).replace("_", " ").strip().title()

        if title == "Partner Functions":
            partner_email_labels = {
                "partner_yf_email": "Invoice Email Address (YF)",
                "partner_cp_email": "Contact Person Email (CP)",
                "partner_cp_name": "Contact Person Name (CP)",
                "partner_yl_email": "Logistics Contact Email (YL)",
                "partner_yl_name": "Logistics Contact Name (YL)",
                "partner_yb_employee_id": "Sales Rep Employee ID (YB)",
                "partner_yz_employee_id": "Customer Service Employee ID (YZ)",
                "bill_to_party_mode": "Bill-to Party (BP)",
                "bill_to_party_id": "Bill-to Party ID (BP)",
                "bill_to_party_address": "Bill-to Party Address (BP)",
                "payer_mode": "Payer (PY)",
                "payer_id": "Payer ID (PY)",
                "payer_address": "Payer Address (PY)",
                "ship_to_party_mode": "Ship-to Party (SH)",
                "ship_to_party_id": "Ship-to Party ID (SH)",
                "ship_to_party_address": "Ship-to Party Address (SH)",
            }
            label = partner_email_labels.get(str(key), label)

        rows.append(
            "<tr>"
            f"<td style='padding:7px 10px;border-bottom:1px solid #e7e7e7;"
            "font-weight:600;width:38%;vertical-align:top;'>"
            f"{html.escape(label)}</td>"
            f"<td style='padding:7px 10px;border-bottom:1px solid #e7e7e7;"
            "vertical-align:top;'>"
            f"{html.escape(value_text)}</td>"
            "</tr>"
        )

    if not rows:
        return ""

    return (
        "<div style='margin-top:20px;'>"
        f"<h3 style='margin:0 0 8px 0;color:#222222;'>{html.escape(title)}</h3>"
        "<table style='border-collapse:collapse;width:100%;font-size:14px;'>"
        + "".join(rows)
        + "</table></div>"
    )


def build_confirmation_email_html(
    *,
    payload: dict[str, Any],
    request_id: str,
    assigned_to: str,
) -> str:
    request_info = payload.get("request_information", {})
    existing_customer = payload.get("existing_customer", {})
    company_data = payload.get("company_code", {})
    sales_data = payload.get("sales_distribution", {})
    credit_data = {
        key: value
        for key, value in payload.get("credit_management", {}).items()
        if key != "collection_contact"
    }
    partner_data = dict(payload.get("partner_functions", {}))

    current_customer_id = clean(request_info.get("customer_id", ""))

    for mode_key in (
        "bill_to_party_mode",
        "payer_mode",
        "ship_to_party_mode",
    ):
        if (
            clean(partner_data.get(mode_key, "")) == "SAME_AS_CUSTOMER"
            and current_customer_id
        ):
            partner_data[mode_key] = current_customer_id

    general_data = payload.get("general_data", {})
    section_comments = payload.get("section_comments", {})
    attachments = payload.get("attachments", [])

    general_data_summary: dict[str, str] = {}
    if isinstance(general_data, dict):
        for item in general_data.values():
            if not isinstance(item, dict):
                continue
            label = clean(item.get("label")) or clean(item.get("field_key"))
            requested_value = clean(item.get("requested_value"))
            if label and requested_value:
                general_data_summary[label] = requested_value

    comments_summary: dict[str, str] = {}
    if isinstance(section_comments, dict):
        for key, value in section_comments.items():
            value_text = clean(value)
            if value_text:
                comments_summary[str(key).replace("_", " ").title()] = value_text

    attachment_summary = (
        {
        "Files": ", ".join(
        clean(item.get("name"))
        for item in attachments
        if isinstance(item, dict) and clean(item.get("name"))
    )
    }
        if isinstance(attachments, list)
        else {}
    )

    workbench_url = clean(os.environ.get("WORKBENCH_URL", ""))
    open_link = (
        f"<p style='margin-top:22px;'><a href='{html.escape(workbench_url)}' "
        "style='background:#EB6910;color:#ffffff;text-decoration:none;"
        "padding:10px 16px;border-radius:4px;font-weight:600;'>"
        "Open Customer Master Workbench</a></p>"
        if workbench_url
        else ""
    )

    return (
        "<div style='font-family:Segoe UI,Arial,sans-serif;color:#222222;"
        "max-width:760px;margin:auto;'>"
        "<div style='background:#0B0B0B;padding:20px 24px;border-bottom:5px solid #EB6910;'>"
        "<div style='color:#ffffff;font-size:23px;font-weight:700;'>"
        "Customer Master Data Request</div></div>"
        "<div style='padding:24px;border:1px solid #dedede;border-top:0;'>"
        f"<p style='font-size:16px;margin-top:0;'>Hi {html.escape(_current_request_name())},</p>"
        "<p>Your customer master data request was submitted successfully.</p>"
        "<div style='background:#F5F5F3;border-left:5px solid #EB6910;"
        "padding:14px 16px;margin:18px 0;'>"
        "<div style='font-size:12px;color:#666666;text-transform:uppercase;"
        "letter-spacing:.08em;'>Request number</div>"
        f"<div style='font-size:20px;font-weight:700;'>{html.escape(request_id)}</div>"
        f"<div style='margin-top:8px;'>Status: <b>NEEDS REVIEW</b> &nbsp;·&nbsp; "
        f"Assigned to: <b>{html.escape(assigned_to)}</b></div>"
        "</div>"
        + _email_rows("Request Information", request_info)
        + _email_rows("General Data Requests", general_data_summary)
        + _email_rows("Existing Customer", existing_customer)
        + _email_rows("Company Code", company_data)
        + _email_rows("Sales & Distribution", sales_data)
        + _email_rows("Partner Functions", partner_data)
        + _email_rows("Credit Management", credit_data)
        + _email_rows("Section Comments", comments_summary)
        + _email_rows("Attachments", attachment_summary)
        + open_link
        + "<p style='margin-top:26px;color:#777777;font-size:12px;'>"
        "This is an automated confirmation from the Customer Request Portal."
        "</p></div></div>"
    )


def _assignment_candidates(
    *,
    company_code: str,
    sales_org: str,
    assignment_rules: dict[str, pd.DataFrame],
) -> list[dict[str, str]]:
    members = active_rows(assignment_rules["members"])
    pool = active_rows(assignment_rules["pool"])

    exact_pool = pool[
        (pool["company_code"].astype(str).str.strip() == clean(company_code))
        & (pool["sales_org"].astype(str).str.strip() == clean(sales_org))
    ]

    candidates: list[dict[str, str]] = []

    if exact_pool.empty:
        for _, member in members.iterrows():
            display_name = clean(member.get("display_name"))
            if not display_name:
                continue
            candidates.append(
                {
                "member_id": clean(member.get("member_id")),
                "display_name": display_name,
                "email": clean(member.get("email")),
            }
            )
        return candidates

    for _, pool_row in exact_pool.iterrows():
        member_id = clean(pool_row.get("member_id"))
        match = members[members["member_id"].astype(str).str.strip() == member_id]
        if match.empty:
            continue

        member = match.iloc[0]
        display_name = clean(member.get("display_name"))
        if not display_name:
            continue

        candidates.append(
            {
            "member_id": member_id,
            "display_name": display_name,
            "email": clean(member.get("email")),
        }
        )

    return candidates


def choose_assignee(
    *,
    company_code: str,
    sales_org: str,
    assignment_rules: dict[str, pd.DataFrame],
) -> dict[str, str]:
    candidates = _assignment_candidates(
        company_code=company_code,
        sales_org=sales_org,
        assignment_rules=assignment_rules,
    )

    if not candidates:
        raise RuntimeError(
            "No active MDM assignment members are configured for "
            f"Company Code {company_code} + Sales Org {sales_org}."
        )

    return random.choice(candidates)


def choose_notification_message(
    *,
    assignment_rules: dict[str, pd.DataFrame],
    assignee: dict[str, str],
    request_id: str,
    customer_name: str,
    customer_id: str,
    company_code: str,
    sales_org: str,
) -> str:
    messages = active_rows(assignment_rules["messages"])
    templates = [
        clean(value) for value in messages["message_template"].tolist() if clean(value)
    ]

    if not templates:
        templates = ["{name}, a new customer request {request_id} is assigned to you."]

    template = random.choice(templates)

    return template.format(
        name=assignee["display_name"],
        request_id=request_id,
        customer=customer_name,
        customer_id=customer_id,
        company_code=company_code,
        sales_org=sales_org,
        workbench_url=clean(os.environ.get("WORKBENCH_URL", "")),
    )


def send_submission_notifications(
    *,
    assignee: dict[str, str],
    request_id: str,
    customer_name: str,
    customer_id: str,
    company_code: str,
    sales_org: str,
    message: str,
    payload: dict[str, Any],
) -> bool:
    flow_url = clean(os.environ.get("NOTIFICATION_FLOW_URL", "")) or clean(
        os.environ.get("TEAMS_FLOW_URL", "")
    )

    if not flow_url:
        return False

    requester_email = _current_request_email()
    requester_name = _current_request_name()
    assignee_email = clean(assignee.get("email"))
    workbench_url = clean(os.environ.get("WORKBENCH_URL", ""))

    email_subject = f"Customer request submitted — {request_id}"
    email_body_html = build_confirmation_email_html(
        payload=payload,
        request_id=request_id,
        assigned_to=assignee["display_name"],
    )

    response = requests.post(
        flow_url,
        json={
        "assignee_name": assignee["display_name"],
        "assignee_email": assignee_email,
        "requester_name": requester_name,
        "requester_email": requester_email,
        "request_id": request_id,
        "customer_name": customer_name,
        "customer_id": customer_id,
        "company_code": company_code,
        "sales_org": sales_org,
        "teams_message": message,
        "workbench_url": workbench_url,
        "email_subject": email_subject,
        "email_body_html": email_body_html,
    },
        timeout=30,
    )

    if not response.ok:
        raise RuntimeError(
            "Power Automate notification flow failed "
            f"(HTTP {response.status_code}): {response.text}"
        )

    return True


def save_request_to_databricks(
    *,
    request_id: str,
    payload: dict[str, Any],
    original_defaults: dict[str, Any],
    assignee: dict[str, str],
    requested_at: datetime,
) -> None:
    """Save the complete submitted request for the Master Data Workbench."""

    request_info = payload.get(
        "request_information",
        {},
    )

    existing_customer = payload.get(
        "existing_customer",
        {},
    )

    request_type = clean(
        request_info.get(
        "request_type",
        "",
    )
    )

    customer_id = clean(
        request_info.get(
        "customer_id",
        "",
    )
    )

    customer_name = (
        clean(existing_customer.get("name_1", ""))
        or clean(existing_customer.get("customer_name", ""))
        or clean(existing_customer.get("name", ""))
    )

    company_code = clean(
        request_info.get(
        "company_code",
        "",
    )
    )

    sales_org = clean(
        request_info.get(
        "sales_org",
        "",
    )
    )

    requested_by = _current_request_email() or _current_request_user()

    section_comments = payload.get(
        "section_comments",
        {},
    )

    business_justification = clean(
        section_comments.get(
        "request_information",
        "",
    )
    )

    payload_json = json.dumps(
        payload,
        ensure_ascii=False,
        default=str,
    )

    original_defaults_json = json.dumps(
        original_defaults,
        ensure_ascii=False,
        default=str,
    )

    statement = f"""
    INSERT INTO {REQUEST_TABLE}
    (
        request_id,
        request_type,
        customer_id,
        customer_name,
        company_code,
        sales_org,
        status,
        assigned_to,
        requested_by,
        requested_at,
        updated_at,
        business_justification,
        payload_json,
        original_defaults_json
    )
    VALUES
    (
        :request_id,
        :request_type,
        :customer_id,
        :customer_name,
        :company_code,
        :sales_org,
        :status,
        :assigned_to,
        :requested_by,
        :requested_at,
        :updated_at,
        :business_justification,
        :payload_json,
        :original_defaults_json
    )
    """

    timestamp_value = requested_at.isoformat()

    execute_sql_statement(
        statement,
        parameters=[
        {
        "name": "request_id",
        "value": request_id,
        "type": "STRING",
    },
        {
        "name": "request_type",
        "value": request_type,
        "type": "STRING",
    },
        {
        "name": "customer_id",
        "value": customer_id,
        "type": "STRING",
    },
        {
        "name": "customer_name",
        "value": customer_name,
        "type": "STRING",
    },
        {
        "name": "company_code",
        "value": company_code,
        "type": "STRING",
    },
        {
        "name": "sales_org",
        "value": sales_org,
        "type": "STRING",
    },
        {
        "name": "status",
        "value": "ASSIGNED",
        "type": "STRING",
    },
        {
        "name": "assigned_to",
        "value": clean(assignee.get("display_name")),
        "type": "STRING",
    },
        {
        "name": "requested_by",
        "value": requested_by,
        "type": "STRING",
    },
        {
        "name": "requested_at",
        "value": timestamp_value,
        "type": "TIMESTAMP",
    },
        {
        "name": "updated_at",
        "value": timestamp_value,
        "type": "TIMESTAMP",
    },
        {
        "name": "business_justification",
        "value": business_justification,
        "type": "STRING",
    },
        {
        "name": "payload_json",
        "value": payload_json,
        "type": "STRING",
    },
        {
        "name": "original_defaults_json",
        "value": original_defaults_json,
        "type": "STRING",
    },
    ],
    )


def submit_to_master_data(
    *,
    payload: dict[str, Any],
    original_defaults: dict[str, Any],
    assignment_rules: dict[str, pd.DataFrame],
) -> dict[str, Any]:
    """Create a test request reference and trigger notifications."""
    request_info = payload.get("request_information", {})
    existing_customer = payload.get("existing_customer", {})

    company_code = clean(request_info.get("company_code", ""))
    sales_org = clean(request_info.get("sales_org", ""))

    assignee = choose_assignee(
        company_code=company_code,
        sales_org=sales_org,
        assignment_rules=assignment_rules,
    )

    now = datetime.now(timezone.utc)
    request_id = (
        "REQ-" + now.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6].upper()
    )

    customer_name = clean(existing_customer.get("name_1", "")) or clean(
        existing_customer.get("customer_name", "")
    )
    customer_id = clean(request_info.get("customer_id", ""))

    notification_message = choose_notification_message(
        assignment_rules=assignment_rules,
        assignee=assignee,
        request_id=request_id,
        customer_name=customer_name,
        customer_id=customer_id,
        company_code=company_code,
        sales_org=sales_org,
    )

        # ---------------------------------------------------------------------
        # Save request to Databricks
        # ---------------------------------------------------------------------

    save_request_to_databricks(
        request_id=request_id,
        payload=payload,
        original_defaults=original_defaults,
        assignee=assignee,
        requested_at=now,
    )

    # ---------------------------------------------------------------------
    # Send notifications
    # ---------------------------------------------------------------------

    teams_sent = send_submission_notifications(
        assignee=assignee,
        request_id=request_id,
        customer_name=customer_name,
        customer_id=customer_id,
        company_code=company_code,
        sales_org=sales_org,
        message=notification_message,
        payload=payload,
    )

    return {
        "request_id": request_id,
        "assigned_to": assignee["display_name"],
        "assigned_email": assignee.get("email", ""),
        "notification_message": notification_message,
        "teams_sent": teams_sent,
    }
