"""
Request store used by the app: demo data or the Databricks tables.

Both modules offer the same functions; services.config.DEMO_MODE picks one.
The Databricks implementation (services/request_store.py) is unchanged.
"""

from __future__ import annotations

from workbench.services.config import DEMO_MODE

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

if DEMO_MODE:
    from workbench.services.demo_store import (  # noqa: F401
        INTERNAL_STATUSES,
        add_history_event,
        current_user,
        display_status,
        get_request,
        get_request_history,
        list_requests,
        normalized_status,
        save_ticket_number,
        set_internal_status,
    )
else:
    from workbench.services.request_store import (  # noqa: F401
        INTERNAL_STATUSES,
        add_history_event,
        current_user,
        display_status,
        get_request,
        get_request_history,
        list_requests,
        normalized_status,
        save_ticket_number,
        set_internal_status,
    )
