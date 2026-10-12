"""
Databricks SQL through the Statement Execution REST API.

Runs as the signed-in user: Databricks Apps forwards the user's token in the
x-forwarded-access-token header when the app has the 'sql' User
Authorization scope. Same mechanism as the Customer Master Workbench.
"""

from __future__ import annotations

from typing import Any, Mapping

from sql_client import execute_sql_statement, sql_parameter, statement_rows


def execute_sql(
    statement: str,
    *,
    headers: Mapping[str, str] | None,
    parameters: list[dict[str, str]] | None = None,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    """Run a statement and wait for it to finish; raises on failure."""
    return execute_sql_statement(
        statement,
        parameters=parameters,
        timeout_seconds=timeout_seconds,
    )


def result_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Rows of a finished statement as {column: value} dicts."""
    return statement_rows(result)
