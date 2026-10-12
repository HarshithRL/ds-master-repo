"""
Form rules from customer_form_rules.xlsx and general_data.xlsx.

Which fields a Company Code + Sales Org combination shows, their dropdown
options and defaults, and the Company Code / Sales Org reference list.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from portal.constants import CHECKBOX, COMPANY_CODE, RULE_SECTIONS, SALES_DISTRIBUTION
from portal.core.utils import (
    active_rows,
    clean,
    column_text,
    is_yes,
    rows_for_scope,
    sort_by_display_order,
    unique,
)

FieldRecord = dict[str, Any]
OptionRow = dict[str, str]

# =============================================================================
# COMPANY CODE / SALES ORGANIZATION REFERENCE
# =============================================================================


def _company_rows(
    company_code: str,
    reference_library: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    rows = active_rows(reference_library["company_sales_org"])
    return rows[column_text(rows, "company_code") == clean(company_code)]


def get_reference_company_codes(
    reference_library: dict[str, pd.DataFrame],
) -> list[str]:
    rows = active_rows(reference_library["company_sales_org"])
    return unique(rows["company_code"].tolist())


def get_reference_sales_orgs(
    company_code: str,
    reference_library: dict[str, pd.DataFrame],
) -> list[str]:
    """Every Sales Org configured for the Company Code (one or many)."""
    return unique(_company_rows(company_code, reference_library)["sales_org"].tolist())


def get_reference_company_label(
    company_code: str,
    reference_library: dict[str, pd.DataFrame],
) -> str:
    rows = _company_rows(company_code, reference_library)

    if rows.empty:
        return clean(company_code)

    company_name = clean(rows.iloc[0].get("company_name"))

    if company_name:
        return f"{clean(company_code)} — {company_name}"

    return clean(company_code)


# =============================================================================
# FORM FIELDS AND OPTIONS
# =============================================================================


def get_form_fields(
    *,
    company_code: str,
    sales_org: str,
    rules: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """Active Form_Fields rows for the scope, sorted by section and order."""
    fields = rows_for_scope(
        active_rows(rules["fields"]),
        company_code=company_code,
        sales_org=sales_org,
    )

    return sort_by_display_order(fields, by=["section"])


def section_fields(fields: pd.DataFrame, section: str) -> pd.DataFrame:
    return fields[column_text(fields, "section").eq(section)]


def split_rule_sections(fields: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """{"company_code": df, "sales_distribution": df, "partner_functions": df}"""
    return {
        key: section_fields(fields, section) for key, section in RULE_SECTIONS.items()
    }


def get_field_options(
    *,
    field_key: str,
    company_code: str,
    sales_org: str,
    rules: dict[str, pd.DataFrame],
) -> list[OptionRow]:
    options = active_rows(rules["options"])
    options = options[column_text(options, "field_key").eq(clean(field_key))]
    options = rows_for_scope(
        options,
        company_code=company_code,
        sales_org=sales_org,
    )

    return [
        {
            "value": clean(row.get("value")),
            "description": clean(row.get("description")),
            "is_default": clean(row.get("is_default")),
        }
        for _, row in options.iterrows()
    ]


def find_default(
    field: FieldRecord,
    option_rows: list[OptionRow],
) -> str:
    """default_value from the field row, else the option flagged is_default."""
    configured = clean(field.get("default_value"))

    if configured:
        return configured

    for option in option_rows:
        if is_yes(option.get("is_default")):
            return clean(option.get("value"))

    return ""


@dataclass(frozen=True)
class SelectChoices:
    options: list[str]
    index: int
    descriptions: dict[str, str]


def build_select_choices(
    *,
    option_rows: list[OptionRow],
    required: bool,
    current_value: str,
    default_value: str,
) -> SelectChoices | None:
    """
    Options and starting index for a select field.

    Optional fields get a blank first option. A value already chosen that is
    no longer configured stays selectable. None means no options exist and
    the field falls back to a text input.
    """
    option_values = [option["value"] for option in option_rows if option["value"]]

    if not option_values:
        return None

    descriptions = {option["value"]: option["description"] for option in option_rows}

    options = list(dict.fromkeys(option_values))
    if not required:
        options = [""] + options

    if current_value and current_value not in options:
        options.insert(0, current_value)

    if current_value in options:
        index = options.index(current_value)
    elif default_value in options:
        index = options.index(default_value)
    else:
        index = 0

    return SelectChoices(options, index, descriptions)


# =============================================================================
# DERIVED VALUES
# =============================================================================


def is_checkbox(field: FieldRecord) -> bool:
    return clean(field.get("input_type")).lower() == CHECKBOX


def readonly_value(field: FieldRecord, context: dict[str, str]) -> str:
    """Readonly fields show the request context value, else default_value."""
    field_key = clean(field.get("field_key"))
    return clean(context.get(field_key) or clean(field.get("default_value")))


def copy_computed_values(
    company_fields: pd.DataFrame,
    target: dict[str, str],
    sales_values: dict[str, Any],
) -> None:
    """Fill computed Company Code fields from their copy_from_field (in place)."""
    for field in company_fields.to_dict("records"):
        if clean(field.get("input_type")).lower() != "computed":
            continue

        target[clean(field.get("field_key"))] = clean(
            sales_values.get(clean(field.get("copy_from_field")))
        )


def get_original_defaults(
    *,
    fields: pd.DataFrame,
    company_code: str,
    sales_org: str,
    rules: dict[str, pd.DataFrame],
    context: dict[str, str],
) -> dict[str, dict[str, str]]:
    """{section: {field_key: value the form starts with}} for every field."""
    result: dict[str, dict[str, str]] = {}

    for field in fields.to_dict("records"):
        section = clean(field.get("section"))
        field_key = clean(field.get("field_key"))
        input_type = clean(field.get("input_type")).lower()

        if section not in result:
            result[section] = {}

        if input_type == "readonly":
            value = readonly_value(field, context)
        elif input_type == "computed":
            value = ""
        else:
            value = find_default(
                field,
                get_field_options(
                    field_key=field_key,
                    company_code=company_code,
                    sales_org=sales_org,
                    rules=rules,
                ),
            )

        result[section][field_key] = value

    company_defaults = result.get(COMPANY_CODE, {})
    copy_computed_values(
        section_fields(fields, COMPANY_CODE),
        company_defaults,
        result.get(SALES_DISTRIBUTION, {}),
    )

    return result


# =============================================================================
# CHANGE REQUESTS
# =============================================================================


def changeable_fields(section_df: pd.DataFrame) -> list[FieldRecord]:
    """Fields a Change request may target: visible, not computed, not readonly."""
    return [
        field
        for field in section_df.to_dict("records")
        if not is_yes(field.get("hidden"))
        and clean(field.get("input_type")).lower() not in {"computed", "readonly"}
    ]
