"""Graph ingest for uploaded files. SQL chunks + parsed_json are source of truth."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from langgraph.types import Send
from shared.db.connection import session_scope
from shared.db.models import Artifact, Chunk
from shared.db.repos import artifacts as artifact_repo
from shared.db.repos import chunks as chunk_repo
from shared.logger_global import get_logger
from sqlalchemy import func, select

log = get_logger(__name__, service="ai_brain")

MAX_FILES = 15
DI_CONCURRENCY = 5
_DI_SEM = asyncio.Semaphore(DI_CONCURRENCY)

# Ephemeral memory store — gated. Matrix/MCP tools read SQL; do not treat this as truth.
_CHUNK_STORE: dict[str, list[dict[str, Any]]] = {}


def _memory_chunk_store_enabled() -> bool:
    return os.getenv("MATE_USE_MEMORY_CHUNK_STORE", "0").strip().lower() in {"1", "true", "yes"}


def count_files(project_id: str) -> int:
    with session_scope() as session:
        return int(
            session.scalar(
                select(func.count()).select_from(Artifact).where(Artifact.project_id == project_id)
            )
            or 0
        )


def pending_files(project_id: str) -> list[dict[str, Any]]:
    if not project_id:
        return []
    with session_scope() as session:
        rows = session.scalars(
            select(Artifact)
            .where(Artifact.project_id == project_id, Artifact.parse_status == "pending")
            .order_by(Artifact.created_at.asc())
        ).all()
        return [_file_card(row) for row in rows]


def _file_card(row: Artifact) -> dict[str, Any]:
    return {
        "file_id": row.id,
        "filename": row.original_name,
        "status": row.parse_status or "pending",
        "storage_relpath": row.storage_relpath,
    }


def route_new_files(state: dict[str, Any]) -> list[Send] | str:
    project_id = str(state.get("project_id") or "").strip()
    files = pending_files(project_id)
    if not files:
        return "assistant"
    log.info("ingest fanout project_id={} files={}", project_id, len(files))
    return [Send("parse_one", {"project_id": project_id, "file": item}) for item in files]

async def parse_one(task: dict[str, Any]) -> dict[str, Any]:
    """Parse via shared ArtifactHandler path that persists parsed_json + SQL chunks."""
    file_card = dict(task.get("file") or {})
    project_id = str(task.get("project_id") or "").strip()
    file_id = str(file_card.get("file_id") or "")
    filename = str(file_card.get("filename") or "")
    try:
        from ai_brain.core.kb.extract.ingest import load_artifact

        # Prefer package import; fall back for apps that put backend on sys.path.
        try:
            from backend.services.artifact_parse import parse_and_store
        except ImportError:  # pragma: no cover
            import sys
            from pathlib import Path

            root = Path(__file__).resolve().parents[3]
            backend = str(root / "backend")
            if backend not in sys.path:
                sys.path.insert(0, backend)
            from services.artifact_parse import parse_and_store

        artifact = await asyncio.to_thread(load_artifact, file_id)
        async with _DI_SEM:
            saved = await asyncio.to_thread(parse_and_store, artifact)
        status = (getattr(saved, "parse_status", None) or "").strip()
        if status != "ok":
            detail = getattr(saved, "parse_error", None) or "parse did not succeed"
            raise RuntimeError(detail)
        markdown = _usable_markdown_from_artifact(saved)
        sql_chunks = chunk_repo.list_for_artifact(file_id)
        if not markdown or not sql_chunks:
            detail = (
                "parse_status=ok but no usable markdown"
                if not markdown
                else "parse_status=ok but no SQL chunks"
            )
            artifact_repo.save_parse_result(file_id, parse_status="error", parse_error=detail)
            raise RuntimeError(detail)
        if _memory_chunk_store_enabled():
            _store_chunks(
                project_id,
                [
                    {
                        "chunk_id": row.id,
                        "file_id": file_id,
                        "filename": filename,
                        "thread_id": project_id,
                        "header": "",
                        "chunk_index": int(row.ordinal or 0),
                        "text": row.text or "",
                    }
                    for row in sql_chunks
                ],
            )
        log.info(
            "parse_one ok via parse_and_store file_id={} file={} chunks={}",
            file_id,
            filename,
            len(sql_chunks),
        )
        return {
            "file_results": [
                {
                    "file_id": file_id,
                    "filename": filename,
                    "status": "chunked",
                    "chunk_count": len(sql_chunks),
                    "error": "",
                }
            ]
        }
    except Exception as exc:
        log.warning("parse_one failed file_id={} file={} detail={}", file_id, filename, exc)
        try:
            artifact_repo.save_parse_result(file_id, parse_status="error", parse_error=str(exc))
        except Exception:
            log.exception("parse_one could not store failure file_id={}", file_id)
        return {
            "file_results": [
                {"file_id": file_id, "filename": filename, "status": "failed", "error": str(exc)}
            ]
        }


async def chunk_one(state: dict[str, Any]) -> dict[str, Any]:
    """No-op when parse_and_store already wrote SQL chunks."""
    results = list(state.get("file_results") or [])
    if not results:
        return {}
    latest = results[-1]
    if latest.get("status") not in {"parsed", "chunked"}:
        return {}
    file_id = str(latest.get("file_id") or "")
    count = len(chunk_repo.list_for_artifact(file_id)) if file_id else 0
    log.info("chunk_one sql file_id={} chunks={}", file_id, count)
    return {
        "file_results": [
            {
                "file_id": file_id,
                "filename": latest.get("filename"),
                "status": "chunked",
                "chunk_count": count,
            }
        ]
    }


def join_docs(state: dict[str, Any]) -> dict[str, Any]:
    results = list(state.get("file_results") or [])
    failed = [item for item in results if item.get("status") == "failed"]
    log.info("join_docs files={} failed={}", len(results), len(failed))
    return {"procurement": {"index_ready": False, "ingest_failed": len(failed)}}


def index_docs(state: dict[str, Any]) -> dict[str, Any]:
    project_id = str(state.get("project_id") or "").strip()
    count = _sql_chunk_count(project_id)
    log.info("index_docs project_id={} sql_chunks={}", project_id, count)
    return {"procurement": {"index_ready": True, "chunk_count": count}}

_SEARCH_STOP = frozenset({
    "a", "an", "the", "and", "or", "of", "to", "for", "in", "on", "at", "by",
    "with", "from", "this", "that", "these", "those", "it", "its", "is", "are",
    "was", "be", "do", "does", "did", "can", "you", "me", "we", "please",
    "what", "why", "how", "about", "tell", "show", "explain", "again",
    "project", "file", "files", "document", "documents",
})


def _search_terms(query: str) -> list[str]:
    words = []
    for raw in (query or "").lower().replace("/", " ").split():
        word = "".join(ch for ch in raw if ch.isalnum())
        if len(word) < 3 or word in _SEARCH_STOP:
            continue
        if word not in words:
            words.append(word)
    return words


def _card(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "chunk_id": row.get("chunk_id"),
        "file_id": row.get("file_id"),
        "filename": row.get("filename"),
        "header": row.get("header"),
        "text": row.get("text"),
    }


def _sql_chunk_count(project_id: str) -> int:
    if not project_id:
        return 0
    with session_scope() as session:
        return int(
            session.scalar(
                select(func.count()).select_from(Chunk).where(Chunk.project_id == project_id)
            )
            or 0
        )


def _sql_chunk_rows(project_id: str, file_id: str | None = None) -> list[dict[str, Any]]:
    with session_scope() as session:
        stmt = (
            select(Chunk, Artifact.original_name)
            .join(Artifact, Artifact.id == Chunk.artifact_id)
            .where(Chunk.project_id == project_id)
            .order_by(Chunk.artifact_id, Chunk.ordinal)
        )
        if file_id:
            stmt = stmt.where(Chunk.artifact_id == file_id)
        out: list[dict[str, Any]] = []
        for chunk, original_name in session.execute(stmt).all():
            heading = ""
            try:
                path = json.loads(chunk.heading_path_json or "[]")
                if isinstance(path, list):
                    heading = " / ".join(str(p) for p in path if p)
            except Exception:
                heading = ""
            out.append(
                {
                    "chunk_id": chunk.id,
                    "file_id": chunk.artifact_id,
                    "filename": original_name or "",
                    "header": heading,
                    "chunk_index": int(chunk.ordinal or 0),
                    "text": chunk.text or "",
                    "thread_id": project_id,
                }
            )
        return out


def search_docs(project_id: str, query: str, file_id: str | None = None, limit: int = 6) -> list[dict[str, Any]]:
    rows = _sql_chunk_rows(project_id, file_id=file_id)
    if not rows and _memory_chunk_store_enabled():
        rows = list(_CHUNK_STORE.get(project_id) or [])
        if file_id:
            rows = [row for row in rows if row.get("file_id") == file_id]
    terms = _search_terms(query)
    if not terms:
        return [_card(row) for row in rows[:limit]]
    scored: list[tuple[int, dict[str, Any]]] = []
    for row in rows:
        hay = f"{row.get('header') or ''} {row.get('text') or ''}".lower()
        hits = sum(1 for term in terms if term in hay)
        if hits:
            scored.append((hits, row))
    scored.sort(key=lambda item: item[0], reverse=True)
    picked = [row for _, row in scored[:limit]]
    return [_card(row) for row in picked]


def _usable_markdown_from_artifact(artifact: Artifact) -> str:
    raw = getattr(artifact, "parsed_json", None) or ""
    if not raw:
        return ""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return ""
    if not isinstance(data, dict):
        return ""
    markdown = data.get("markdown")
    return markdown.strip() if isinstance(markdown, str) else ""


def _store_chunks(project_id: str, chunks: list[dict[str, Any]]) -> None:
    if not _memory_chunk_store_enabled():
        return
    existing = [
        row
        for row in (_CHUNK_STORE.get(project_id) or [])
        if row.get("file_id") != (chunks[0]["file_id"] if chunks else "")
    ]
    _CHUNK_STORE[project_id] = existing + chunks


def _bound_project_id(project_id: str | None = None) -> str:
    pid = (project_id or "").strip()
    if pid:
        return pid
    try:
        from ai_brain.core.kb.store.search import current_project_id

        return current_project_id()
    except Exception:
        return ""


def list_project_files(project_id: str | None = None) -> list[dict[str, Any]]:
    pid = _bound_project_id(project_id)
    if not pid:
        return []
    with session_scope() as session:
        rows = session.scalars(
            select(Artifact).where(Artifact.project_id == pid).order_by(Artifact.created_at.asc())
        ).all()
        return [
            {
                "file_id": row.id,
                "filename": row.original_name,
                "status": row.parse_status or "pending",
            }
            for row in rows
        ]


def read_indexed_chunk(chunk_id: str, project_id: str | None = None) -> dict[str, Any] | None:
    pid = _bound_project_id(project_id)
    if pid:
        for row in _sql_chunk_rows(pid):
            if row.get("chunk_id") == chunk_id:
                return row
    if _memory_chunk_store_enabled():
        if pid:
            for row in _CHUNK_STORE.get(pid) or []:
                if row.get("chunk_id") == chunk_id:
                    return row
        for rows in _CHUNK_STORE.values():
            for row in rows:
                if row.get("chunk_id") == chunk_id:
                    return row
    with session_scope() as session:
        chunk = session.get(Chunk, chunk_id)
        if chunk is None:
            return None
        art = session.get(Artifact, chunk.artifact_id)
        return {
            "chunk_id": chunk.id,
            "file_id": chunk.artifact_id,
            "filename": (art.original_name if art else "") or "",
            "header": "",
            "text": chunk.text or "",
            "chunk_index": int(chunk.ordinal or 0),
            "thread_id": chunk.project_id,
        }


def chat_list_files() -> str:
    """List uploaded files for this project. Returns filename, file_id, and parse status. No file bodies."""
    rows = list_project_files()
    if not rows:
        return "(no files)"
    return json.dumps(rows, ensure_ascii=False)


def chat_search_docs(query: str, file_id: str = "") -> str:
    """Search indexed chunks for this project. Optional file_id limits to one file. Cite filename and header. Do not invent quotes."""
    pid = _bound_project_id(None)
    if not pid:
        return "(no project_id)"
    hits = search_docs(pid, query, file_id or None)
    if not hits:
        return "no hits"
    return json.dumps(hits, ensure_ascii=False)


def chat_read_chunk(chunk_id: str) -> str:
    """Read one indexed chunk by chunk_id from search_docs. Returns that chunk only."""
    row = read_indexed_chunk(chunk_id)
    if not row:
        return "(missing chunk)"
    return json.dumps(
        {
            "chunk_id": row.get("chunk_id"),
            "filename": row.get("filename"),
            "header": row.get("header"),
            "text": row.get("text"),
        },
        ensure_ascii=False,
    )


chat_list_files.__name__ = "list_files"
chat_search_docs.__name__ = "search_docs"
chat_read_chunk.__name__ = "read_chunk"


def ingest_chat_tools() -> list[Any]:
    """Chat tools over SQL chunks. Azure Document Intelligence is not a tool."""
    return [chat_list_files, chat_search_docs, chat_read_chunk]
