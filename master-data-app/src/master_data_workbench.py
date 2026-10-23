"""Customer Master Workbench page of the AXIOM app (Master Data team only)."""

from __future__ import annotations

import html
import re
from pathlib import Path

import streamlit as st

from workbench.services.request_pdf import build_request_pdf
from workbench.services.config import DEMO_MODE
from workbench.services.store import (
    INTERNAL_STATUSES,
    current_user,
    list_requests,
    save_ticket_number,
    set_internal_status,
)
from workbench.ui.request_details import render_request_review
from workbench.ui.theme import apply_theme, apply_workbench_styles, status_pill
from portal.core.identity import is_master_data_member, requester_email
from portal.core.loaders import load_assignment_rules


# =============================================================================
# PAGE + THEME
# =============================================================================

st.set_page_config(
    page_title="AXIOM | Customer Master Workbench",
    page_icon="assets/axiom_icon.png",
    layout="wide",
)

apply_theme()
apply_workbench_styles()

# Only the Master Data team (active Members in assignment_rules.xlsx, plus
# WORKBENCH_ADMINS) may open this page. It is not in any menu; others reach it
# only through a link and see this message.
_email = requester_email(st.context.headers)
try:
    _allowed = is_master_data_member(_email, load_assignment_rules())
except Exception as exc:  # configuration table not reachable
    st.error(f"The Master Data team list could not be loaded: {exc}")
    st.stop()

if not _allowed:
    st.warning(
        "This page is for the Master Data team only. "
        + (f"{_email} is not in the team list." if _email else "Your account could not be identified.")
    )
    st.page_link("request_portal.py", label="Back to the request portal", icon=":material/arrow_back:")
    st.stop()

st.page_link("request_portal.py", label="Request portal", icon=":material/arrow_back:")

if DEMO_MODE:
    st.caption("DEMO MODE · Sample requests and requests from the portal demo")

# Links from the Teams notification open one request: ?request=REQ-...
REQUEST_PARAM = "request"
TEAM_GUIDE_FILE = Path(__file__).resolve().parent / "docs" / "mdm_guide.pdf"
SELECTED_KEY = "review__selected_request"


def _clean(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _status_order(status: str) -> int:
    normalized = _clean(status).upper()
    return {
        "NEEDS_REVIEW": 0,
        "IN_PROCESS": 1,
        "WAITING_FOR_REQUESTER": 2,
        "ON_HOLD": 3,
        "COMPLETED": 4,
    }.get(normalized, 5)


def _safe_filename(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
    return value.strip("_") or "customer_request"


def _select_request(request_id: str) -> None:
    st.session_state[SELECTED_KEY] = request_id
    st.query_params[REQUEST_PARAM] = request_id


linked_request = _clean(st.query_params.get(REQUEST_PARAM))
if linked_request and st.session_state.get("_linked_request") != linked_request:
    st.session_state["_linked_request"] = linked_request
    st.session_state[SELECTED_KEY] = linked_request


# =============================================================================
# SIDEBAR
# =============================================================================

actor = current_user()

with st.sidebar:
    st.markdown(
        """
        <div class="wb-side-eyebrow">MASTER DATA TEAM</div>
        <div class="wb-side-title">Customer request review</div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f'<div class="wb-side-user">Signed in as<br><b>{html.escape(actor)}</b></div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="wb-side-card">
            Requests are submitted by the business in the
            <b>AXIOM Customer Request Portal</b>. Requester communication and
            the official ticket history stay in <b>TOPdesk</b>; this Workbench
            is for structured review and internal tracking.
        </div>
        """,
        unsafe_allow_html=True,
    )

    if DEMO_MODE:
        st.markdown(
            """
            <div class="wb-side-card">
                <b>Demo mode</b>: sample requests plus requests submitted in
                the AXIOM portal demo. Ticket and status changes are saved
                locally. Set <b>WORKBENCH_DEMO_MODE=false</b> to use Databricks.
            </div>
            """,
            unsafe_allow_html=True,
        )

    if st.button(
        "Refresh",
        width="stretch",
        key="review__refresh",
    ):
        st.rerun()

    if TEAM_GUIDE_FILE.exists():
        st.download_button(
            "Team guide (PDF)",
            data=TEAM_GUIDE_FILE.read_bytes(),
            file_name="AXIOM_Workbench_Master_Data_Guide.pdf",
            mime="application/pdf",
            width="stretch",
            key="review__guide",
        )


# =============================================================================
# HEADER
# =============================================================================

with st.container(key="axiom_main_header"):
    logo_col, title_col = st.columns(
        [1.1, 4.6],
        gap="medium",
        vertical_alignment="center",
    )

    with logo_col:
        st.image("assets/axiom_logo.svg", width=150)

    with title_col:
        st.markdown(
            """
            <div class="wb-header-title">Customer Master Workbench</div>
            <div class="wb-header-sub">Review submitted requests, download the form
            for TOPdesk and track the Master Data task.</div>
            """,
            unsafe_allow_html=True,
        )


# =============================================================================
# REQUEST LIST
# =============================================================================

filter_col1, filter_col2 = st.columns([3, 1], vertical_alignment="bottom")

with filter_col1:
    search = st.text_input(
        "Search",
        placeholder="Customer, customer ID, request ID or TOPdesk ticket...",
        key="review__search",
    )

with filter_col2:
    include_completed = st.checkbox(
        "Show completed",
        value=False,
        key="review__show_completed",
    )

requests_list = list_requests(
    search=search,
    include_completed=include_completed,
)

requests_list = sorted(
    requests_list,
    key=lambda item: (
        _status_order(item.get("normalized_status", "")),
        _clean(item.get("customer_name")).lower(),
        _clean(item.get("customer_id")),
    ),
)

selected_request_id = st.session_state.get(SELECTED_KEY)

if not requests_list:
    st.info("No requests match the current filter.")
    if not selected_request_id:
        st.stop()

groups: dict[tuple[str, str], list[dict]] = {}

for item in requests_list:
    customer_id = _clean(item.get("customer_id"))
    customer_name = _clean(item.get("customer_name")) or "Unnamed customer"
    groups.setdefault((customer_id, customer_name), []).append(item)

COLUMNS = [1.3, 1.05, 1.05, 1.25, 1.2, 0.7]

for (customer_id, customer_name), customer_requests in groups.items():
    open_count = sum(
        1
        for item in customer_requests
        if item.get("normalized_status") != "COMPLETED"
    )

    title = f"{customer_name} · {customer_id or 'No ID'}  ({open_count} open)"

    with st.expander(
        title,
        expanded=(
            selected_request_id
            in {item.get("request_id") for item in customer_requests}
        ),
    ):
        header = st.columns(COLUMNS)
        for col, text in zip(
            header,
            ["Request", "TOPdesk", "Type", "Status", "Updated", ""],
        ):
            with col:
                st.markdown(
                    f'<div class="wb-col-head"><p>{text}</p></div>',
                    unsafe_allow_html=True,
                )

        for item in customer_requests:
            cols = st.columns(COLUMNS, vertical_alignment="center")

            with cols[0]:
                st.markdown(
                    f'<span class="wb-request-id">{item.get("request_id", "")}</span>',
                    unsafe_allow_html=True,
                )

            with cols[1]:
                st.markdown(
                    f'<span class="wb-muted">{item.get("topdesk_ticket_number") or "—"}</span>',
                    unsafe_allow_html=True,
                )

            with cols[2]:
                st.markdown(
                    f'<span class="wb-muted">{item.get("request_type") or "—"}</span>',
                    unsafe_allow_html=True,
                )

            with cols[3]:
                st.markdown(
                    status_pill(
                        item.get("normalized_status", ""),
                        item.get("display_status") or "—",
                    ),
                    unsafe_allow_html=True,
                )

            with cols[4]:
                st.markdown(
                    '<span class="wb-muted">'
                    f'{item.get("updated_at") or item.get("requested_at") or ""}</span>',
                    unsafe_allow_html=True,
                )

            with cols[5]:
                if st.button(
                    "Open",
                    key="open__" + item["request_id"],
                    width="stretch",
                    type=(
                        "primary"
                        if item["request_id"] == selected_request_id
                        else "secondary"
                    ),
                ):
                    _select_request(item["request_id"])
                    st.rerun()


# =============================================================================
# SELECTED REQUEST
# =============================================================================

selected_request_id = st.session_state.get(SELECTED_KEY)

if not selected_request_id:
    st.info("Open a request above to review it.")
    st.stop()

st.divider()

request = render_request_review(selected_request_id)

if request is None:
    st.stop()


# =============================================================================
# TOPDESK + INTERNAL TRACKING
# =============================================================================

st.divider()
st.markdown(
    '<div class="wb-section-title">TOPdesk & Internal Tracking</div>',
    unsafe_allow_html=True,
)
st.caption(
    "The ticket conversation stays in TOPdesk. These fields are only for the "
    "Master Data team's internal overview."
)

with st.container(border=True):
    tracking_cols = st.columns([1.3, 1.1, .9], vertical_alignment="bottom")

    with tracking_cols[0]:
        ticket_number = st.text_input(
            "TOPdesk Ticket Number",
            value=request.get("topdesk_ticket_number") or "",
            placeholder="e.g. T24012345 / INC-123456",
            key=f"tracking__ticket__{selected_request_id}",
        )

    with tracking_cols[1]:
        status_options = list(INTERNAL_STATUSES.keys())
        current_status = request.get("normalized_status") or "NEEDS_REVIEW"
        try:
            current_index = status_options.index(current_status)
        except ValueError:
            current_index = 0

        internal_status = st.selectbox(
            "Internal Status",
            options=status_options,
            index=current_index,
            format_func=lambda value: INTERNAL_STATUSES[value],
            key=f"tracking__status__{selected_request_id}",
            help=(
                "Needs review = not started; In process = MDM is working; "
                "Waiting for requester = awaiting information through TOPdesk; "
                "On hold = internally paused; Completed = finished."
            ),
        )

    with tracking_cols[2]:
        if st.button(
            "Save",
            type="primary",
            width="stretch",
            key=f"tracking__save__{selected_request_id}",
        ):
            try:
                changed = False

                if _clean(ticket_number) != _clean(
                    request.get("topdesk_ticket_number")
                ):
                    request = save_ticket_number(
                        selected_request_id,
                        ticket_number=ticket_number,
                        actor=actor,
                    )
                    changed = True

                if internal_status != request.get("normalized_status"):
                    request = set_internal_status(
                        selected_request_id,
                        status=internal_status,
                        actor=actor,
                    )
                    changed = True

                if changed:
                    st.success("Workbench tracking updated.")
                    st.rerun()
                else:
                    st.info("Nothing changed.")

            except Exception as exc:
                st.error(str(exc))


# =============================================================================
# PDF EXPORT
# =============================================================================

pdf_cols = st.columns([1.2, 2.8], vertical_alignment="center")

with pdf_cols[0]:
    try:
        pdf_request = dict(request)
        pdf_request["display_status"] = INTERNAL_STATUSES.get(
            internal_status,
            request.get("display_status") or "",
        )
        pdf_request["status"] = internal_status

        pdf_bytes = build_request_pdf(
            pdf_request,
            ticket_number=ticket_number,
        )

        pdf_name_parts = [
            _clean(ticket_number),
            _clean(request.get("request_id")),
            "customer_form",
        ]

        pdf_name = _safe_filename(
            "_".join(part for part in pdf_name_parts if part)
        ) + ".pdf"

        st.download_button(
            "Download form as PDF",
            data=pdf_bytes,
            file_name=pdf_name,
            mime="application/pdf",
            width="stretch",
            key=f"pdf__{selected_request_id}",
        )
    except Exception as exc:
        st.error(f"PDF could not be generated: {exc}")

with pdf_cols[1]:
    st.caption(
        "The PDF contains the submitted form, requester comments, attachment names, "
        "request status and TOPdesk ticket number. It can be attached to the TOPdesk ticket."
    )
