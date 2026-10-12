"""Existing Customer Information card (left panel)."""

from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from portal.core.customers import OverviewItem, OverviewSection, build_customer_overview


def _item_html(item: OverviewItem) -> str:
    info = (
        f'<span class="customer-tax-info" '
        f'title="{html.escape(item.tooltip, quote=True)}" '
        'style="margin-left:5px;cursor:help;color:#667085" '
        'aria-label="Tax field information">ⓘ</span>'
        if item.tooltip
        else ""
    )

    return (
        '<div class="customer-card-item">'
        f'<span class="customer-card-label">{html.escape(item.label)}{info}</span>'
        f'<span class="customer-card-value">{html.escape(item.value or "—")}</span>'
        '</div>'
    )


def _section_html(section: OverviewSection) -> str:
    return (
        '<div class="customer-info-section">'
        f'<div class="customer-info-heading">{html.escape(section.title)}</div>'
        f'<div class="customer-card-grid">'
        + "".join(_item_html(item) for item in section.items)
        + '</div>'
        '</div>'
    )


def render_customer_information(
    customer: dict[str, str],
    reference_library: dict[str, pd.DataFrame],
) -> None:
    body = "".join(
        _section_html(section)
        for section in build_customer_overview(customer, reference_library)
    )

    st.markdown(
        '<div class="customer-card">'
        '<div class="customer-card-title">'
        '<span>Existing Customer Information</span>'
        '</div>'
        f'{body}'
        '</div>',
        unsafe_allow_html=True,
    )
