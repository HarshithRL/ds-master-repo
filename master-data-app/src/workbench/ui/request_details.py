from __future__ import annotations

from typing import Any
import base64

import pandas as pd
import streamlit as st

from workbench.services.store import (
    get_request,
    get_request_history,
)


SECTION_LABELS = {
    "request_information":
    "Request Information",
    "general_data":
    "General Data",
    "company_code":
    "Company Code",
    "sales_distribution":
    "Sales & Distribution",
    "partner_functions":
    "Partner Functions",
    "credit_management":
    "Credit Management",
}


def _label(
    key: str,
) -> str:
    special = {
        "id": "ID",
        "vat": "VAT",
        "iban": "IBAN",
        "sap": "SAP",
        "mdm": "MDM",
        "url": "URL",
    }

    words: list[str] = []

    for part in (
        str(key)
        .replace("-", "_")
        .split("_")
    ):
        lower = part.lower()

        words.append(
            special.get(
                lower,
                part.capitalize(),
            )
        )

    return " ".join(
        words
    )


def _value(
    value: Any,
) -> str:
    if value is None:
        return ""

    if isinstance(
        value,
        bool,
    ):
        return (
            "Yes"
            if value
            else "No"
        )

    if isinstance(
        value,
        (list, tuple),
    ):
        return ", ".join(
            _value(item)
            for item in value
        )

    return str(value)


def _simple_rows(
    data: dict[str, Any],
) -> pd.DataFrame:
    rows: list[
        dict[str, str]
    ] = []

    for key, value in data.items():
        if isinstance(
            value,
            dict,
        ):
            continue

        text = _value(
            value
        )

        if text == "":
            continue

        rows.append(
            {
                "Field":
                _label(key),
                "Value":
                text,
            }
        )

    return pd.DataFrame(
        rows
    )

def _render_single_change(
    change_request: dict[str, Any],
) -> None:
    """Older portal versions sent one field per Change request."""

    section = str(
        change_request.get(
            "section",
            "",
        )
        or ""
    ).strip()

    field_key = str(
        change_request.get(
            "field_key",
            "",
        )
        or ""
    ).strip()

    field_label = str(
        change_request.get(
            "field_label",
            "",
        )
        or ""
    ).strip()

    requested_value = str(
        change_request.get(
            "requested_value",
            "",
        )
        or ""
    ).strip()

    comment = str(
        change_request.get(
            "comment",
            "",
        )
        or ""
    ).strip()

    if not field_label:
        field_label = (
            _label(field_key)
            if field_key
            else "Requested Change"
        )

    st.markdown(
        '<div class="wb-section-title">Change Request</div>',
        unsafe_allow_html=True,
    )

    if section:
        st.caption(
            f"Section: {section}"
        )

    st.markdown(
        f"""
        <div style="
            border: 2px solid #EB6910;
            border-left: 7px solid #EB6910;
            border-radius: 8px;
            padding: 18px 20px;
            margin-top: 12px;
            margin-bottom: 18px;
            background: #FFF7F0;
        ">
            <div style="
                color: #666666;
                font-size: 12px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.06em;
                margin-bottom: 5px;
            ">
                Field to Change
            </div>

            <div style="
                color: #222222;
                font-size: 18px;
                font-weight: 700;
                margin-bottom: 16px;
            ">
                {field_label}
            </div>

            <div style="
                color: #666666;
                font-size: 12px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.06em;
                margin-bottom: 5px;
            ">
                Requested Value
            </div>

            <div style="
                background: #EB6910;
                color: #FFFFFF;
                display: inline-block;
                padding: 8px 14px;
                border-radius: 5px;
                font-size: 16px;
                font-weight: 700;
            ">
                {requested_value or "—"}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if comment:
        st.markdown(
            "**Requester comment**"
        )

        st.info(
            comment
        )

def _render_change_list(
    changes: list[Any],
) -> None:
    """The portal's Change form sends every picked field with its current value."""
    rows = [
        {
            "Section": item.get("section") or "",
            "Field": item.get("field_label") or _label(item.get("field_key") or ""),
            "Current": item.get("current_value") or "",
            "Requested": item.get("requested_value") or "",
        }
        for item in changes
        if isinstance(item, dict)
    ]

    st.markdown(
        '<div class="wb-section-title">Change Request</div>',
        unsafe_allow_html=True,
    )

    if not rows:
        st.caption(
            "No section fields were changed; see General Data, "
            "the comments and the attachments below."
        )
        return

    st.caption(
        f"{len(rows)} field change(s) requested"
    )

    st.dataframe(
        pd.DataFrame(rows),
        hide_index=True,
        width="stretch",
        column_config={
            "Section": st.column_config.TextColumn(width="small"),
            "Field": st.column_config.TextColumn(width="medium"),
            "Current": st.column_config.TextColumn(width="medium"),
            "Requested": st.column_config.TextColumn(width="medium"),
        },
    )


def _render_change_request(
    payload: dict[str, Any],
) -> None:
    change_request = payload.get(
        "change_request",
        {},
    )

    if isinstance(
        change_request,
        list,
    ):
        _render_change_list(
            change_request
        )
    else:
        _render_single_change(
            change_request
            if isinstance(change_request, dict)
            else {}
        )

def _render_general_data(
    data: dict[str, Any],
) -> None:
    rows: list[
        dict[str, str]
    ] = []

    for field_key, item in data.items():
        if not isinstance(
            item,
            dict,
        ):
            continue

        rows.append(
            {
                "Field":
                item.get("label")
                or _label(
                    field_key
                ),
                "SAP Field":
                item.get("sap_field")
                or "",
                "Current":
                item.get(
                    "current_value"
                )
                or "",
                "Requested":
                item.get(
                    "requested_value"
                )
                or "",
            }
        )

    if not rows:
        st.caption(
            "No General Data changes requested."
        )
        return

    st.dataframe(
        pd.DataFrame(rows),
        hide_index=True,
        width="stretch",
        column_config={
            "Field":
            st.column_config.TextColumn(
                width="medium"
            ),
            "SAP Field":
            st.column_config.TextColumn(
                width="small"
            ),
            "Current":
            st.column_config.TextColumn(
                width="medium"
            ),
            "Requested":
            st.column_config.TextColumn(
                width="large"
            ),
        },
    )


def _render_section(
    section: str,
    data: dict[str, Any],
    comment: str,
) -> None:
    if section == "general_data":
        _render_general_data(
            data
        )
    else:
        df = _simple_rows(
            data
        )

        if df.empty:
            st.caption(
                "No values submitted."
            )
        else:
            st.dataframe(
                df,
                hide_index=True,
                width="stretch",
                column_config={
                    "Field":
                    st.column_config.TextColumn(
                        width="medium"
                    ),
                    "Value":
                    st.column_config.TextColumn(
                        width="large"
                    ),
                },
            )

    if comment.strip():
        st.markdown(
            "**Requester comment**"
        )
        st.info(
            comment
        )


def _render_attachments(
    payload: dict[str, Any],
) -> None:
    items = payload.get(
        "attachments",
        [],
    )

    if not isinstance(
        items,
        list,
    ) or not items:
        return

    st.markdown(
        "<div class=\"wb-section-title\">Attachments</div>",
        unsafe_allow_html=True,
    )

    columns = st.columns(3)

    for index, item in enumerate(
        items
    ):
        if not isinstance(
            item,
            dict,
        ):
            continue

        name = (
            str(
                item.get("name")
                or f"attachment_{index + 1}"
            )
        )

        encoded = (
            item.get(
                "content_base64"
            )
            or ""
        )

        try:
            file_bytes = (
                base64.b64decode(
                    encoded
                )
                if encoded
                else b""
            )
        except Exception:
            file_bytes = b""

        with columns[
            index % 3
        ]:
            st.markdown(
                f"**{name}**"
            )

            try:
                size_kb = (
                    int(
                        item.get(
                            "size_bytes",
                            0,
                        )
                        or 0
                    )
                    / 1024
                )
            except (
                TypeError,
                ValueError,
            ):
                size_kb = 0

            st.caption(
                f"{size_kb:.0f} KB"
            )

            if file_bytes:
                st.download_button(
                    "Download",
                    data=file_bytes,
                    file_name=name,
                    mime=(
                        item.get(
                            "mime_type"
                        )
                        or (
                            "application/"
                            "octet-stream"
                        )
                    ),
                    key=(
                        "download__"
                        f"{index}__"
                        f"{name}"
                    ),
                    width="stretch",
                )
            else:
                st.caption(
                    "File content unavailable."
                )


def render_request_review(
    request_id: str,
) -> dict[str, Any] | None:
    request = get_request(
        request_id
    )

    if request is None:
        st.warning(
            f"Request {request_id} is not in the Workbench yet. "
            "A portal running in demo mode stores its requests locally: they "
            "show here only in a demo Workbench on the same machine, and in the "
            "live Workbench once the portal writes to the Databricks table."
        )
        return None

    payload = request.get(
        "payload",
        {},
    )

    if not isinstance(
        payload,
        dict,
    ):
        payload = {}

    summary = st.container(border=True, key="wb_request_summary")
    top = summary.columns(5)

    with top[0]:
        st.caption(
            "Customer"
        )
        st.write(
            request.get(
                "customer_name"
            )
            or "—"
        )
        st.caption(
            request.get(
                "customer_id"
            )
            or ""
        )

    with top[1]:
        st.caption(
            "Request"
        )
        st.write(
            request.get(
                "request_id"
            )
            or "—"
        )
        st.caption(
            request.get(
                "request_type"
            )
            or ""
        )

    with top[2]:
        st.caption(
            "Company / Sales Org"
        )
        st.write(
            (
                f"{request.get('company_code') or '—'} "
                f"/ {request.get('sales_org') or '—'}"
            )
        )

    with top[3]:
        st.caption(
            "Status"
        )
        st.write(
            request.get(
                "display_status"
            )
            or "—"
        )
        st.caption(
            request.get(
                "requested_by"
            )
            or ""
        )

    with top[4]:
        st.caption(
            "TOPdesk Ticket"
        )
        st.write(
            request.get(
                "topdesk_ticket_number"
            )
            or "—"
        )
        st.caption(
            "Communication stays in TOPdesk"
        )

    request_type = str(
        request.get(
            "request_type",
            "",
        )
        or ""
    ).strip()

    comments = payload.get(
        "section_comments",
        {},
    )

    if not isinstance(
        comments,
        dict,
    ):
        comments = {}

    # =====================================================================
    # CHANGE CUSTOMER: summary of the requested changes first
    # =====================================================================

    if request_type == "Change Customer":
        _render_change_request(
            payload
        )

    # =====================================================================
    # SUBMITTED SECTIONS
    # =====================================================================

    ordered = [
        "general_data",
        "company_code",
        "sales_distribution",
        "partner_functions",
        "credit_management",
        "request_information",
    ]

    available = [
        section
        for section in ordered
        if section in payload
    ]

    if available:
        tabs = st.tabs(
            [
                SECTION_LABELS.get(
                    section,
                    _label(section),
                )
                for section in available
            ]
        )

        for tab, section in zip(
            tabs,
            available,
        ):
            with tab:
                data = payload.get(
                    section,
                    {},
                )

                if not isinstance(
                    data,
                    dict,
                ):
                    data = {
                        "value":
                        data
                    }

                _render_section(
                    section,
                    data,
                    str(
                        comments.get(
                            section,
                            "",
                        )
                        or ""
                    ),
                )

    _render_attachments(
        payload
    )

    history = get_request_history(
        request_id
    )

    if history:
        with st.expander(
            "Activity",
            expanded=False,
        ):
            rows = [
                {
                    "When":
                    item.get(
                        "created_at",
                        "",
                    ),
                    "Event":
                    _label(
                        item.get(
                            "event_type",
                            "",
                        )
                    ),
                    "By":
                    item.get(
                        "actor",
                        "",
                    ),
                    "Comment":
                    item.get(
                        "comment",
                        "",
                    ),
                }
                for item in history[
                    :12
                ]
            ]

            st.dataframe(
                pd.DataFrame(
                    rows
                ),
                hide_index=True,
                width="stretch",
            )

    return request
