"""
Hand a submitted request to the Customer Master Workbench.

The Workbench (axiom-workbench) lists and reviews the rows of
REQUEST_TABLE (payload_json, original_defaults_json) and records its own
changes in the history table. Status ASSIGNED is shown there as "Needs review".
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Mapping

from portal.config import REQUEST_TABLE
from portal.core.identity import requester_email, requester_user
from portal.core.utils import clean
from portal.integrations.databricks_sql import execute_sql, result_rows, sql_parameter

INITIAL_STATUS = "ASSIGNED"

INSERT_REQUEST_SQL = f"""
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

def save_request_for_workbench(
    *,
    request_id: str,
    payload: dict[str, Any],
    original_defaults: dict[str, Any],
    assignee: dict[str, str],
    requested_at: datetime,
    customer_name: str,
    request_headers: Mapping[str, str] | None,
) -> None:
    """Insert the complete request (payload + original values) for review."""
    request_info = payload.get("request_information", {})
    section_comments = payload.get("section_comments", {})
    timestamp_value = requested_at.isoformat()
    requested_by = requester_email(request_headers) or requester_user(request_headers)

    values = {
        "request_id": request_id,
        "request_type": clean(request_info.get("request_type", "")),
        "customer_id": clean(request_info.get("customer_id", "")),
        "customer_name": customer_name,
        "company_code": clean(request_info.get("company_code", "")),
        "sales_org": clean(request_info.get("sales_org", "")),
        "status": INITIAL_STATUS,
        "assigned_to": clean(assignee.get("display_name")),
        "requested_by": requested_by,
        "business_justification": clean(section_comments.get("request_information", "")),
        "payload_json": json.dumps(payload, ensure_ascii=False, default=str),
        "original_defaults_json": json.dumps(original_defaults, ensure_ascii=False, default=str),
    }

    parameters = [sql_parameter(name, value) for name, value in values.items()]
    parameters += [
        sql_parameter("requested_at", timestamp_value, data_type="TIMESTAMP"),
        sql_parameter("updated_at", timestamp_value, data_type="TIMESTAMP"),
    ]

    execute_sql(INSERT_REQUEST_SQL, headers=request_headers, parameters=parameters)



# Workbench internal statuses (old values mapped like the Workbench does)
STATUS_LABELS = {
    "NEEDS_REVIEW": "Needs review",
    "ASSIGNED": "Needs review",
    "NEW": "Needs review",
    "RESUBMITTED": "Needs review",
    "IN_PROCESS": "In process",
    "IN_REVIEW": "In process",
    "APPROVED": "In process",
    "WAITING_FOR_REQUESTER": "Waiting for you",
    "WAITING_FOR_BUSINESS": "Waiting for you",
    "RETURNED_TO_REQUESTER": "Waiting for you",
    "ON_HOLD": "On hold",
    "COMPLETED": "Completed",
    "REJECTED": "Completed",
}


def list_my_requests(
    requester: str,
    request_headers: Mapping[str, str] | None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """The requester's newest requests with the status the Master Data team set."""
    if not requester:
        return []

    rows = result_rows(
        execute_sql(
            f"""
            SELECT request_id, request_type, customer_id, customer_name, status, requested_at
            FROM {REQUEST_TABLE}
            WHERE lower(requested_by) = lower(:requester)
            ORDER BY requested_at DESC
            LIMIT {int(limit)}
            """,
            headers=request_headers,
            parameters=[sql_parameter("requester", requester)],
        )
    )

    return [
        {
            **{key: clean(row.get(key)) for key in ("request_id", "request_type", "customer_id", "customer_name")},
            "requested_at": clean(row.get("requested_at"))[:16].replace("T", " "),
            "status": STATUS_LABELS.get(clean(row.get("status")).upper(), clean(row.get("status")).title()),
        }
        for row in rows
    ]
