"""Studio insights and pack actions. Brain is primary; local builders are the demo fallback."""

from __future__ import annotations

from pathlib import Path
from threading import Event, RLock
from time import monotonic
from typing import Any

import httpx

from services.brain_client import brain_base_url, brain_request_headers
from shared.db.repos import artifacts as artifact_repo
from shared.db.repos import chunks as chunk_repo
from shared.db.repos import projects as project_repo
from shared.logger_global import get_logger

log = get_logger(__name__)

_INSIGHT_TTL_S = 30.0
_INSIGHT_LOCK = RLock()
_INSIGHT_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_INSIGHT_IN_FLIGHT: dict[str, Event] = {}


def insights_for_owner(project_id: str, owner_id: str) -> dict[str, Any] | None:
    project = project_repo.get_for_owner_or_none(project_id, owner_id)
    if project is None:
        return None
    cache_key = f"{owner_id}:{project_id}"
    now = monotonic()
    with _INSIGHT_LOCK:
        cached = _INSIGHT_CACHE.get(cache_key)
        if cached and now - cached[0] < _INSIGHT_TTL_S:
            return cached[1]
        pending = _INSIGHT_IN_FLIGHT.get(cache_key)
        if pending is None:
            pending = Event()
            _INSIGHT_IN_FLIGHT[cache_key] = pending
            is_leader = True
        else:
            is_leader = False

    if not is_leader:
        # A concurrent poll is already doing the expensive work. Wait briefly
        # for its result, then serve the last known payload rather than fan out
        # another AI Brain request.
        pending.wait(timeout=2.0)
        with _INSIGHT_LOCK:
            cached = _INSIGHT_CACHE.get(cache_key)
            if cached:
                return cached[1]
        return _build_local_insights(project_id, project, owner_id)

    try:
        payload = _brain_get(f"/v1/projects/{project_id}/insights")
        if payload.get("project_id"):
            result = payload
        else:
            result = _build_local_insights(project_id, project, owner_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("brain insights fallback: {}", exc)
        try:
            result = _build_local_insights(project_id, project, owner_id)
        except Exception:
            # Fallback itself failed — release waiters and surface the real
            # error instead of masking it with an unbound `result` in finally.
            with _INSIGHT_LOCK:
                waiter = _INSIGHT_IN_FLIGHT.pop(cache_key, None)
                if waiter:
                    waiter.set()
            raise
    with _INSIGHT_LOCK:
        _INSIGHT_CACHE[cache_key] = (monotonic(), result)
        waiter = _INSIGHT_IN_FLIGHT.pop(cache_key, None)
        if waiter:
            waiter.set()
    return result


def _build_local_insights(project_id: str, project: Any, owner_id: str) -> dict[str, Any]:
    import contextvars
    from concurrent.futures import ThreadPoolExecutor

    from ai_brain.core.procurement_ai.insights import build_insight_payload

    # Each call opens its own NullPool DBSQL connection (OBO-scoped, not
    # pooled/reusable) — run them concurrently instead of two round trips.
    # ThreadPoolExecutor workers do not inherit contextvars, so the visitor
    # OBO token must be copied in explicitly or these silently run as the
    # app service principal instead (which lacks the visitor's UC grants).
    # Each thread needs its OWN Context — the same Context cannot be
    # entered concurrently from two threads (raises RuntimeError).
    with ThreadPoolExecutor(max_workers=2) as pool:
        artifacts_future = pool.submit(
            contextvars.copy_context().run, artifact_repo.list_for_project, project_id, owner_id
        )
        chunks_future = pool.submit(
            contextvars.copy_context().run, chunk_repo.list_for_project, project_id
        )
        artifacts = artifacts_future.result()
        chunks = chunks_future.result()
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

    if capability == "kb_build":
        # enqueue_kb_build already copies the OBO context onto its own thread.
        from ai_brain.core.kb.extract import job_store
        from ai_brain.core.kb.extract.ingest import enqueue_kb_build

        # A second build races the first onto the same evidence rows, doubling
        # cost and per-vendor counts. A dead run is reaped first, so this cannot
        # wedge the project.
        job_store.reap_stalled(project_id)
        live = job_store.latest_status_map([project_id]).get(project_id)
        if live == "building":
            return {
                "route": "procurement",
                "thread_id": thread_id,
                "procurement": {"kb_status": "building"},
            }

        enqueue_kb_build(project_id)
        return {
            "route": "procurement",
            "thread_id": thread_id,
            "procurement": {"kb_status": "building"},
        }

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
    # Insights are a read model. A slow brain must not make every active
    # workspace poll wait 15 seconds before the local/cache fallback responds.
    with httpx.Client(timeout=httpx.Timeout(2.0, connect=1.0)) as client:
        response = client.get(url, headers=brain_request_headers())
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
        response = client.post(url, json=payload, headers=brain_request_headers())
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise ValueError("brain did not return an object")
        return body
