"""Studio insights and pack actions. Brain is primary; local builders are the demo fallback."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from services.brain_client import brain_base_url
from shared.db.repos import artifacts as artifact_repo
from shared.db.repos import chunks as chunk_repo
from shared.db.repos import projects as project_repo
from shared.logger_global import get_logger

log = get_logger(__name__)


def insights_for_owner(project_id: str, owner_id: str) -> dict[str, Any] | None:
    project = project_repo.get_for_owner_or_none(project_id, owner_id)
    if project is None:
        return None
    try:
        payload = _brain_get(f"/v1/projects/{project_id}/insights")
        if payload.get("project_id"):
            return payload
    except Exception as exc:  # noqa: BLE001
        log.warning("brain insights fallback: {}", exc)
    from ai_brain.core.procurement_ai.insights import build_insight_payload

    artifacts = artifact_repo.list_for_project(project_id, owner_id)
    chunks = chunk_repo.list_for_project(project_id)
    return build_insight_payload(project, artifacts, chunks)


def packs_for_owner(project_id: str, owner_id: str) -> dict[str, Any] | None:
    if project_repo.get_for_owner_or_none(project_id, owner_id) is None:
        return None
    try:
        return _brain_get(f"/v1/projects/{project_id}/packs")
    except Exception as exc:  # noqa: BLE001
        log.warning("brain packs fallback: {}", exc)
        from ai_brain.core.procurement_ai.packs import store as pack_store

        return pack_store.read_status(project_id)


def start_pack(project_id: str, owner_id: str, capability: str) -> dict[str, Any] | None:
    if project_repo.get_for_owner_or_none(project_id, owner_id) is None:
        return None
    thread_id = f"{project_id}:{capability}"
    try:
        return _brain_post(
            f"/v1/projects/{project_id}/runs",
            {"capability": capability, "message": capability, "thread_id": thread_id},
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("brain run fallback capability={}: {}", capability, exc)
        return _local_pack(project_id, owner_id, capability, thread_id)


def pack_download_path(project_id: str, owner_id: str, kind: str) -> Path | None:
    if project_repo.get_for_owner_or_none(project_id, owner_id) is None:
        return None
    from ai_brain.core.procurement_ai.packs import store as pack_store

    status = pack_store.read_status(project_id).get(kind) or {}
    filename = status.get("filename")
    if not filename:
        return None
    path = pack_store.pack_file(project_id, filename)
    from shared.db.volume_fs import exists as vol_exists
    return path if vol_exists(path) else None


def _local_pack(project_id: str, owner_id: str, capability: str, thread_id: str) -> dict[str, Any]:
    from ai_brain.core.procurement_ai.insights import build_insight_payload
    from ai_brain.core.procurement_ai.packs.compare_xlsx import build_comparison_xlsx
    from ai_brain.core.procurement_ai.packs.steerco_ppt import build_steerco_ppt

    project = project_repo.get_for_owner(project_id, owner_id)
    artifacts = artifact_repo.list_for_project(project_id, owner_id)
    chunks = chunk_repo.list_for_project(project_id)
    if capability == "compare_xlsx":
        insights = build_insight_payload(project, artifacts, chunks)
        result = build_comparison_xlsx(
            project_id,
            insights,
            thread_id=thread_id,
            chunks=chunks,
            artifacts=artifacts,
        )
        return {
            "route": "procurement",
            "thread_id": thread_id,
            "procurement": {
                "xlsx_status": result["status"],
                "xlsx_href": result.get("href") or "",
                "evidence_used": bool(result.get("evidence_used")),
            },
        }
    if capability == "steerco_ppt":
        result = build_steerco_ppt(project_id, thread_id=thread_id)
        return {
            "route": "procurement",
            "thread_id": thread_id,
            "procurement": {"ppt_status": result["status"], "ppt_href": result.get("href")},
        }
    raise ValueError(f"unsupported local capability {capability}")


def _brain_get(path: str) -> dict[str, Any]:
    url = f"{brain_base_url()}{path}"
    with httpx.Client(timeout=5.0) as client:
        response = client.get(url)
        if response.status_code == 404:
            raise LookupError(f"brain {path} not found")
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise ValueError("brain did not return an object")
        return body


def _brain_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{brain_base_url()}{path}"
    with httpx.Client(timeout=180.0) as client:
        response = client.post(url, json=payload)
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise ValueError("brain did not return an object")
        return body
