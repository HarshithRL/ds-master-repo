from __future__ import annotations

from typing import Any
import time

import requests

from config import REQUEST_WAREHOUSE_ID, REQUEST_HISTORY_TABLE
from helpers import clean
from auth import workspace_host, forwarded_user_token


def execute_sql_statement(
    statement: str,
    *,
    parameters: list[dict[str, str]] | None = None,
    timeout_seconds: int = 300,
) -> dict[str, Any]:
    if not REQUEST_WAREHOUSE_ID:
        raise RuntimeError("The SQL warehouse resource is not configured for this app.")

    host = workspace_host()
    token = forwarded_user_token()

    url = f"{host}/api/2.0/sql/statements"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    body: dict[str, Any] = {
        "warehouse_id": REQUEST_WAREHOUSE_ID,
        "statement": statement,
        "wait_timeout": "30s",
        "on_wait_timeout": "CONTINUE",
    }

    if parameters:
        body["parameters"] = parameters
    response = requests.post(
        url,
        headers=headers,
        json=body,
        timeout=45,
    )

    if not response.ok:
        detail = response.text

        if response.status_code == 403 and "scope" in detail.lower():
            raise RuntimeError(
                "Databricks rejected the request because the app's user "
                "authorization is missing the required SQL scope. "
                "Enable 'sql' under Settings \u2192 User authorization."
            )
        raise RuntimeError(
            "Databricks SQL submission failed "
            f"(HTTP {response.status_code}): {detail}"
        )
    result = response.json()

    statement_id = clean(result.get("statement_id"))

    started = time.time()

    while True:
        status = result.get("status") or {}
        state = clean(status.get("state")).upper()

        if state == "SUCCEEDED":
            return result
        if state in {"FAILED", "CANCELED", "CLOSED"}:
            error = status.get("error") or {}

            message = (
                clean(error.get("message"))
                or str(error)
                or f"Statement ended in state {state}."
            )

            raise RuntimeError(f"Databricks SQL statement {state}: {message}")
        if not statement_id:
            raise RuntimeError(
                "Databricks returned a non-final SQL response without "
                "a statement ID."
            )
        if time.time() - started > timeout_seconds:
            raise RuntimeError(
                "The SQL statement is still running after "
                f"{timeout_seconds} seconds. "
                "Check the SQL warehouse and Query History."
            )
        time.sleep(2)

        poll = requests.get(
            f"{host}/api/2.0/sql/statements/{statement_id}",
            headers=headers,
            timeout=30,
        )

        if not poll.ok:
            raise RuntimeError(
                "Could not retrieve SQL statement status "
                f"(HTTP {poll.status_code}): {poll.text}"
            )
        result = poll.json()


def statement_rows(
    result: dict[str, Any],
) -> list[dict[str, Any]]:
    manifest = result.get("manifest") or {}
    schema = manifest.get("schema") or {}
    columns = schema.get("columns") or []

    column_names = [clean(column.get("name")) for column in columns]

    data_array = (result.get("result") or {}).get("data_array") or []

    rows: list[dict[str, Any]] = []

    for values in data_array:
        rows.append(
            {
                name: (values[index] if index < len(values) else None)
                for index, name in enumerate(column_names)
            }
        )
    return rows


def sql_parameter(
    name: str,
    value: Any,
    *,
    data_type: str = "STRING",
) -> dict[str, str]:
    return {
        "name": name,
        "value": ("" if value is None else str(value)),
        "type": data_type,
    }


def write_submission_history(
    *,
    history_id: str,
    request_id: str,
    event_type: str,
    from_status: str,
    to_status: str,
    actor: str,
    comment: str,
) -> None:
    execute_sql_statement(
        f"""
        INSERT INTO {REQUEST_HISTORY_TABLE}
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
            sql_parameter("history_id", history_id),
            sql_parameter("request_id", request_id),
            sql_parameter("event_type", event_type),
            sql_parameter("from_status", from_status),
            sql_parameter("to_status", to_status),
            sql_parameter("actor", actor),
            sql_parameter("comment", comment),
        ],
    )
