"""Graph ingest for uploaded files. Inventory in state. Markdown stays on disk."""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any

from langgraph.types import Send
from shared.db.connection import session_scope
from shared.db.models import Artifact
from shared.db.paths import artifact_absolute_path, parsed_storage_relpath
from shared.db.repos import artifacts as artifact_repo
from shared.logger_global import get_logger
from sqlalchemy import func, select

log = get_logger(__name__, service="ai_brain")

MAX_FILES = 15
DI_MODEL = "prebuilt-layout"
DI_CONCURRENCY = 5
_DI_SEM = asyncio.Semaphore(DI_CONCURRENCY)

_CHUNK_STORE: dict[str, list[dict[str, Any]]] = {}


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
    file_card = dict(task.get("file") or {})
    project_id = str(task.get("project_id") or "").strip()
    file_id = str(file_card.get("file_id") or "")
    filename = str(file_card.get("filename") or "")
    try:
        async with _DI_SEM:
            markdown = await asyncio.to_thread(_analyze_markdown, file_card)
        _write_markdown(project_id, file_id, markdown)
        artifact_repo.save_parse_result(
            file_id,
            parse_status="ok",
            parse_error=None,
            parsed_relpath=parsed_storage_relpath(project_id, file_id),
        )
        chunks = _split_markdown(markdown, file_id, filename, project_id)
        _store_chunks(project_id, chunks)
        log.info(
            "parse_one ok parser=AzureDocumentIntelligence file_id={} file={} chunks={}",
            file_id,
            filename,
            len(chunks),
        )
        return {
            "file_results": [
                {
                    "file_id": file_id,
                    "filename": filename,
                    "status": "chunked",
                    "chunk_count": len(chunks),
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
    """Chunk the latest parsed file result. Bodies stay on disk."""
    results = list(state.get("file_results") or [])
    if not results:
        return {}
    latest = results[-1]
    if latest.get("status") != "parsed":
        return {}
    project_id = str(state.get("project_id") or "").strip()
    file_id = str(latest.get("file_id") or "")
    path = _markdown_path(project_id, file_id)
    if not path.is_file():
        return {}
    chunks = _split_markdown(path.read_text(encoding="utf-8"), file_id, str(latest.get("filename") or ""), project_id)
    _store_chunks(project_id, chunks)
    log.info("chunk_one file_id={} chunks={}", file_id, len(chunks))
    return {"file_results": [{"file_id": file_id, "filename": latest.get("filename"), "status": "chunked", "chunk_count": len(chunks)}]}


def join_docs(state: dict[str, Any]) -> dict[str, Any]:
    results = list(state.get("file_results") or [])
    failed = [item for item in results if item.get("status") == "failed"]
    log.info("join_docs files={} failed={}", len(results), len(failed))
    return {"procurement": {"index_ready": False, "ingest_failed": len(failed)}}


def index_docs(state: dict[str, Any]) -> dict[str, Any]:
    project_id = str(state.get("project_id") or "").strip()
    chunks = _CHUNK_STORE.get(project_id) or []
    log.info("index_docs project_id={} chunks={}", project_id, len(chunks))
    return {"procurement": {"index_ready": True, "chunk_count": len(chunks)}}


def search_docs(project_id: str, query: str, file_id: str | None = None, limit: int = 6) -> list[dict[str, Any]]:
    needle = (query or "").strip().lower()
    rows = list(_CHUNK_STORE.get(project_id) or [])
    if file_id:
        rows = [row for row in rows if row.get("file_id") == file_id]
    if needle:
        rows = [row for row in rows if needle in (row.get("text") or "").lower() or needle in (row.get("header") or "").lower()]
    return [
        {
            "chunk_id": row.get("chunk_id"),
            "file_id": row.get("file_id"),
            "filename": row.get("filename"),
            "header": row.get("header"),
            "text": row.get("text"),
        }
        for row in rows[:limit]
    ]


def _analyze_markdown(file_card: dict[str, Any]) -> str:
    relpath = str(file_card.get("storage_relpath") or "")
    path = artifact_absolute_path(relpath)
    data = path.read_bytes()
    filename = str(file_card.get("filename") or path.name)
    endpoint = (os.getenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT") or "").strip()
    key = (os.getenv("AZURE_DOCUMENT_INTELLIGENCE_KEY") or "").strip()
    if not endpoint or not key:
        raise RuntimeError("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT and AZURE_DOCUMENT_INTELLIGENCE_KEY are required.")
    content_type = _content_type(filename)
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            return _call_di(endpoint, key, data, content_type=content_type)
        except Exception as exc:
            last_error = exc
            if "429" not in str(exc) or attempt == 2:
                raise
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(str(last_error or "Document Intelligence failed"))


def _content_type(filename: str) -> str | None:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "html": "text/html",
        "htm": "text/html",
    }.get(ext)


def _call_di(endpoint: str, key: str, data: bytes, content_type: str | None = None) -> str:
    from azure.core.credentials import AzureKeyCredential

    try:
        from azure.ai.documentintelligence import DocumentIntelligenceClient
        from azure.ai.documentintelligence.models import AnalyzeDocumentRequest, DocumentContentFormat

        client = DocumentIntelligenceClient(endpoint=endpoint, credential=AzureKeyCredential(key))
        poller = client.begin_analyze_document(
            DI_MODEL,
            AnalyzeDocumentRequest(bytes_source=data),
            output_content_format=DocumentContentFormat.MARKDOWN,
        )
        result = poller.result()
        content = getattr(result, "content", None) or ""
        if content.strip():
            return content
    except ImportError:
        log.info("documentintelligence SDK missing, using formrecognizer")
    from azure.ai.formrecognizer import DocumentAnalysisClient

    client = DocumentAnalysisClient(endpoint=endpoint, credential=AzureKeyCredential(key))
    kwargs: dict[str, Any] = {}
    if content_type:
        kwargs["content_type"] = content_type
    poller = client.begin_analyze_document(DI_MODEL, data, **kwargs)
    result = poller.result()
    return (getattr(result, "content", None) or "").strip()


def _write_markdown(project_id: str, file_id: str, markdown: str) -> None:
    rel = parsed_storage_relpath(project_id, file_id)
    json_path = artifact_absolute_path(rel)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path = json_path.with_suffix(".md")
    md_path.write_text(markdown, encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {
                "file_id": file_id,
                "parser": "AzureDocumentIntelligence",
                "model": DI_MODEL,
                "markdown_relpath": str(md_path.name),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _markdown_path(project_id: str, file_id: str):
    return artifact_absolute_path(parsed_storage_relpath(project_id, file_id)).with_suffix(".md")


def _split_markdown(markdown: str, file_id: str, filename: str, project_id: str) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    try:
        from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

        headered = MarkdownHeaderTextSplitter(headers_to_split_on=[("#", "h1"), ("##", "h2"), ("###", "h3")]).split_text(markdown)
        splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
        pieces = splitter.split_documents(headered)
        for index, doc in enumerate(pieces):
            header = " / ".join(str(v) for v in (doc.metadata or {}).values() if v)
            chunks.append(_chunk(project_id, file_id, filename, index, header, doc.page_content))
        if chunks:
            return chunks
    except Exception:
        log.info("header splitter unavailable, using plain split file_id={}", file_id)
    text = markdown.strip()
    if not text:
        return []
    step = 850
    for index, start in enumerate(range(0, len(text), step)):
        chunks.append(_chunk(project_id, file_id, filename, index, "", text[start : start + 1000]))
    return chunks


def _chunk(project_id: str, file_id: str, filename: str, index: int, header: str, text: str) -> dict[str, Any]:
    return {
        "chunk_id": f"{file_id}:{index}",
        "file_id": file_id,
        "filename": filename,
        "thread_id": project_id,
        "header": header,
        "chunk_index": index,
        "text": text,
    }


def _store_chunks(project_id: str, chunks: list[dict[str, Any]]) -> None:
    existing = [row for row in (_CHUNK_STORE.get(project_id) or []) if row.get("file_id") != (chunks[0]["file_id"] if chunks else "")]
    _CHUNK_STORE[project_id] = existing + chunks


def _bound_project_id(project_id: str | None = None) -> str:
    pid = (project_id or "").strip()
    if pid:
        return pid
    try:
        from ai_brain.core.kb.search import current_project_id

        return current_project_id()
    except Exception:
        return ""


def _ensure_chunks(project_id: str) -> None:
    """Reload markdown already written to disk if this process has no chunks."""
    if not project_id or _CHUNK_STORE.get(project_id):
        return
    with session_scope() as session:
        rows = session.scalars(
            select(Artifact)
            .where(Artifact.project_id == project_id, Artifact.parse_status == "ok")
            .order_by(Artifact.created_at.asc())
        ).all()
        cards = [_file_card(row) for row in rows]
    loaded = 0
    for card in cards:
        path = _markdown_path(project_id, str(card.get("file_id") or ""))
        if not path.is_file():
            continue
        chunks = _split_markdown(path.read_text(encoding="utf-8"), str(card["file_id"]), str(card.get("filename") or ""), project_id)
        if chunks:
            _store_chunks(project_id, chunks)
            loaded += len(chunks)
    if loaded:
        log.info("ingest chunks reloaded project_id={} chunks={}", project_id, loaded)


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
        _ensure_chunks(pid)
        for row in _CHUNK_STORE.get(pid) or []:
            if row.get("chunk_id") == chunk_id:
                return row
    if not pid:
        for rows in _CHUNK_STORE.values():
            for row in rows:
                if row.get("chunk_id") == chunk_id:
                    return row
    return None


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
    _ensure_chunks(pid)
    hits = search_docs(pid, query, file_id or None)
    if not hits:
        return "(no matching chunks)"
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
    """Chat tools over ingest chunks. Azure Document Intelligence is not a tool."""
    return [chat_list_files, chat_search_docs, chat_read_chunk]
