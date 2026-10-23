"""Save Draft / Submit buttons and the submission feedback."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

import pandas as pd
import streamlit as st

from portal.config import DEMO_MODE
from portal.core.submission import submit_to_master_data
from portal.ui.sidebar import refresh_my_requests
from portal.ui.state import LAST_REQUEST_KEY, SESSION_REQUESTS_KEY


def render_action_buttons(key_prefix: str) -> bool:
    """Returns True when Submit was clicked."""
    save_col, submit_col = st.columns([1, 2], gap="small")

    with save_col:
        st.button(
            "Save Draft",
            width="stretch",
            key=f"{key_prefix}__save_draft",
            disabled=True,
            help="Save Draft functionality is coming soon",
        )

    with submit_col:
        return st.button(
            "Submit to Master Data",
            width="stretch",
            key=f"{key_prefix}__submit",
            type="primary",
        )


def handle_submit(
    *,
    validate: Callable[[], list[str]],
    payload: dict[str, Any],
    original_defaults: dict[str, Any],
    assignment_rules: dict[str, pd.DataFrame],
) -> None:
    """Validate, then submit and show the request reference."""
    errors = validate()

    if errors:
        for message in errors:
            st.error(message)
        return

    try:
        with st.spinner("Sending request notification..."):
            submission = submit_to_master_data(
                payload=payload,
                original_defaults=original_defaults,
                assignment_rules=assignment_rules,
                request_headers=st.context.headers,
            )

        st.session_state[LAST_REQUEST_KEY] = submission["request_id"]
        _remember_request(submission["request_id"], payload)
        refresh_my_requests()

        if DEMO_MODE:
            st.success(
                f"Test request {submission['request_id']} "
                f"was created and assigned to "
                f"{submission['assigned_to']}. It is saved in the demo only; "
                "nothing is sent to SAP."
            )
        else:
            st.success(
                f"Request {submission['request_id']} was sent to the Master Data "
                f"team and assigned to {submission['assigned_to']}."
            )

        _show_notification_result(submission)

    except Exception as exc:
        st.error("The request could not be submitted")
        st.exception(exc)


def _remember_request(request_id: str, payload: dict[str, Any]) -> None:
    info = payload.get("request_information", {})
    st.session_state.setdefault(SESSION_REQUESTS_KEY, []).append(
        {
            "request_id": request_id,
            "request_type": info.get("request_type", ""),
            "customer_id": info.get("customer_id", ""),
            "customer_name": payload.get("existing_customer", {}).get("name_1", ""),
            "requested_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "status": "",
        }
    )


def _show_notification_result(submission: dict[str, Any]) -> None:
    if submission.get("notification_error"):
        st.warning(
            "The request reference was created, but the notification "
            f"could not be sent. {submission['notification_error']}"
        )

    elif submission["teams_sent"]:
        if submission.get("notified_requester"):
            st.caption(
                "Notification flow triggered: Teams message to "
                f"{submission['assigned_to']} and confirmation email to "
                f"{submission['notified_requester']}"
            )
        else:
            st.caption(
                "Notification flow triggered: Teams message to "
                f"{submission['assigned_to']}. No requester email was "
                "available for the confirmation (set DEMO_REQUESTER_EMAIL "
                "when running locally)"
            )

    else:
        st.warning(
            "The request reference was created, "
            "but the notification flow URL is not configured"
        )


def render_last_request_reference() -> None:
    if st.session_state.get(LAST_REQUEST_KEY):
        st.caption("Last request reference: " + st.session_state[LAST_REQUEST_KEY])
