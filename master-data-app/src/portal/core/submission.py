"""Assign a submitted request to an MDM member and record it."""

from __future__ import annotations

import random
import uuid
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from portal.config import DEMO_MODE
from portal.core.customers import customer_display_name
from portal.core.identity import Headers, requester_email
from portal.core.links import workbench_request_url
from portal.core.storage import save_demo_request
from portal.core.utils import active_rows, clean, column_text

DEFAULT_MESSAGE = "{name}, a new customer request {request_id} is assigned to you."

# =============================================================================
# ASSIGNMENT
# =============================================================================


def _member(member: Any, member_id: str | None = None) -> dict[str, str] | None:
    display_name = clean(member.get("display_name"))
    if not display_name:
        return None

    return {
        "member_id": member_id if member_id is not None else clean(member.get("member_id")),
        "display_name": display_name,
        "email": clean(member.get("email")),
    }


def _assignment_candidates(
    *,
    company_code: str,
    sales_org: str,
    assignment_rules: dict[str, pd.DataFrame],
) -> list[dict[str, str]]:
    """Pool members for the Company Code + Sales Org, else every member."""
    members = active_rows(assignment_rules["members"])
    pool = active_rows(assignment_rules["pool"])

    exact_pool = pool[
        (column_text(pool, "company_code") == clean(company_code))
        & (column_text(pool, "sales_org") == clean(sales_org))
    ]

    if exact_pool.empty:
        candidates = [_member(member) for _, member in members.iterrows()]
        return [candidate for candidate in candidates if candidate]

    candidates = []

    for _, pool_row in exact_pool.iterrows():
        member_id = clean(pool_row.get("member_id"))
        match = members[column_text(members, "member_id") == member_id]
        if match.empty:
            continue

        candidate = _member(match.iloc[0], member_id)
        if candidate:
            candidates.append(candidate)

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
    """A random active template from Notification_Messages, filled in."""
    messages = active_rows(assignment_rules["messages"])
    templates = [
        clean(value) for value in messages["message_template"].tolist() if clean(value)
    ] or [DEFAULT_MESSAGE]

    return random.choice(templates).format(
        name=assignee["display_name"],
        request_id=request_id,
        customer=customer_name,
        customer_id=customer_id,
        company_code=company_code,
        sales_org=sales_org,
        workbench_url=workbench_request_url(request_id),
    )


# =============================================================================
# SUBMIT
# =============================================================================


def new_request_id(now: datetime) -> str:
    return "REQ-" + now.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6].upper()


def submit_to_master_data(
    *,
    payload: dict[str, Any],
    original_defaults: dict[str, Any],
    assignment_rules: dict[str, pd.DataFrame],
    request_headers: Headers | None = None,
) -> dict[str, Any]:
    """
    Create the request reference, pick the assignee, store the request and
    notify through the Power Automate flow.

    Demo mode stores the request in demo_requests.jsonl; otherwise it goes to
    the Databricks table read by the Customer Master Workbench. The flow is
    called in both modes whenever NOTIFICATION_FLOW_URL is configured.
    """
    # Imported here so the logic layer loads without the HTTP integrations
    from portal.integrations.power_automate import send_submission_notifications
    from portal.integrations.workbench import save_request_for_workbench

    request_info = payload.get("request_information", {})
    company_code = clean(request_info.get("company_code", ""))
    sales_org = clean(request_info.get("sales_org", ""))
    customer_id = clean(request_info.get("customer_id", ""))

    existing_customer = payload.get("existing_customer", {})
    customer_name = clean(existing_customer.get("name_1", "")) or clean(
        existing_customer.get("customer_name", "")
    )

    assignee = choose_assignee(
        company_code=company_code,
        sales_org=sales_org,
        assignment_rules=assignment_rules,
    )

    now = datetime.now(timezone.utc)
    request_id = new_request_id(now)

    notification_message = choose_notification_message(
        assignment_rules=assignment_rules,
        assignee=assignee,
        request_id=request_id,
        customer_name=customer_name,
        customer_id=customer_id,
        company_code=company_code,
        sales_org=sales_org,
    )

    if DEMO_MODE:
        save_demo_request(
            request_id=request_id,
            requested_by=requester_email(request_headers),
            payload=payload,
            original_defaults=original_defaults,
            assignee=assignee,
            requested_at=now,
        )
    else:
        save_request_for_workbench(
            request_id=request_id,
            payload=payload,
            original_defaults=original_defaults,
            assignee=assignee,
            requested_at=now,
            customer_name=customer_display_name(existing_customer),
            request_headers=request_headers,
        )

    notification = send_submission_notifications(
        assignee=assignee,
        request_id=request_id,
        customer_name=customer_name,
        customer_id=customer_id,
        company_code=company_code,
        sales_org=sales_org,
        message=notification_message,
        payload=payload,
        request_headers=request_headers,
    )

    return {
        "request_id": request_id,
        "assigned_to": assignee["display_name"],
        "assigned_email": assignee.get("email", ""),
        "notification_message": notification_message,
        "teams_sent": notification.sent,
        "notified_requester": notification.requester_email,
        "notification_error": notification.error,
    }
