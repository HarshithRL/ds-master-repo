"""Customer search: the demo workbook, or Databricks outside demo mode."""

from __future__ import annotations

from typing import Mapping

import pandas as pd

from portal.config import DEMO_MODE
from portal.core.customers import CustomerRecord, get_customer, search_customers
from portal.core.loaders import load_customer_database
from portal.core.utils import active_rows, clean, column_text
from portal.integrations.databricks_sql import execute_sql, result_rows, sql_parameter


def find_customer(
    customer_id: str,
    reference_library: dict[str, pd.DataFrame],
    request_headers: Mapping[str, str] | None = None,
) -> CustomerRecord | None:
    if DEMO_MODE:
        return get_customer(customer_id, load_customer_database())

    return live_customer_lookup(customer_id, reference_library, request_headers)


def live_customer_lookup(
    customer_id: str,
    reference_library: dict[str, pd.DataFrame],
    request_headers: Mapping[str, str] | None,
) -> CustomerRecord | None:
    """Select the General_Data_Fields columns mapped to Databricks for one customer."""
    fields = active_rows(reference_library["general_data_fields"])
    fields = fields[
        fields["databricks_table"].apply(clean).ne("")
        & fields["databricks_column"].apply(clean).ne("")
    ].copy()

    if fields.empty:
        return None

    customer_id_rows = fields[column_text(fields, "field_key").eq("customer_id")]

    if customer_id_rows.empty:
        raise ValueError(
            "General_Data_Fields must contain an active "
            "field_key 'customer_id' with a Databricks mapping"
        )

    table_name = clean(customer_id_rows.iloc[0].get("databricks_table"))
    customer_column = clean(customer_id_rows.iloc[0].get("databricks_column"))

    if not table_name or not customer_column:
        raise ValueError(
            "The customer_id row must contain databricks_table "
            "and databricks_column"
        )

    select_parts = [
        f"`{clean(config.get('databricks_column'))}` AS `{clean(config.get('field_key'))}`"
        for config in fields[column_text(fields, "databricks_table").eq(table_name)].to_dict("records")
        if clean(config.get("field_key")) and clean(config.get("databricks_column"))
    ]

    if not select_parts:
        return None

    select_sql = ",\n        ".join(select_parts)

    rows = result_rows(
        execute_sql(
            f"""
    SELECT
        {select_sql}
    FROM {table_name}
    WHERE `{customer_column}` = :customer_id
    LIMIT 1
    """,
            headers=request_headers,
            parameters=[sql_parameter("customer_id", clean(customer_id))],
        )
    )

    if not rows:
        return None

    return {str(key): clean(value) for key, value in rows[0].items()}


# =============================================================================
# SEARCH BY ID, NAME OR VAT
# =============================================================================

SEARCH_KEYS = ("customer_id", "name_1", "vat_registration_number")


def search_customers_anywhere(
    query: str,
    reference_library: dict[str, pd.DataFrame],
    request_headers: Mapping[str, str] | None = None,
    limit: int = 8,
) -> list[CustomerRecord]:
    if DEMO_MODE:
        return search_customers(query, load_customer_database(), limit)

    return live_customer_search(query, reference_library, request_headers, limit)


def live_customer_search(
    query: str,
    reference_library: dict[str, pd.DataFrame],
    request_headers: Mapping[str, str] | None,
    limit: int = 8,
) -> list[CustomerRecord]:
    """Same matching as the demo search, run against the mapped Databricks table."""
    fields = active_rows(reference_library["general_data_fields"])
    mapped = {
        clean(row.get("field_key")): (clean(row.get("databricks_table")), clean(row.get("databricks_column")))
        for row in fields.to_dict("records")
        if clean(row.get("databricks_table")) and clean(row.get("databricks_column"))
    }

    if "customer_id" not in mapped or not clean(query):
        return []

    table_name = mapped["customer_id"][0]
    columns = {key: column for key, (table, column) in mapped.items() if table == table_name}
    select_sql = ", ".join(f"`{column}` AS `{key}`" for key, column in columns.items())

    conditions = [f"`{columns['customer_id']}` = :exact"]
    conditions += [
        f"lower(`{columns[key]}`) LIKE lower(:like)"
        for key in SEARCH_KEYS
        if key in columns
    ]

    rows = result_rows(
        execute_sql(
            f"SELECT {select_sql} FROM {table_name} "
            f"WHERE {' OR '.join(conditions)} LIMIT {int(limit)}",
            headers=request_headers,
            parameters=[
                sql_parameter("exact", clean(query)),
                sql_parameter("like", f"%{clean(query)}%"),
            ],
        )
    )

    return [{str(key): clean(value) for key, value in row.items()} for row in rows]
