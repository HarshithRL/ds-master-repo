"""Test customer list on the start screen (demo build)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from portal.ui.sidebar import load_customer

TABLE_KEY = "test_customers__table"
ROWS_KEY = "_test_customers__ids"


def _open_selected() -> None:
    """Row click: open that customer."""
    selected = st.session_state.get(TABLE_KEY, {}).get("selection", {}).get("rows", [])
    ids = st.session_state.get(ROWS_KEY, [])

    if selected and selected[0] < len(ids):
        load_customer(ids[selected[0]])


def render_test_customers(rows: list[dict[str, str]]) -> None:
    st.markdown(
        """
        <div class="test-customers-title">Test customers</div>
        <div class="test-customers-text">Click a row to open the customer. Each one
        belongs to a Company Code; Create requests use it automatically.</div>
        """,
        unsafe_allow_html=True,
    )

    st.session_state[ROWS_KEY] = [row["customer_id"] for row in rows]

    table = pd.DataFrame(
        {
            "Customer ID": [row["customer_id"] for row in rows],
            "Customer name": [row["name"] for row in rows],
            "City": [row["city"] for row in rows],
            "Country": [row["country"] for row in rows],
            "Company Code": [
                f"{row['company_code']} · {row['company']}" if row["company"] else row["company_code"]
                for row in rows
            ],
        }
    )

    st.dataframe(
        table,
        key=TABLE_KEY,
        on_select=_open_selected,
        selection_mode="single-row",
        hide_index=True,
        width="stretch",
        height=min(38 + 35 * len(rows), 460),
    )
