"""
Power Automate notification flow.

One HTTP POST to the flow in NOTIFICATION_FLOW_URL (fallback TEAMS_FLOW_URL)
after every submit. The flow sends:
  - a Teams message (teams_message) to the assigned MDM member, ending with a
    direct link that opens this request in the Workbench
  - an Outlook confirmation (email_subject / email_body_html) to the requester

workbench_url / request_url hold that direct link. The original keys are the
flow's trigger schema; keep them unchanged (request_url is an extra key the
flow may use, e.g. for a Teams button).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import requests

from portal.config import setting
from portal.core.links import workbench_request_url
from portal.core.email import build_confirmation_email_html
from portal.core.identity import requester_email, requester_name
from portal.core.utils import clean


@dataclass(frozen=True)
class NotificationResult:
    sent: bool
    requester_email: str = ""
    assignee_email: str = ""
    error: str = ""


def flow_url() -> str:
    return setting("NOTIFICATION_FLOW_URL") or setting("TEAMS_FLOW_URL")


def build_flow_body(
    *,
    assignee: dict[str, str],
    request_id: str,
    customer_name: str,
    customer_id: str,
    company_code: str,
    sales_org: str,
    message: str,
    payload: dict[str, Any],
    request_headers: Mapping[str, str] | None,
) -> dict[str, str]:
    name = requester_name(request_headers)
    request_url = workbench_request_url(request_id)

    # Append the link unless the message template already contains it
    teams_message = message
    if request_url and request_url not in message:
        teams_message = f"{message}\n\nOpen the request in the Workbench: {request_url}"

    return {
        "assignee_name": assignee["display_name"],
        "assignee_email": clean(assignee.get("email")),
        "requester_name": name,
        "requester_email": requester_email(request_headers),
        "request_id": request_id,
        "customer_name": customer_name,
        "customer_id": customer_id,
        "company_code": company_code,
        "sales_org": sales_org,
        "teams_message": teams_message,
        "workbench_url": request_url,
        "email_subject": f"Customer request submitted — {request_id}",
        "email_body_html": build_confirmation_email_html(
            payload=payload,
            request_id=request_id,
            assigned_to=assignee["display_name"],
            requester_name=name,
        ),
        "request_url": request_url,
    }


def send_submission_notifications(**kwargs: Any) -> NotificationResult:
    """
    POST the notification to the flow (arguments as build_flow_body).

    Never raises: the request is already stored when this runs, so a flow
    problem is reported back instead of failing the submission.
    """
    url = flow_url()

    if not url:
        return NotificationResult(sent=False)

    body = build_flow_body(**kwargs)

    try:
        response = requests.post(url, json=body, timeout=30)
    except requests.RequestException as exc:
        return NotificationResult(sent=False, error=f"Power Automate flow unreachable: {exc}")

    if not response.ok:
        return NotificationResult(
            sent=False,
            error=(
                "Power Automate notification flow failed "
                f"(HTTP {response.status_code}): {response.text[:300]}"
            ),
        )

    return NotificationResult(
        sent=True,
        requester_email=body["requester_email"],
        assignee_email=body["assignee_email"],
    )
