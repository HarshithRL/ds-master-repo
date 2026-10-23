from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import json
import os
import time
import uuid

import requests
import streamlit as st


# Inside the AXIOM app the Workbench uses the app's own tables and warehouse
# (src/config.py: {catalog}.bronze.master_data_app_requests / _request_history),
# the same ones the request portal writes.
from config import REQUEST_HISTORY_TABLE as HISTORY_TABLE  # noqa: E402
from config import REQUEST_TABLE, REQUEST_WAREHOUSE_ID  # noqa: E402


INTERNAL_STATUSES = {
    "NEEDS_REVIEW": "Needs review",
    "IN_PROCESS": "In process",
    "WAITING_FOR_REQUESTER": "Waiting for requester",
    "ON_HOLD": "On hold",
    "COMPLETED": "Completed",
}

LEGACY_STATUS_MAP = {
    "NEW": "NEEDS_REVIEW",
    "ASSIGNED": "NEEDS_REVIEW",
    "IN_REVIEW": "IN_PROCESS",
    "WAITING_FOR_BUSINESS": "WAITING_FOR_REQUESTER",
    "RETURNED_TO_REQUESTER": "WAITING_FOR_REQUESTER",
    "RESUBMITTED": "NEEDS_REVIEW",
    "APPROVED": "IN_PROCESS",
    "REJECTED": "COMPLETED",
}


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _workspace_host() -> str:
    host = _clean(
        os.environ.get(
            "DATABRICKS_HOST",
            "",
        )
    )

    if not host:
        raise RuntimeError(
            "DATABRICKS_HOST is not available in the app environment."
        )

    if not host.startswith(
        ("http://", "https://")
    ):
        host = "https://" + host

    return host.rstrip("/")


def _forwarded_user_token() -> str:
    token = _clean(
        st.context.headers.get(
            "x-forwarded-access-token"
        )
    )

    if not token:
        raise RuntimeError(
            "No forwarded Databricks user token was received. "
            "Enable the 'sql' User Authorization scope for the Workbench."
        )

    return token


# app (default): the Workbench's own service principal reads and writes the
# request tables (grant it CAN USE on the warehouse and MODIFY on both tables;
# who may open the Workbench is set by the app permissions). user: the
# signed-in user's forwarded token (needs the 'sql' User Authorization scope
# and table rights for every Master Data member).
SQL_AUTH = os.environ.get("SQL_AUTH", "user").strip().lower()

_app_token: dict[str, Any] = {"value": "", "expires": 0.0}


def _service_principal_token() -> str:
    """OAuth machine-to-machine token of the app's service principal (cached)."""
    if _app_token["value"] and time.time() < float(_app_token["expires"]) - 120:
        return str(_app_token["value"])

    client_id = _clean(os.environ.get("DATABRICKS_CLIENT_ID"))
    client_secret = _clean(os.environ.get("DATABRICKS_CLIENT_SECRET"))
    if not client_id or not client_secret:
        raise RuntimeError(
            "The app's service principal credentials are not available "
            "(DATABRICKS_CLIENT_ID / DATABRICKS_CLIENT_SECRET). Run the app in "
            "Databricks Apps, or set SQL_AUTH to user."
        )

    response = requests.post(
        f"{_workspace_host()}/oidc/v1/token",
        auth=(client_id, client_secret),
        data={"grant_type": "client_credentials", "scope": "all-apis"},
        timeout=30,
    )
    if not response.ok:
        raise RuntimeError(
            f"Could not get the app's Databricks token (HTTP {response.status_code}): {response.text[:300]}"
        )

    body = response.json()
    _app_token.update(value=body["access_token"], expires=time.time() + int(body.get("expires_in", 3600)))
    return str(_app_token["value"])


def current_user() -> str:
    headers = st.context.headers

    for key in (
        "x-forwarded-email",
        "x-forwarded-preferred-username",
        "x-forwarded-user",
    ):
        value = _clean(
            headers.get(key)
        )
        if value:
            return value

    return "Master Data"


def _parameter(
    name: str,
    value: Any,
    *,
    data_type: str = "STRING",
) -> dict[str, str]:
    return {
        "name": name,
        "value": (
            ""
            if value is None
            else str(value)
        ),
        "type": data_type,
    }


def _execute_sql(
    statement: str,
    *,
    parameters: list[dict[str, str]] | None = None,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    host = _workspace_host()
    token = _forwarded_user_token() if SQL_AUTH == "user" else _service_principal_token()

    headers = {
        "Authorization":
        f"Bearer {token}",
        "Content-Type":
        "application/json",
    }

    body: dict[str, Any] = {
        "warehouse_id":
        REQUEST_WAREHOUSE_ID,
        "statement":
        statement,
        "wait_timeout":
        "30s",
        "on_wait_timeout":
        "CONTINUE",
    }

    if parameters:
        body["parameters"] = parameters

    response = requests.post(
        f"{host}/api/2.0/sql/statements",
        headers=headers,
        json=body,
        timeout=45,
    )

    if not response.ok:
        raise RuntimeError(
            "Databricks SQL request failed "
            f"(HTTP {response.status_code}): "
            f"{response.text}"
        )

    result = response.json()
    statement_id = _clean(
        result.get(
            "statement_id"
        )
    )
    started = time.time()

    while True:
        status = result.get(
            "status"
        ) or {}

        state = _clean(
            status.get("state")
        ).upper()

        if state == "SUCCEEDED":
            return result

        if state in {
            "FAILED",
            "CANCELED",
            "CLOSED",
        }:
            error = (
                status.get("error")
                or {}
            )

            message = (
                _clean(
                    error.get("message")
                )
                or str(error)
                or state
            )

            raise RuntimeError(
                "Databricks SQL statement "
                f"{state}: {message}"
            )

        if not statement_id:
            raise RuntimeError(
                "Databricks returned a non-final response without a statement ID."
            )

        if (
            time.time() - started
            > timeout_seconds
        ):
            raise RuntimeError(
                "The SQL statement is still running after "
                f"{timeout_seconds} seconds."
            )

        time.sleep(2)

        poll = requests.get(
            (
                f"{host}/api/2.0/sql/statements/"
                f"{statement_id}"
            ),
            headers=headers,
            timeout=30,
        )

        if not poll.ok:
            raise RuntimeError(
                "Could not retrieve SQL statement status "
                f"(HTTP {poll.status_code}): "
                f"{poll.text}"
            )

        result = poll.json()


def _result_rows(
    result: dict[str, Any],
) -> list[dict[str, Any]]:
    manifest = (
        result.get("manifest")
        or {}
    )
    schema = (
        manifest.get("schema")
        or {}
    )
    columns = (
        schema.get("columns")
        or []
    )

    names = [
        _clean(
            column.get("name")
        )
        for column in columns
    ]

    data = (
        (result.get("result") or {})
        .get("data_array")
        or []
    )

    rows: list[
        dict[str, Any]
    ] = []

    for values in data:
        rows.append(
            {
                name: (
                    values[index]
                    if index < len(values)
                    else None
                )
                for index, name
                in enumerate(names)
            }
        )

    return rows


def _query(
    statement: str,
    *,
    parameters: list[dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    return _result_rows(
        _execute_sql(
            statement,
            parameters=parameters,
        )
    )


def _write_history(
    *,
    request_id: str,
    event_type: str,
    actor: str,
    comment: str = "",
    from_status: str = "",
    to_status: str = "",
) -> None:
    history_id = (
        "HIST-"
        + datetime.now(
            timezone.utc
        ).strftime(
            "%Y%m%d-%H%M%S"
        )
        + "-"
        + uuid.uuid4().hex[
            :6
        ].upper()
    )

    _execute_sql(
        f"""
        INSERT INTO {HISTORY_TABLE}
        (
            history_id,
            request_id,
            event_type,
            from_status,
            to_status,
            actor,
            comment,
            created_at
        )
        VALUES
        (
            :history_id,
            :request_id,
            :event_type,
            :from_status,
            :to_status,
            :actor,
            :comment,
            current_timestamp()
        )
        """,
        parameters=[
            _parameter(
                "history_id",
                history_id,
            ),
            _parameter(
                "request_id",
                request_id,
            ),
            _parameter(
                "event_type",
                event_type,
            ),
            _parameter(
                "from_status",
                from_status,
            ),
            _parameter(
                "to_status",
                to_status,
            ),
            _parameter(
                "actor",
                actor,
            ),
            _parameter(
                "comment",
                comment,
            ),
        ],
    )


def normalized_status(
    status: str,
) -> str:
    status = _clean(
        status
    ).upper()

    if status in INTERNAL_STATUSES:
        return status

    return LEGACY_STATUS_MAP.get(
        status,
        "NEEDS_REVIEW",
    )


def display_status(
    status: str,
) -> str:
    normalized = normalized_status(
        status
    )

    return INTERNAL_STATUSES.get(
        normalized,
        normalized.replace(
            "_",
            " ",
        ).title(),
    )


def _payload_internal(
    payload_json: Any,
) -> dict[str, Any]:
    try:
        payload = json.loads(
            payload_json
            or "{}"
        )
    except (
        json.JSONDecodeError,
        TypeError,
    ):
        payload = {}

    if not isinstance(
        payload,
        dict,
    ):
        return {}

    internal = payload.get(
        "workbench_internal",
        {},
    )

    if not isinstance(
        internal,
        dict,
    ):
        return {}

    return internal


def list_requests(
    *,
    search: str = "",
    include_completed: bool = False,
) -> list[dict[str, Any]]:
    conditions: list[str] = []
    parameters: list[
        dict[str, str]
    ] = []

    if not include_completed:
        conditions.append(
            "upper(coalesce(status, '')) "
            "NOT IN ('COMPLETED', 'REJECTED')"
        )

    if search.strip():
        conditions.append(
            """
            (
                lower(coalesce(request_id, ''))
                    LIKE lower(:search)
                OR lower(coalesce(customer_id, ''))
                    LIKE lower(:search)
                OR lower(coalesce(customer_name, ''))
                    LIKE lower(:search)
                OR lower(coalesce(company_code, ''))
                    LIKE lower(:search)
                OR lower(coalesce(sales_org, ''))
                    LIKE lower(:search)
                OR lower(coalesce(requested_by, ''))
                    LIKE lower(:search)
                OR lower(coalesce(payload_json, ''))
                    LIKE lower(:search)
            )
            """
        )
        parameters.append(
            _parameter(
                "search",
                f"%{search.strip()}%",
            )
        )

    where_clause = (
        "WHERE "
        + " AND ".join(
            conditions
        )
        if conditions
        else ""
    )

    rows = _query(
        f"""
        SELECT
            request_id,
            request_type,
            customer_id,
            customer_name,
            company_code,
            sales_org,
            status,
            requested_by,
            requested_at,
            updated_at,
            payload_json
        FROM {REQUEST_TABLE}
        {where_clause}
        ORDER BY
            customer_name,
            customer_id,
            updated_at DESC,
            requested_at DESC
        """,
        parameters=parameters,
    )

    result: list[
        dict[str, Any]
    ] = []

    for row in rows:
        internal = _payload_internal(
            row.get(
                "payload_json"
            )
        )

        result.append(
            {
                **row,
                "normalized_status":
                normalized_status(
                    row.get(
                        "status",
                        "",
                    )
                ),
                "display_status":
                display_status(
                    row.get(
                        "status",
                        "",
                    )
                ),
                "topdesk_ticket_number":
                _clean(
                    internal.get(
                        "topdesk_ticket_number"
                    )
                ),
            }
        )

    return result


def get_request(
    request_id: str,
) -> dict[str, Any] | None:
    rows = _query(
        f"""
        SELECT
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
            payload_json,
            original_defaults_json
        FROM {REQUEST_TABLE}
        WHERE request_id = :request_id
        LIMIT 1
        """,
        parameters=[
            _parameter(
                "request_id",
                request_id,
            )
        ],
    )

    if not rows:
        return None

    row = rows[0]

    try:
        payload = json.loads(
            row.get(
                "payload_json"
            )
            or "{}"
        )
    except json.JSONDecodeError:
        payload = {}

    try:
        original_defaults = json.loads(
            row.get(
                "original_defaults_json"
            )
            or "{}"
        )
    except json.JSONDecodeError:
        original_defaults = {}

    if not isinstance(
        payload,
        dict,
    ):
        payload = {}

    internal = payload.get(
        "workbench_internal",
        {},
    )

    if not isinstance(
        internal,
        dict,
    ):
        internal = {}

    return {
        **row,
        "payload":
        payload,
        "original_defaults":
        original_defaults,
        "normalized_status":
        normalized_status(
            row.get(
                "status",
                "",
            )
        ),
        "display_status":
        display_status(
            row.get(
                "status",
                "",
            )
        ),
        "topdesk_ticket_number":
        _clean(
            internal.get(
                "topdesk_ticket_number"
            )
        ),
    }


def get_request_history(
    request_id: str,
) -> list[dict[str, Any]]:
    return _query(
        f"""
        SELECT
            history_id,
            request_id,
            event_type,
            from_status,
            to_status,
            actor,
            comment,
            created_at
        FROM {HISTORY_TABLE}
        WHERE request_id = :request_id
        ORDER BY created_at DESC
        """,
        parameters=[
            _parameter(
                "request_id",
                request_id,
            )
        ],
    )


def save_ticket_number(
    request_id: str,
    *,
    ticket_number: str,
    actor: str,
) -> dict[str, Any]:
    current = get_request(
        request_id
    )

    if current is None:
        raise KeyError(
            f"Request {request_id} was not found."
        )

    payload = current.get(
        "payload",
        {},
    )

    if not isinstance(
        payload,
        dict,
    ):
        payload = {}

    internal = payload.get(
        "workbench_internal",
        {},
    )

    if not isinstance(
        internal,
        dict,
    ):
        internal = {}

    old_ticket = _clean(
        internal.get(
            "topdesk_ticket_number"
        )
    )

    new_ticket = _clean(
        ticket_number
    )

    internal[
        "topdesk_ticket_number"
    ] = new_ticket

    internal[
        "updated_by"
    ] = actor

    internal[
        "updated_at"
    ] = datetime.now(
        timezone.utc
    ).isoformat()

    payload[
        "workbench_internal"
    ] = internal

    _execute_sql(
        f"""
        UPDATE {REQUEST_TABLE}
        SET
            payload_json = :payload_json,
            updated_at = current_timestamp()
        WHERE request_id = :request_id
        """,
        parameters=[
            _parameter(
                "payload_json",
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    default=str,
                ),
            ),
            _parameter(
                "request_id",
                request_id,
            ),
        ],
    )

    if old_ticket != new_ticket:
        _write_history(
            request_id=request_id,
            event_type="TOPDESK_TICKET_UPDATED",
            actor=actor,
            comment=(
                f"TOPdesk ticket: "
                f"{new_ticket or '(cleared)'}"
            ),
            from_status=_clean(
                current.get(
                    "status"
                )
            ),
            to_status=_clean(
                current.get(
                    "status"
                )
            ),
        )

    updated = get_request(
        request_id
    )

    if updated is None:
        raise RuntimeError(
            "Ticket number was saved but the request could not be reloaded."
        )

    return updated


def set_internal_status(
    request_id: str,
    *,
    status: str,
    actor: str,
    comment: str = "",
) -> dict[str, Any]:
    target = normalized_status(
        status
    )

    if target not in INTERNAL_STATUSES:
        raise ValueError(
            f"Unsupported internal status: {status}"
        )

    current = get_request(
        request_id
    )

    if current is None:
        raise KeyError(
            f"Request {request_id} was not found."
        )

    old_status = _clean(
        current.get(
            "status"
        )
    )

    _execute_sql(
        f"""
        UPDATE {REQUEST_TABLE}
        SET
            status = :status,
            updated_at = current_timestamp()
        WHERE request_id = :request_id
        """,
        parameters=[
            _parameter(
                "status",
                target,
            ),
            _parameter(
                "request_id",
                request_id,
            ),
        ],
    )

    _write_history(
        request_id=request_id,
        event_type="STATUS_CHANGED",
        actor=actor,
        comment=(
            _clean(comment)
            or (
                f"Internal status changed to "
                f"{INTERNAL_STATUSES[target]}."
            )
        ),
        from_status=old_status,
        to_status=target,
    )

    updated = get_request(
        request_id
    )

    if updated is None:
        raise RuntimeError(
            "Status was updated but the request could not be reloaded."
        )

    return updated


def add_history_event(
    request_id: str,
    *,
    event_type: str,
    actor: str,
    comment: str,
) -> None:
    current = get_request(
        request_id
    )

    current_status = (
        _clean(
            current.get("status")
        )
        if current
        else ""
    )

    _write_history(
        request_id=request_id,
        event_type=event_type,
        actor=actor,
        comment=comment,
        from_status=current_status,
        to_status=current_status,
    )
