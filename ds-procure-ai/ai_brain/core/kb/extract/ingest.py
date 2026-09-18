"""Async pipelined ingest: parse (sem 4) overlaps extract (sem 8) via a queue.

Upload stores the blob with parse_status=pending and enqueues this pipeline.
HTTP accept must not wait for parse. Extraction is a stub until W5; embed/graph
are no-op stubs until W6/W7.
"""

from __future__ import annotations

import asyncio
import os
import inspect
import sys
import contextvars
import threading
import time
import traceback
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

from shared.artifacts.exceptions import UnsupportedArtifact
from shared.db.connection import session_scope
from shared.db.models import Artifact
from shared.db.repos import artifacts as artifact_repo
from shared.logger_global import get_logger
from sqlalchemy import func, select

log = get_logger(__name__)

SENTINEL = object()
PARSE_CONCURRENCY = 4
EXTRACT_CONCURRENCY = 8
RFP_PRIORITY = 0
DEFAULT_PRIORITY = 1
SENTINEL_PRIORITY = 10**9
PARSE_PENDING = "pending"
PARSE_OK = "ok"
PARSE_ERROR = "error"
PARSE_SKIPPED = "skipped"

ParseFn = Callable[[Artifact], Any]
ExtractFn = Callable[[Artifact, Any], Any]
QualityFn = Callable[[Artifact], Any]
EmbedFn = Callable[..., Any]
GraphFn = Callable[[str], Any]
LoadFn = Callable[[str], Artifact]
EventFn = Callable[..., None]

T = TypeVar("T")


@dataclass
class IngestReport:
    project_id: str
    parsed_ok: list[str] = field(default_factory=list)
    extracted_ok: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failures: list[tuple[str, str]] = field(default_factory=list)

    def failed(self, artifact_id: str, exc: BaseException | str) -> None:
        self.failures.append((artifact_id, str(exc)))


def is_rfp_priority(artifact: Artifact) -> bool:
    role = (getattr(artifact, "doc_role", None) or "").strip().lower()
    if role == "rfp":
        return True
    name = (getattr(artifact, "original_name", None) or "").lower()
    return "rfp" in name


def load_artifact(artifact_id: str) -> Artifact:
    with session_scope() as session:
        row = session.get(Artifact, artifact_id)
        if row is None:
            raise LookupError(f"artifact not found: {artifact_id}")
        session.expunge(row)
        return row


def _ensure_backend_on_path() -> None:
    root = Path(__file__).resolve().parents[3]
    backend = str(root / "backend")
    if backend not in sys.path:
        sys.path.insert(0, backend)


def _parse_and_store(artifact: Artifact) -> Artifact:
    """Persist via the existing Flask helper (chunks + parsed_json + status)."""
    _ensure_backend_on_path()
    from services.artifact_parse import parse_and_store

    return parse_and_store(artifact)


async def extract_artifact(artifact: Artifact, doc: Any = None) -> None:
    """Classify vendor_id + doc_role (filename first). Deep-agent extract is kb_build."""
    from ai_brain.core.kb.extract.classify import classify_and_pin

    project_id = getattr(artifact, "project_id", "") or ""
    name = getattr(artifact, "original_name", "") or ""
    aid = getattr(artifact, "id", "") or ""
    if project_id and aid:
        pinned = classify_and_pin(project_id, aid, name)
        log.info(
            "ingest classify artifact_id={} name={} pinned={}",
            aid,
            name,
            pinned,
        )
    else:
        log.info("ingest classify skip artifact_id={} name={}", aid, name)


async def embed_pending_chunks(project_id: str, batch_size: int = 64) -> None:
    """W6 hook: batch embeddings after the extract queue drains."""
    log.info("ingest embed stub skip project_id={} batch_size={}", project_id, batch_size)


async def resolve_entities_and_write_graph(project_id: str) -> None:
    """W7 hook: entity resolution after ALL extractions finish."""
    log.info("ingest graph stub skip project_id={}", project_id)


async def _maybe_await(fn: Callable[..., T | Awaitable[T]], *args: Any, **kwargs: Any) -> T:
    result = fn(*args, **kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


async def _call_parse(parse_fn: ParseFn, artifact: Artifact) -> Artifact:
    if inspect.iscoroutinefunction(parse_fn):
        return await parse_fn(artifact)
    return await asyncio.to_thread(parse_fn, artifact)


async def _call_extract(extract_fn: ExtractFn, artifact: Artifact, doc: Any) -> None:
    if inspect.iscoroutinefunction(extract_fn):
        await extract_fn(artifact, doc)
        return
    await asyncio.to_thread(extract_fn, artifact, doc)


def _emit(on_event: EventFn | None, event: str, **fields: Any) -> None:
    artifact_id = fields.get("artifact_id", "")
    log.info(
        "ingest {} artifact_id={} t={:.3f}",
        event,
        artifact_id,
        time.monotonic(),
    )
    if on_event is None:
        return
    try:
        on_event(event, **fields)
    except TypeError:
        on_event(event, fields)


def _run_quality(artifact: Artifact) -> Any:
    from ai_brain.core.kb.build.quality import document_from_artifact, persist_flags, run_quality_detectors

    doc = document_from_artifact(artifact)
    flags = run_quality_detectors(artifact, doc)
    persist_flags(artifact.project_id, artifact.id, flags)
    return doc


def _mark_parse_failure(artifact: Artifact, status: str, detail: str) -> None:
    try:
        artifact_repo.save_parse_result(artifact.id, parse_status=status, parse_error=detail)
    except Exception:
        log.exception("mark parse status failed artifact_id={} status={}", artifact.id, status)


async def ingest_project(
    project_id: str,
    artifact_ids: Sequence[str],
    *,
    on_event: EventFn | None = None,
    parse_fn: ParseFn | None = None,
    extract_fn: ExtractFn | None = None,
    quality_fn: QualityFn | None = None,
    embed_fn: EmbedFn | None = None,
    graph_fn: GraphFn | None = None,
    load_artifact_fn: LoadFn | None = None,
    parse_concurrency: int = PARSE_CONCURRENCY,
    extract_concurrency: int = EXTRACT_CONCURRENCY,
) -> IngestReport:
    """Parse up to `parse_concurrency` artifacts while extract workers drain a priority queue.

    RFP artifacts (`rfp` in filename or doc_role) are dequeued first. One failure
    never cancels the rest of the batch. Embed + graph run only after the queue drains.
    """
    parse_impl = parse_fn or _parse_and_store
    extract_impl = extract_fn or extract_artifact
    quality_impl = _run_quality if quality_fn is None else quality_fn
    embed_impl = embed_fn or embed_pending_chunks
    graph_impl = graph_fn or resolve_entities_and_write_graph
    load_impl = load_artifact_fn or load_artifact

    parse_sem = asyncio.Semaphore(parse_concurrency)
    extract_sem = asyncio.Semaphore(extract_concurrency)
    queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
    seq = 0
    seq_lock = asyncio.Lock()
    report_lock = asyncio.Lock()
    report = IngestReport(project_id=project_id)

    async def _next_seq() -> int:
        nonlocal seq
        async with seq_lock:
            seq += 1
            return seq

    async def parse_one(aid: str) -> None:
        artifact = None
        try:
            artifact = await _maybe_await(load_impl, aid)
            _emit(on_event, "parse_start", artifact_id=aid)
            async with parse_sem:
                saved = await _call_parse(parse_impl, artifact)
            status = (getattr(saved, "parse_status", None) or "").strip()
            _emit(on_event, "parse_done", artifact_id=aid, parse_status=status)
            if status != PARSE_OK:
                async with report_lock:
                    report.skipped.append(aid)
                return
            async with report_lock:
                report.parsed_ok.append(aid)
            doc = None
            try:
                doc = await _maybe_await(quality_impl, saved)
            except Exception as exc:
                log.exception("quality detectors failed artifact_id={}", aid)
                async with report_lock:
                    report.failed(aid, exc)
            priority = RFP_PRIORITY if is_rfp_priority(saved) else DEFAULT_PRIORITY
            await queue.put((priority, await _next_seq(), (saved, doc)))
        except UnsupportedArtifact as exc:
            log.info("parse skipped artifact_id={} detail={}", aid, exc)
            if artifact is not None:
                _mark_parse_failure(artifact, PARSE_SKIPPED, str(exc))
            async with report_lock:
                report.skipped.append(aid)
            _emit(on_event, "parse_done", artifact_id=aid, parse_status=PARSE_SKIPPED)
        except Exception as exc:
            log.exception("parse failed artifact_id={}", aid)
            if artifact is not None:
                _mark_parse_failure(artifact, PARSE_ERROR, str(exc))
            async with report_lock:
                report.failed(aid, exc)
            _emit(on_event, "parse_error", artifact_id=aid, error=str(exc))

    async def extract_worker() -> None:
        while True:
            _priority, _seq, item = await queue.get()
            try:
                if item is SENTINEL:
                    return
                artifact, doc = item
                aid = artifact.id
                try:
                    _emit(on_event, "extract_start", artifact_id=aid)
                    async with extract_sem:
                        await _call_extract(extract_impl, artifact, doc)
                    _emit(on_event, "extract_done", artifact_id=aid)
                    async with report_lock:
                        report.extracted_ok.append(aid)
                except Exception as exc:
                    log.exception("extract failed artifact_id={}", aid)
                    async with report_lock:
                        report.failed(aid, exc)
                    _emit(on_event, "extract_error", artifact_id=aid, error=str(exc))
            finally:
                queue.task_done()

    worker_count = max(1, extract_concurrency)
    workers = [asyncio.create_task(extract_worker()) for _ in range(worker_count)]
    parse_coros = [parse_one(aid) for aid in artifact_ids]
    if parse_coros:
        await asyncio.gather(*parse_coros)
    for _ in workers:
        await queue.put((SENTINEL_PRIORITY, await _next_seq(), SENTINEL))
    await asyncio.gather(*workers)

    if embed_fn is None:
        await embed_pending_chunks(project_id, batch_size=64)
    else:
        await _maybe_await(embed_impl, project_id)
    if graph_fn is None:
        await resolve_entities_and_write_graph(project_id)
    else:
        await _maybe_await(graph_impl, project_id)
    _emit(on_event, "ingest_done", artifact_id="", project_id=project_id)
    return report


def _run_ingest_thread(project_id: str, artifact_ids: list[str]) -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(ingest_project(project_id, artifact_ids))
    except Exception:
        log.exception("ingest thread failed project_id={}", project_id)
        _set_kb_job(
            project_id,
            status="failed",
            message="File parse failed.",
            error="ingest thread failed",
        )
        return
    if _auto_kb_build_enabled():
        enqueue_kb_build(project_id)
    else:
        _set_kb_job(
            project_id,
            status="staged",
            message="Files parsed. Knowledge base build is off.",
        )


def _auto_kb_build_enabled() -> bool:
    if os.getenv("PYTEST_CURRENT_TEST"):
        return os.getenv("KB_AUTO_BUILD", "0").strip().lower() in {"1", "true", "yes"}
    return os.getenv("KB_AUTO_BUILD", "1").strip().lower() not in {"0", "false", "no"}


def enqueue_kb_build(project_id: str) -> threading.Thread | None:
    """Start kb_build after parse/classify. Does not write Excel.

    MATE_KB_BUILD_MODE=job runs it as a durable Databricks Job (survives app
    restarts); the default `thread` mode keeps the original in-process path.
    Returns the thread for thread mode, None for job mode.
    """
    from ai_brain.core.kb.extract import dispatch, job_store

    mode = dispatch.build_mode()
    log.info("enqueue kb_build project_id={} mode={}", project_id, mode)
    kb_job_id = job_store.create_job(project_id, mode=mode)

    if mode == dispatch.MODE_JOB:
        try:
            run_id = dispatch.submit_databricks_job(project_id, kb_job_id)
            job_store.mark_running(kb_job_id, project_id, run_id=run_id)
            return None
        except Exception as exc:
            # Submission failed (misconfig, permissions). Fall back to the
            # in-process path rather than leaving the project with no build.
            log.exception(
                "kb_build job submit failed project_id={}, falling back to thread",
                project_id,
            )
            job_store.finish(
                kb_job_id,
                project_id,
                status="queued",
                message="Job submit failed; running in-process instead.",
                error=f"{type(exc).__name__}: {exc}",
            )
            kb_job_id = job_store.create_job(project_id, mode=dispatch.MODE_THREAD)

    job_store.mark_running(kb_job_id, project_id)
    # Propagate visitor OBO context for UC writes in kb_build.
    ctx = contextvars.copy_context()
    thread = threading.Thread(
        target=ctx.run,
        args=(_run_kb_build_thread, project_id, kb_job_id),
        daemon=True,
        name=f"kb-build-{project_id[:12]}",
    )
    thread.start()
    return thread


def _run_kb_build_thread(project_id: str, kb_job_id: str = "") -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    from ai_brain.core.kb.extract import dispatch, job_store

    stop_heartbeat = dispatch.start_heartbeat(kb_job_id) if kb_job_id else None
    try:
        from ai_brain.core.kb.extract.runner import run_kb_build

        run_kb_build(project_id)
    except Exception as exc:
        log.exception("kb_build thread failed project_id={}", project_id)
        # Persist the real exception: app logs rotate within minutes, so this
        # status file is the only durable record of why a build failed.
        detail = "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        )[-4000:]
        message = f"Knowledge base build failed: {type(exc).__name__}: {exc}"[:500]
        if kb_job_id:
            job_store.finish(
                kb_job_id, project_id, status="failed", message=message, error=detail
            )
        else:
            _set_kb_job(project_id, status="failed", message=message, error=detail)
    else:
        if kb_job_id:
            from ai_brain.core.procurement_ai.packs import store as pack_store

            kb = pack_store.read_status(project_id).get("kb") or {}
            job_store.finish(
                kb_job_id,
                project_id,
                status=str(kb.get("status") or "ready"),
                message=kb.get("message"),
                error=kb.get("error"),
            )
    finally:
        if stop_heartbeat is not None:
            stop_heartbeat.set()


def pending_artifact_ids(project_id: str) -> list[str]:
    """Artifact ids still waiting to parse (pending or empty status)."""
    if not project_id:
        return []
    with session_scope() as session:
        rows = session.scalars(
            select(Artifact)
            .where(Artifact.project_id == project_id)
            .order_by(Artifact.created_at.asc())
        ).all()
        return [
            row.id
            for row in rows
            if (row.parse_status or PARSE_PENDING).strip() == PARSE_PENDING
        ]


def _usable_markdown(parsed_json: str | None) -> bool:
    if not parsed_json:
        return False
    import json

    try:
        data = json.loads(parsed_json)
    except json.JSONDecodeError:
        return False
    if not isinstance(data, dict):
        return False
    markdown = data.get("markdown")
    return isinstance(markdown, str) and bool(markdown.strip())


def stale_ok_artifact_ids(project_id: str) -> list[str]:
    """parse_status=ok but missing SQL chunks or usable parsed_json.markdown — reparse."""
    if not project_id:
        return []
    from shared.db.models import Chunk

    with session_scope() as session:
        rows = session.scalars(
            select(Artifact)
            .where(Artifact.project_id == project_id, Artifact.parse_status == PARSE_OK)
            .order_by(Artifact.created_at.asc())
        ).all()
        stale: list[str] = []
        for row in rows:
            chunk_count = session.scalar(
                select(func.count()).select_from(Chunk).where(Chunk.artifact_id == row.id)
            ) or 0
            if int(chunk_count) < 1 or not _usable_markdown(row.parsed_json):
                stale.append(row.id)
        return stale


async def ensure_parsed_for_matrix(project_id: str) -> IngestReport:
    """Parse pending uploads and reparse ok-but-empty corpus. Does not start kb_build."""
    ids = pending_artifact_ids(project_id)
    for aid in stale_ok_artifact_ids(project_id):
        if aid not in ids:
            ids.append(aid)
    if not ids:
        return IngestReport(project_id=project_id)
    from shared.db.repos import artifacts as artifact_repo

    for aid in ids:
        try:
            artifact_repo.save_parse_result(aid, parse_status=PARSE_PENDING, parse_error=None)
        except Exception:
            log.exception("reset parse_status pending failed artifact_id={}", aid)
    return await ingest_project(project_id, ids)

def enqueue_ingest(project_id: str, artifact_ids: Sequence[str]) -> threading.Thread:
    """Fire-and-forget background ingest. Must not block the HTTP handler."""
    ids = list(artifact_ids)
    log.info("enqueue ingest project_id={} artifacts={}", project_id, len(ids))
    _set_kb_job(
        project_id,
        status="ingesting",
        message="Parsing uploaded files…",
    )
    # Capture the visitor OBO context so background thread can write UC tables.
    ctx = contextvars.copy_context()
    thread = threading.Thread(
        target=ctx.run,
        args=(_run_ingest_thread, project_id, ids),
        daemon=True,
        name=f"kb-ingest-{project_id[:12]}",
    )
    thread.start()
    return thread


def _set_kb_job(
    project_id: str,
    *,
    status: str,
    message: str | None = None,
    error: str | None = None,
) -> None:
    try:
        from ai_brain.core.procurement_ai.packs.store import write_kb_job

        write_kb_job(project_id, status=status, message=message, error=error)
    except Exception:
        log.exception("kb job status write failed project_id={}", project_id)
