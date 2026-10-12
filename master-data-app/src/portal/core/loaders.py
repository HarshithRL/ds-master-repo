"""Load portal configuration from the environment's seeded sheet snapshots."""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from config import CONFIGURATION_TABLE
from sql_client import execute_sql_statement, sql_parameter, statement_rows


@st.cache_data(ttl=300, show_spinner=False)
def _load_configuration_sheet(source_file: str, sheet_name: str) -> pd.DataFrame:
    legacy_source_file = (
        "customer_reference_library.xlsx" if source_file == "general_data.xlsx" else source_file
    )
    result = execute_sql_statement(
        f"""
        SELECT records_json
        FROM {CONFIGURATION_TABLE}
        WHERE source_file IN (:source_file, :legacy_source_file)
          AND sheet_name = :sheet_name
        ORDER BY CASE WHEN source_file = :source_file THEN 0 ELSE 1 END
        LIMIT 1
        """,
        parameters=[
            sql_parameter("source_file", source_file),
            sql_parameter("legacy_source_file", legacy_source_file),
            sql_parameter("sheet_name", sheet_name),
        ],
    )
    rows = statement_rows(result)
    if not rows:
        raise RuntimeError(
            "Master Data configuration is not populated. Run the paused "
            "'ds-master-data-app - Setup and Seed Bronze Tables' job before starting the app."
        )
    try:
        records = json.loads(rows[0].get("records_json") or "[]")
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"Configuration snapshot {source_file}/{sheet_name} is invalid JSON."
        ) from error
    if not isinstance(records, list) or not records:
        raise RuntimeError(
            f"Configuration snapshot {source_file}/{sheet_name} is empty or invalid."
        )
    return pd.DataFrame.from_records(records).fillna("").astype(str)


def load_customer_database() -> dict[str, pd.DataFrame]:
    return {"customers": pd.DataFrame()}


def load_reference_library() -> dict[str, pd.DataFrame]:
    return {
        "company_sales_org": _load_configuration_sheet(
            "general_data.xlsx", "Company_Sales_Org"
        ),
        "general_data_fields": _load_configuration_sheet(
            "general_data.xlsx", "General_Data_Fields"
        ),
        "tax_details": _load_configuration_sheet(
            "general_data.xlsx", "Tax_Details"
        ),
    }


def load_form_rules() -> dict[str, pd.DataFrame]:
    return {
        "fields": _load_configuration_sheet("customer_form_rules.xlsx", "Form_Fields"),
        "options": _load_configuration_sheet("customer_form_rules.xlsx", "Field_Options"),
    }


def load_credit_rules() -> dict[str, pd.DataFrame]:
    return {
        "mapping": _load_configuration_sheet("credit_management_rules.xlsx", "Credit_Mapping"),
        "fields": _load_configuration_sheet("credit_management_rules.xlsx", "Form_Fields"),
    }


def load_assignment_rules() -> dict[str, pd.DataFrame]:
    return {
        "members": _load_configuration_sheet("assignment_rules.xlsx", "Members"),
        "pool": _load_configuration_sheet("assignment_rules.xlsx", "Assignment_Pool"),
        "messages": _load_configuration_sheet("assignment_rules.xlsx", "Notification_Messages"),
    }