"""
Demo request store: same functions as services/request_store.py, no Databricks.

Requests come from
  - data/demo_requests.json (sample requests shipped with the Workbench)
  - the AXIOM portal's demo log (demo_requests.jsonl), so a request submitted
    in the portal demo can be reviewed here
Ticket numbers, status changes and their history are kept in DEMO_STATE_FILE.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime
from typing import Any

import streamlit as st

from workbench.services.config import DEMO_REQUESTS_FILE, DEMO_STATE_FILE, PORTAL_DEMO_REQUESTS_FILE
from workbench.services.request_store import INTERNAL_STATUSES, display_status, normalized_status

__all__ = [
    "INTERNAL_STATUSES",
    "add_history_event",
    "current_user",
    "display_status",
    "get_request",
    "get_request_history",
    "list_requests",
    "normalized_status",
    "save_ticket_number",
    "set_internal_status",
]

DEMO_USER = "Master Data team (demo)"


def _clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


# =============================================================================
# SOURCES
# =============================================================================


def _sample_requests() -> list[dict[str, Any]]:
    if not DEMO_REQUESTS_FILE.exists():
        return []
    return json.loads(DEMO_REQUESTS_FILE.read_text(encoding="utf-8"))


def _portal_requests() -> list[dict[str, Any]]:
    """Requests submitted from the portal in demo mode (one JSON object per line)."""
    if not PORTAL_DEMO_REQUESTS_FILE.exists():
        return []

    rows = []

    for line in PORTAL_DEMO_REQUESTS_FILE.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue

        payload = record.get("payload") or {}
        info = payload.get("request_information") or {}
        customer = payload.get("existing_customer") or {}
        requested_at = _clean(record.get("requested_at"))[:16].replace("T", " ")

        rows.append(
            {
                "request_id": _clean(record.get("request_id")),
                "request_type": _clean(info.get("request_type")),
                "customer_id": _clean(info.get("customer_id")),
                "customer_name": _clean(customer.get("name_1")) or _clean(customer.get("customer_name")),
                "company_code": _clean(info.get("company_code")),
                "sales_org": _clean(info.get("sales_org")),
                "status": "ASSIGNED",
                "assigned_to": _clean((record.get("assignee") or {}).get("display_name")),
                "requested_by": _clean(record.get("requested_by")),
                "requested_at": requested_at,
                "updated_at": requested_at,
                "payload": payload,
                "original_defaults": record.get("original_defaults") or {},
            }
        )

    return rows


def _state() -> dict[str, Any]:
    if not DEMO_STATE_FILE.exists():
        return {}
    try:
        return json.loads(DEMO_STATE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_state(state: dict[str, Any]) -> None:
    DEMO_STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def _all_requests() -> dict[str, dict[str, Any]]:
    """Every request with the locally saved ticket / status applied."""
    state = _state()
    requests: dict[str, dict[str, Any]] = {}

    for row in _sample_requests() + _portal_requests():
        if not row.get("request_id"):
            continue

        row = copy.deepcopy(row)
        saved = state.get(row["request_id"], {})

        if saved.get("status"):
            row["status"] = saved["status"]
        if saved.get("updated_at"):
            row["updated_at"] = saved["updated_at"]

        internal = row["payload"].setdefault("workbench_internal", {})
        if "topdesk_ticket_number" in saved:
            internal["topdesk_ticket_number"] = saved["topdesk_ticket_number"]

        requests[row["request_id"]] = row

    return requests


def _enrich(row: dict[str, Any]) -> dict[str, Any]:
    internal = row["payload"].get("workbench_internal") or {}
    return {
        **row,
        "normalized_status": normalized_status(row.get("status", "")),
        "display_status": display_status(row.get("status", "")),
        "topdesk_ticket_number": _clean(internal.get("topdesk_ticket_number")),
    }


# =============================================================================
# SAME FUNCTIONS AS services/request_store.py
# =============================================================================


def current_user() -> str:
    headers = st.context.headers

    for key in ("x-forwarded-email", "x-forwarded-preferred-username", "x-forwarded-user"):
        value = _clean(headers.get(key))
        if value:
            return value

    return DEMO_USER


def list_requests(
    *,
    search: str = "",
    include_completed: bool = False,
) -> list[dict[str, Any]]:
    rows = [_enrich(row) for row in _all_requests().values()]

    if not include_completed:
        rows = [row for row in rows if _clean(row.get("status")).upper() not in {"COMPLETED", "REJECTED"}]

    needle = search.strip().lower()
    if needle:
        searchable = (
            "request_id", "customer_id", "customer_name", "company_code",
            "sales_org", "requested_by",
        )
        rows = [
            row
            for row in rows
            if any(needle in _clean(row.get(key)).lower() for key in searchable)
            or needle in json.dumps(row["payload"], ensure_ascii=False, default=str).lower()
        ]

    return [
        {key: value for key, value in row.items() if key not in ("payload", "original_defaults")}
        for row in sorted(rows, key=lambda r: (_clean(r.get("customer_name")), _clean(r.get("customer_id"))))
    ]


def get_request(request_id: str) -> dict[str, Any] | None:
    row = _all_requests().get(request_id)
    return _enrich(row) if row else None


def get_request_history(request_id: str) -> list[dict[str, Any]]:
    sample = next(
        (row.get("history", []) for row in _sample_requests() if row.get("request_id") == request_id),
        [],
    )
    saved = _state().get(request_id, {}).get("history", [])
    return sorted(saved + sample, key=lambda event: event.get("created_at", ""), reverse=True)


def _record_event(
    request_id: str,
    *,
    event_type: str,
    actor: str,
    comment: str,
    from_status: str,
    to_status: str,
    changes: dict[str, Any] | None = None,
) -> None:
    state = _state()
    entry = state.setdefault(request_id, {})
    entry.update(changes or {})
    entry["updated_at"] = _now()
    entry.setdefault("history", []).append(
        {
            "history_id": f"HIST-DEMO-{len(entry['history']) + 1}",
            "request_id": request_id,
            "event_type": event_type,
            "from_status": from_status,
            "to_status": to_status,
            "actor": actor,
            "comment": comment,
            "created_at": entry["updated_at"],
        }
    )
    _save_state(state)


def save_ticket_number(request_id: str, *, ticket_number: str, actor: str) -> dict[str, Any]:
    current = get_request(request_id)
    if current is None:
        raise KeyError(f"Request {request_id} was not found.")

    new_ticket = _clean(ticket_number)

    if new_ticket != current.get("topdesk_ticket_number"):
        _record_event(
            request_id,
            event_type="TOPDESK_TICKET_UPDATED",
            actor=actor,
            comment=f"TOPdesk ticket: {new_ticket or '(cleared)'}",
            from_status=_clean(current.get("status")),
            to_status=_clean(current.get("status")),
            changes={"topdesk_ticket_number": new_ticket},
        )

    return get_request(request_id)


def set_internal_status(request_id: str, *, status: str, actor: str, comment: str = "") -> dict[str, Any]:
    target = normalized_status(status)
    if target not in INTERNAL_STATUSES:
        raise ValueError(f"Unsupported internal status: {status}")

    current = get_request(request_id)
    if current is None:
        raise KeyError(f"Request {request_id} was not found.")

    _record_event(
        request_id,
        event_type="STATUS_CHANGED",
        actor=actor,
        comment=_clean(comment) or f"Internal status changed to {INTERNAL_STATUSES[target]}.",
        from_status=_clean(current.get("status")),
        to_status=target,
        changes={"status": target},
    )

    return get_request(request_id)


def add_history_event(request_id: str, *, event_type: str, actor: str, comment: str) -> None:
    current = get_request(request_id)
    status = _clean(current.get("status")) if current else ""
    _record_event(
        request_id,
        event_type=event_type,
        actor=actor,
        comment=comment,
        from_status=status,
        to_status=status,
    )
