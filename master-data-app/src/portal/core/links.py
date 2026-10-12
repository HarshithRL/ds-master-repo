"""Links into the Customer Master Workbench (Master Data team only)."""

from __future__ import annotations

from urllib.parse import quote

from portal.config import setting

# Query parameter the Workbench reads to open one request directly
REQUEST_PARAM = "request"


def workbench_request_url(request_id: str) -> str:
    """Workbench URL that opens this request, or "" when no Workbench is configured."""
    base = setting("WORKBENCH_URL").rstrip("/")

    if not base:
        return ""

    return f"{base}/?{REQUEST_PARAM}={quote(request_id)}"
