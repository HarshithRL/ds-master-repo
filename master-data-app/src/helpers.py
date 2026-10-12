from __future__ import annotations

from typing import Any

import pandas as pd


def clean(value: Any) -> str:
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass

    return str(value).strip()


def is_yes(value: Any) -> bool:
    return clean(value).upper() in {
        "Y",
        "YES",
        "TRUE",
        "1",
        "X",
    }


def active_rows(df: pd.DataFrame) -> pd.DataFrame:
    if "active" not in df.columns:
        return df.copy()

    return df[
        df["active"]
        .astype(str)
        .str.strip()
        .str.upper()
        .isin({"Y", "YES", "TRUE", "1", "X"})
    ].copy()


def as_int(value: Any) -> int | None:
    value = clean(value)

    if not value:
        return None

    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def format_option(
    value: str,
    description: str,
) -> str:
    if description:
        return f"{value} — {description}"

    return value
