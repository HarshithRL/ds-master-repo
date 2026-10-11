from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st


def clean(value: Any) -> str:
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
    return clean(value).upper() in {"Y", "YES", "TRUE", "1", "X"}


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


def format_option(value: str, description: str) -> str:
    return f"{value} — {description}" if description else value


def reset_form_state() -> None:
    for key in list(st.session_state.keys()):
        if (
            key.startswith("form__")
            or key.startswith("computed_display__")
            or key.startswith("credit__")
            or key.startswith("general_data__")
            or key.startswith("section_comment__")
            or key == "_submit_attempted"
        ):
            del st.session_state[key]
