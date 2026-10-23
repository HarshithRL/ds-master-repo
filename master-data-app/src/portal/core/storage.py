"""Local request log used in demo mode (one JSON object per line)."""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from portal.config import DEMO_REQUESTS_FILE
from portal.core.utils import clean


def _json_default(obj):
    return obj.isoformat() if isinstance(obj, (date, datetime)) else str(obj)


def save_demo_request(**record) -> None:
    with DEMO_REQUESTS_FILE.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, default=_json_default, ensure_ascii=False) + "\n")


def demo_requests_for(requester_email: str, limit: int = 8) -> list[dict[str, Any]]:
    """Newest demo requests submitted by this requester (summary fields only)."""
    if not requester_email or not DEMO_REQUESTS_FILE.exists():
        return []

    summaries = []

    for line in DEMO_REQUESTS_FILE.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue

        if clean(record.get("requested_by")).casefold() != requester_email.casefold():
            continue

        payload = record.get("payload") or {}
        info = payload.get("request_information") or {}
        customer = payload.get("existing_customer") or {}
        summaries.append(
            {
                "request_id": clean(record.get("request_id")),
                "request_type": clean(info.get("request_type")),
                "customer_name": clean(customer.get("name_1")),
                "customer_id": clean(info.get("customer_id")),
                "requested_at": clean(record.get("requested_at"))[:16].replace("T", " "),
                "status": "",
            }
        )

    return list(reversed(summaries))[:limit]
