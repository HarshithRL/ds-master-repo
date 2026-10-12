"""Small value and DataFrame helpers used across the logic layer."""

from __future__ import annotations

from typing import Any

import pandas as pd

from portal.constants import YES_VALUES


def clean(value: Any) -> str:
    """Return the value as a stripped string; None and NaN become ""."""
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass

    return str(value).strip()


def normalize_customer_id(value: Any) -> str:
    value = clean(value)
    if not value:
        return ""
    if value.isdigit():
        return value.lstrip("0") or "0"
    return value


def is_yes(value: Any) -> bool:
    return clean(value).upper() in YES_VALUES


def as_int(value: Any) -> int | None:
    value = clean(value)

    if not value:
        return None

    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def format_option(value: str, description: str) -> str:
    return f"{value} — {description}" if description else value


def unique(values: list[Any]) -> list[str]:
    """Non-empty cleaned values, duplicates removed, order kept."""
    return list(dict.fromkeys(clean(value) for value in values if clean(value)))


# =============================================================================
# DATAFRAME FILTERS
# =============================================================================


def column_text(df: pd.DataFrame, column: str) -> pd.Series:
    return df[column].astype(str).str.strip()


def flagged_rows(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """Rows whose flag column holds a "yes" value (Y, YES, TRUE, 1, X)."""
    return df[column_text(df, column).str.upper().isin(YES_VALUES)].copy()


def active_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Rows marked active; every row when the sheet has no active column."""
    if "active" not in df.columns:
        return df.copy()

    return flagged_rows(df, "active")


def rows_for_scope(
    df: pd.DataFrame,
    *,
    company_code: str,
    sales_org: str,
) -> pd.DataFrame:
    """Rows that apply to the Company Code + Sales Org ("" and * mean all)."""
    df = df[column_text(df, "company_code").isin(["", "*", clean(company_code)])]
    return df[column_text(df, "sales_org").isin(["", "*", clean(sales_org)])]


def sort_by_display_order(
    df: pd.DataFrame,
    *,
    by: list[str] | None = None,
) -> pd.DataFrame:
    """Stable sort by display_order (blank/invalid last), optionally after `by`."""
    df = df.copy()
    df["_display_order"] = pd.to_numeric(
        df["display_order"],
        errors="coerce",
    ).fillna(999999)

    return (
        df.sort_values([*(by or []), "_display_order"], kind="stable")
        .drop(columns=["_display_order"])
        .reset_index(drop=True)
    )


def lowercase_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [clean(column).lower() for column in df.columns]
    return df
