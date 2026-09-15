"""On-disk pack status for comparison Excel and SteerCo PPT."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shared.db.paths import project_root, projects_data_root
from shared.db.volume_fs import ensure_dir, exists as vol_exists, read_text as vol_read_text, write_text as vol_write_text

KINDS = ("xlsx", "ppt")
VIEW_KINDS = ("overview", "requirements", "vendors")
_IDLE_PACK = {
    "status": "idle",
    "href": None,
    "thread_id": None,
    "filename": None,
}
_IDLE_KB = {"status": "idle", "message": None, "error": None}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def packs_dir(project_id: str) -> Path:
    path = project_root(project_id) / "packs"
    ensure_dir(path)
    return path


def status_path(project_id: str) -> Path:
    return packs_dir(project_id) / "status.json"


def _pack_row(row: dict[str, Any] | None) -> dict[str, Any]:
    row = row if isinstance(row, dict) else {}
    return {
        "status": row.get("status") or "idle",
        "href": row.get("href"),
        "thread_id": row.get("thread_id"),
        "filename": row.get("filename"),
        "error": row.get("error"),
        "updated_at": row.get("updated_at"),
    }


def _kb_row(row: dict[str, Any] | None) -> dict[str, Any]:
    row = row if isinstance(row, dict) else {}
    return {
        "status": row.get("status") or "idle",
        "message": row.get("message"),
        "error": row.get("error"),
        "updated_at": row.get("updated_at"),
    }


def read_status(project_id: str) -> dict[str, Any]:
    path = status_path(project_id)
    if not vol_exists(path):
        return {"xlsx": dict(_IDLE_PACK), "ppt": dict(_IDLE_PACK), "kb": dict(_IDLE_KB)}
    try:
        data = json.loads(vol_read_text(path))
    except (json.JSONDecodeError, Exception):
        data = {}
    return {
        "xlsx": _pack_row(data.get("xlsx") if isinstance(data.get("xlsx"), dict) else None),
        "ppt": _pack_row(data.get("ppt") if isinstance(data.get("ppt"), dict) else None),
        "kb": _kb_row(data.get("kb") if isinstance(data.get("kb"), dict) else None),
    }


def kb_is_building(project_id: str) -> bool:
    """True while ingest/kb_build is in progress — do not overwrite Excel."""
    status = str((read_status(project_id).get("kb") or {}).get("status") or "")
    return status in {"building", "ingesting"}


def pack_status(project_id: str) -> dict[str, Any]:
    return read_status(project_id)


def _write_status(project_id: str, current: dict[str, Any]) -> dict[str, Any]:
    vol_write_text(status_path(project_id), json.dumps(current, indent=2))
    return current


def write_status(project_id: str, kind: str, **fields: Any) -> dict[str, Any]:
    if kind not in KINDS:
        raise ValueError(f"unknown pack kind: {kind}")
    current = read_status(project_id)
    current[kind] = {**current[kind], **fields, "updated_at": utc_now_iso()}
    return _write_status(project_id, current)


def write_kb_job(
    project_id: str,
    *,
    status: str,
    message: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """Persist ingest/kb_build progress for Studio polling. Does not wipe pack rows."""
    if not (project_id or "").strip():
        return {}
    current = read_status(project_id)
    current["kb"] = {
        "status": status,
        "message": message,
        "error": error,
        "updated_at": utc_now_iso(),
    }
    return _write_status(project_id, current)


def views_dir(project_id: str) -> Path:
    path = packs_dir(project_id) / "views"
    ensure_dir(path)
    return path


def view_path(project_id: str, kind: str) -> Path:
    if kind not in VIEW_KINDS:
        raise ValueError(f"unknown view kind: {kind}")
    return views_dir(project_id) / f"{kind}.json"


def write_view(project_id: str, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Graph hand-off cache. APIs still assemble live from SQL."""
    if not (project_id or "").strip():
        return payload
    if kind not in VIEW_KINDS:
        raise ValueError(f"unknown view kind: {kind}")
    vol_write_text(
        view_path(project_id, kind),
        json.dumps(payload, indent=2, default=str),
    )
    return payload


def read_view(project_id: str, kind: str) -> dict[str, Any] | None:
    if not (project_id or "").strip() or kind not in VIEW_KINDS:
        return None
    path = view_path(project_id, kind)
    if not vol_exists(path):
        return None
    try:
        data = json.loads(vol_read_text(path))
    except (json.JSONDecodeError, Exception):
        return None
    return data if isinstance(data, dict) else None


def pack_file(project_id: str, filename: str) -> Path:
    return packs_dir(project_id) / filename


def flask_href(project_id: str, kind: str) -> str:
    return f"/api/procurement/projects/{project_id}/packs/{kind}/download"
