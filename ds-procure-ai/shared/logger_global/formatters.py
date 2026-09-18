"""Log line format strings for pretty and JSON sinks."""

from __future__ import annotations

import json
from typing import Any

PRETTY_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{extra[service]}</cyan> | "
    "<cyan>{extra[module]}</cyan> | "
    "rid=<yellow>{extra[request_id]}</yellow> | "
    "wf=<yellow>{extra[workflow]}</yellow> | "
    "{message}"
)


def dump_json_record(record: dict[str, Any]) -> str:
    """One flat JSON object per line — readable in Databricks Apps /logz."""
    extra = record.get("extra") or {}
    level = record.get("level")
    level_name = level.name if hasattr(level, "name") else str(level)
    time_value = record.get("time")
    if hasattr(time_value, "isoformat"):
        time_str = time_value.isoformat(timespec="milliseconds")
    else:
        time_str = str(time_value)

    payload: dict[str, Any] = {
        "time": time_str,
        "level": level_name,
        "service": extra.get("service") or "-",
        "module": extra.get("module") or "-",
        "request_id": extra.get("request_id") or "-",
        "workflow": extra.get("workflow") or "-",
        "project_id": extra.get("project_id") or "-",
        "message": record.get("message") or "",
    }
    user_id = extra.get("user_id")
    if user_id and user_id != "-":
        payload["user_id"] = user_id

    exception = record.get("exception")
    if exception:
        formatter = getattr(exception, "format", None)
        payload["exception"] = (
            "".join(formatter()) if callable(formatter) else str(exception)
        )

    return json.dumps(payload, ensure_ascii=False, default=str)


def json_format(record: dict[str, Any]) -> str:
    record["extra"]["json_line"] = dump_json_record(record)
    return "{extra[json_line]}\n"
