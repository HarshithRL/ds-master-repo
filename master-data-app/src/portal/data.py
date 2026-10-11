from __future__ import annotations

import json
from typing import Any

import pandas as pd
import streamlit as st

from config import CONFIGURATION_TABLE
from .utils import (
    active_rows,
    clean,
    is_yes,
    normalize_customer_id,
)

from sql_client import execute_sql_statement, sql_parameter, statement_rows


@st.cache_data(ttl=300, show_spinner=False)
def _load_configuration_sheet(source_file: str, sheet_name: str) -> pd.DataFrame:
    result = execute_sql_statement(
        f"""
        SELECT records_json
        FROM {CONFIGURATION_TABLE}
        WHERE source_file = :source_file
          AND sheet_name = :sheet_name
        LIMIT 1
        """,
        parameters=[
            sql_parameter("source_file", source_file),
            sql_parameter("sheet_name", sheet_name),
        ],
    )
    rows = statement_rows(result)
    if not rows:
        raise RuntimeError(
            "Master Data configuration is not populated. Run the paused "
            "'Master Data App - Setup and Seed Bronze Tables' job before starting the app."
        )

    try:
        records = json.loads(rows[0].get("records_json") or "[]")
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Configuration snapshot {source_file}/{sheet_name} is invalid JSON."
        ) from exc
    if not isinstance(records, list) or not records:
        raise RuntimeError(
            f"Configuration snapshot {source_file}/{sheet_name} is empty or invalid."
        )
    return pd.DataFrame.from_records(records).fillna("").astype(str)


def load_reference_library() -> dict[str, pd.DataFrame]:
    return {
        "company_sales_org": _load_configuration_sheet(
            "customer_reference_library.xlsx", "Company_Sales_Org"
        ),
        "general_data_fields": _load_configuration_sheet(
            "customer_reference_library.xlsx", "General_Data_Fields"
        ),
        "tax_details": _load_configuration_sheet(
            "customer_reference_library.xlsx", "Tax_Details"
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
        "messages": _load_configuration_sheet(
            "assignment_rules.xlsx", "Notification_Messages"
        ),
    }


def get_customer_from_databricks(
    customer_id: str,
    reference_library: dict[str, pd.DataFrame],
) -> dict[str, str] | None:

    fields = active_rows(
        reference_library["general_data_fields"]
    ).copy()

    fields = fields[
        fields["databricks_table"].apply(clean).ne("")
        & fields["databricks_column"].apply(clean).ne("")
    ].copy()

    if fields.empty:
        return None

    # Find the configured Customer ID row
    customer_id_rows = fields[
        fields["field_key"]
        .astype(str)
        .str.strip()
        .eq("customer_id")
    ]

    if customer_id_rows.empty:
        raise ValueError(
            "General_Data_Fields must contain an active "
            "field_key 'customer_id' with a Databricks mapping."
        )

    customer_id_config = customer_id_rows.iloc[0]

    table_name = clean(
        customer_id_config.get("databricks_table")
    )

    customer_column = clean(
        customer_id_config.get("databricks_column")
    )

    if not table_name or not customer_column:
        raise ValueError(
            "The customer_id row must contain databricks_table "
            "and databricks_column."
        )

    table_fields = fields[
        fields["databricks_table"]
        .astype(str)
        .str.strip()
        .eq(table_name)
    ].copy()

    select_parts: list[str] = []

    for _, config in table_fields.iterrows():
        field_key = clean(config.get("field_key"))
        source_column = clean(config.get("databricks_column"))

        if not field_key or not source_column:
            continue

        select_parts.append(
            f"`{source_column}` AS `{field_key}`"
        )

    if not select_parts:
        return None
    
    select_sql = ",\n        ".join(select_parts)

    statement = f"""
    SELECT
        {select_sql}
    FROM {table_name}
    WHERE `{customer_column}` = :customer_id
    LIMIT 1
    """

    result = execute_sql_statement(
        statement,
        parameters=[
            {
                "name": "customer_id",
                "value": clean(customer_id),
                "type": "STRING",
            }
        ],
    )

    rows = statement_rows(result)

    if not rows:
        return None

    return {
        str(key): clean(value)
        for key, value in rows[0].items()
    }
    

def get_customer_company_codes(
    customer_id: str,
    db: dict[str, pd.DataFrame],
) -> list[str]:
    rows = active_rows(db["sales_areas"])
    rows = rows[
        rows["customer_id"].apply(normalize_customer_id)
        == normalize_customer_id(customer_id)
    ]

    values = [clean(value) for value in rows["company_code"].tolist() if clean(value)]
    return list(dict.fromkeys(values))


def get_customer_sales_areas(
    customer_id: str,
    company_code: str,
    db: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    rows = active_rows(db["sales_areas"])
    rows = rows[
        rows["customer_id"].apply(normalize_customer_id)
        == normalize_customer_id(customer_id)
    ]

    if company_code:
        rows = rows[rows["company_code"].astype(str).str.strip() == clean(company_code)]

    return rows.reset_index(drop=True)


def get_reference_company_codes(
    reference_library: dict[str, pd.DataFrame],
) -> list[str]:
    rows = active_rows(reference_library["company_sales_org"])
    values = [clean(value) for value in rows["company_code"].tolist() if clean(value)]
    return list(dict.fromkeys(values))


def get_reference_sales_orgs(
    company_code: str,
    reference_library: dict[str, pd.DataFrame],
) -> list[str]:
    rows = active_rows(reference_library["company_sales_org"])
    rows = rows[rows["company_code"].astype(str).str.strip() == clean(company_code)]
    values = [clean(value) for value in rows["sales_org"].tolist() if clean(value)]
    return list(dict.fromkeys(values))


def get_reference_company_label(
    company_code: str,
    reference_library: dict[str, pd.DataFrame],
) -> str:
    rows = active_rows(reference_library["company_sales_org"])
    rows = rows[
        rows["company_code"].astype(str).str.strip()
        == clean(company_code)
    ]

    if rows.empty:
        return clean(company_code)

    company_name = clean(rows.iloc[0].get("company_name"))

    if company_name:
        return f"{clean(company_code)} — {company_name}"

    return clean(company_code)


def get_display_general_data_fields(
    *,
    reference_library: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """
    Return active General Data fields configured to appear
    in Existing Customer Information.
    """
    fields = active_rows(
        reference_library["general_data_fields"]
    ).copy()

    if "display" not in fields.columns:
        return fields.iloc[0:0].copy()

    fields = fields[
        fields["display"]
        .astype(str)
        .str.strip()
        .str.upper()
        .isin({"Y", "YES", "TRUE", "1", "X"})
    ].copy()

    return fields.reset_index(drop=True)


def get_existing_customer_pairs(
    customer_id: str,
    db: dict[str, pd.DataFrame],
) -> set[tuple[str, str]]:
    rows = active_rows(db["sales_areas"])
    rows = rows[
        rows["customer_id"].apply(normalize_customer_id)
        == normalize_customer_id(customer_id)
    ]

    return {
        (
            clean(row.get("company_code")),
            clean(row.get("sales_organization")),
        )
        for row in rows.to_dict("records")
        if clean(row.get("company_code")) and clean(row.get("sales_organization"))
    }

def get_form_fields(
    *,
    company_code: str,
    sales_org: str,
    rules: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    fields = active_rows(rules["fields"]).copy()

    selected_company_code = clean(company_code)
    selected_sales_org = clean(sales_org)

    fields = fields[
        fields["company_code"]
        .astype(str)
        .str.strip()
        .isin(["", "*", selected_company_code])
    ]

    fields = fields[
        fields["sales_org"]
        .astype(str)
        .str.strip()
        .isin(["", "*", selected_sales_org])
    ]

    fields["_display_order"] = pd.to_numeric(
        fields["display_order"],
        errors="coerce",
    ).fillna(999999)

    return (
        fields.sort_values(
            ["section", "_display_order"],
            kind="stable",
        )
        .drop(columns=["_display_order"])
        .reset_index(drop=True)
    )


def get_field_options(
    *,
    field_key: str,
    company_code: str,
    sales_org: str,
    rules: dict[str, pd.DataFrame],
) -> list[dict[str, str]]:
    options = active_rows(rules["options"]).copy()

    selected_company_code = clean(company_code)
    selected_sales_org = clean(sales_org)

    options = options[
        options["field_key"]
        .astype(str)
        .str.strip()
        .eq(clean(field_key))
    ]

    options = options[
        options["company_code"]
        .astype(str)
        .str.strip()
        .isin(["", "*", selected_company_code])
    ]

    options = options[
        options["sales_org"]
        .astype(str)
        .str.strip()
        .isin(["", "*", selected_sales_org])
    ]

    result: list[dict[str, str]] = []

    for _, row in options.iterrows():
        result.append(
            {
                "value": clean(row.get("value")),
                "description": clean(row.get("description")),
                "is_default": clean(row.get("is_default")),
            }
        )

    return result

def get_credit_mapping(
    *,
    company_code: str,
    credit_rules: dict[str, pd.DataFrame],
) -> dict[str, str] | None:
    mapping = active_rows(credit_rules["mapping"])

    company_column = (
        "company_code"
        if "company_code" in mapping.columns
        else "sp1"
        if "sp1" in mapping.columns
        else None
    )
    if company_column is None:
        return None

    match = mapping[
        mapping[company_column].astype(str).str.strip() == clean(company_code)
    ]
    if match.empty:
        return None

    return {
        str(column): clean(value) for column, value in match.iloc[0].to_dict().items()
    }

def find_default(
    field: dict[str, Any],
    option_rows: list[dict[str, str]],
) -> str:
    configured = clean(field.get("default_value"))

    if configured:
        return configured

    for option in option_rows:
        if is_yes(option.get("is_default")):
            return clean(option.get("value"))

    return ""
    
def get_credit_fields(
    credit_rules: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    fields = active_rows(credit_rules["fields"]).copy()

    if "visible" in fields.columns:
        fields = fields[
            fields["visible"]
            .astype(str)
            .str.strip()
            .str.upper()
            .isin({"Y", "YES", "TRUE", "1", "X"})
        ].copy()

    existing_keys = set(fields["field_key"].astype(str).str.strip())
    old_collection = fields[
        fields["field_key"].astype(str).str.strip().eq("collection_contact")
    ]
    legacy = old_collection.iloc[0].to_dict() if not old_collection.empty else {}

    try:
        order = float(legacy.get("display_order"))
        if pd.isna(order):
            order = 30.0
    except (ValueError, TypeError):
        order = 30.0

    fields = fields[
        ~fields["field_key"].astype(str).str.strip().eq("collection_contact")
    ].copy()

    description = (
        "Individual or department to contact regarding outstanding invoices, "
        "payment issues and collection-related enquiries."
    )

    new_fields = []
    for key, label, required, offset in [
        ("collection_contact_name", "Collection Contact Name", "Y", 0.01),
        ("collection_contact_email", "Collection Contact Email", "Y", 0.02),
        ("collection_contact_phone", "Collection Contact Phone", "N", 0.03),
    ]:
        if key in existing_keys:
            continue
        new_fields.append(
            {
                **legacy,
                "section": "Credit Management",
                "field_key": key,
                "label": label,
                "input_type": "text",
                "required": required,
                "visible": "Y",
                "editable": "Y",
                "value_source": "mapping",
                "mapping_column": key,
                "preserve_existing": "Y",
                "display_order": order + offset,
                "active": "Y",
                "notes": description if key == "collection_contact_name" else "",
            }
        )

    if new_fields:
        fields = pd.concat([fields, pd.DataFrame(new_fields)], ignore_index=True)

    fields["_display_order"] = pd.to_numeric(
        fields["display_order"], errors="coerce"
    ).fillna(999999)

    return (
        fields.sort_values("_display_order", kind="stable")
        .drop(columns=["_display_order"])
        .reset_index(drop=True)
    )


def get_credit_initial_value(
    *,
    field: dict[str, Any],
    customer: dict[str, str],
    mapping: dict[str, str] | None,
) -> str:
    field_key = clean(field.get("field_key"))
    existing_value = clean(customer.get(field_key))
    mapped = mapping or {}

    if field_key in {
        "collection_contact_name",
        "collection_contact_email",
        "collection_contact_phone",
    }:
        explicit_value = existing_value or clean(mapped.get(field_key))
        if explicit_value:
            return explicit_value

        legacy_value = clean(customer.get("collection_contact")) or clean(
            mapped.get("collection_contact")
        )
        if (
            field_key == "collection_contact_name"
            and legacy_value
            and "@" not in legacy_value
        ):
            return legacy_value
        if field_key == "collection_contact_email" and "@" in legacy_value:
            return legacy_value
        return ""

    preserve_existing = is_yes(field.get("preserve_existing"))
    if preserve_existing and existing_value:
        return existing_value

    value_source = clean(field.get("value_source")).lower()
    if value_source == "existing":
        return existing_value

    if value_source == "mapping":
        mapping_column = clean(field.get("mapping_column")) or field_key
        mapped_value = clean(mapped.get(mapping_column))
        if mapped_value:
            return mapped_value
        if existing_value:
            return existing_value

    return ""


def get_original_defaults(
    *,
    fields: pd.DataFrame,
    company_code: str,
    sales_org: str,
    rules: dict[str, pd.DataFrame],
    context: dict[str, str],
) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}

    for _, row in fields.iterrows():
        field = row.to_dict()
        section = clean(field.get("section"))
        field_key = clean(field.get("field_key"))
        input_type = clean(field.get("input_type")).lower()

        if section not in result:
            result[section] = {}

        if input_type == "readonly":
            value = clean(context.get(field_key))
        elif input_type == "computed":
            value = ""
        else:
            options = get_field_options(
                field_key=field_key,
                company_code=company_code,
                sales_org=sales_org,
                rules=rules,
            )
            value = find_default(field, options)

        result[section][field_key] = value

    return result
