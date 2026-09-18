"""LangChain MCP tools for the vendor analyst.

Read/search go through MCP tools adapted for ``create_agent``. Prefer
``langchain.mcp.MCPAdapter`` (in-process FastMCP). Fall back to
``langchain-mcp-adapters`` then plain Python callables. SQL writes stay in
``persist.py`` after structured output so the model cannot skip the grounding
gate.

https://docs.langchain.com/oss/python/langchain/mcp
https://docs.langchain.com/langsmith/server-mcp#python
https://docs.langchain.com/oss/python/migrate/langchain-mcp-adapters
"""

from __future__ import annotations

import json
import os
import warnings
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from sqlalchemy import text

from ai_brain.core.kb.build.coverage import record_chunk_ids, record_path
from ai_brain.core.kb.store.materialize import project_files
from ai_brain.core.kb.api.schemas import load_chunk_text
from ai_brain.core.kb.store.search import search_kb as _search_kb
from shared.db.connection import mate_table_name, session_scope
from shared.logger_global import get_logger

log = get_logger(__name__, service="ai_brain")

READ_CHUNKS_CHAR_CAP = 24_000
CHUNK_FILE_CHARS = 12_000
READ_CHUNK_WINDOW_DEFAULT = 8


def _current_project_id() -> str:
    try:
        from ai_brain.core.kb.store.search import current_project_id

        return current_project_id()
    except Exception:  # noqa: BLE001
        return ""


def search_project_kb(
    query: str,
    vendor: str | None = None,
    doc_role: str | None = None,
    chunk_type: str | None = None,
    k: int = 8,
    project_id: str | None = None,
) -> str:
    """Search this project's knowledge base (parsed chunks + graph expand).

    Use to answer questions about vendors, pricing, requirements, or RFP text.
    Cite file + page from the returned headers. Pass vendor / doc_role
    (rfp|proposal|pricing|registry|csr) to narrow.
    """
    try:
        return _search_kb(
            query,
            vendor=vendor,
            doc_role=doc_role,
            chunk_type=chunk_type,
            k=k,
            project_id=project_id,
        )
    except Exception as exc:  # noqa: BLE001
        return f"search_kb unavailable: {exc}"


def list_bids(project_id: str | None = None) -> str:
    """List classified bid ids (artifact.vendor_id) for this project. Never guess from filenames."""
    from ai_brain.core.kb.store.materialize import list_bid_ids

    pid = (project_id or "").strip() or _current_project_id()
    if not pid:
        return "(no project_id)"
    bids = list(list_bid_ids(pid))
    if not bids:
        return "(no bids)"
    return json.dumps(bids, ensure_ascii=False)


def list_project_paths(project_id: str | None = None) -> str:
    """List virtual /project paths materialized for this kb_build run."""
    pid = (project_id or "").strip() or _current_project_id()
    if not pid:
        return "(no project_id)"
    files = project_files(pid)
    if not files:
        return "(no materialized files)"
    return "\n".join(sorted(files))


def read_chunk(chunk_id: str) -> str:
    """Return stored chunk text by id, or empty if missing."""
    record_chunk_ids(chunk_id)
    return load_chunk_text(chunk_id) or ""


def read_chunks(chunk_ids: list[str] | str, project_id: str | None = None) -> str:
    """Read several chunks. Stops around 24k chars so the model pages through the rest."""
    del project_id
    ids = _as_id_list(chunk_ids)
    if not ids:
        return "(no chunk_ids)"
    parts: list[str] = []
    used = 0
    unread: list[str] = []
    for index, cid in enumerate(ids):
        body = load_chunk_text(cid) or ""
        block = f"[{cid}]\n{body}\n"
        if used and used + len(block) > READ_CHUNKS_CHAR_CAP:
            unread = ids[index:]
            break
        parts.append(block)
        used += len(block)
        record_chunk_ids(cid)
    if unread:
        parts.append("... truncated; remaining unread: " + ", ".join(unread))
    return "\n".join(parts).strip()


def read_chunk_window(
    bid_id: str,
    offset: int = 0,
    limit: int = READ_CHUNK_WINDOW_DEFAULT,
    project_id: str | None = None,
) -> str:
    """Page this bid's chunks by offset. Prefer /_chunks files; use this to re-open a window."""
    rows = list_bid_chunk_rows(project_id, bid_id)
    start = max(0, int(offset or 0))
    take = max(1, min(int(limit or READ_CHUNK_WINDOW_DEFAULT), 20))
    window = rows[start : start + take]
    if not window:
        return "(no chunks)"
    parts: list[str] = []
    for row in window:
        cid = str(row["chunk_id"])
        body = load_chunk_text(cid) or ""
        record_chunk_ids(cid)
        header = f"[{cid}] {row.get('original_name') or ''} {row.get('locator') or ''}".strip()
        parts.append(f"{header}\n{body}")
    nxt = start + len(window)
    if nxt < len(rows):
        parts.append(f"... next offset={nxt} remaining={len(rows) - nxt}")
    return "\n\n".join(parts)


def prefetch_bid_chunks(project_id: str, bid_id: str) -> tuple[dict[str, str], list[str]]:
    """Pack parsed chunks into virtual /_chunks/*.md files (no LLM)."""
    from ai_brain.core.procurement_ai.project_context import load_project

    rows = list_bid_chunk_rows(project_id, bid_id)
    project = load_project(project_id)
    code = project.code if project is not None else "project"
    prefix = f"/project/{code}/vendors/{bid_id}/_chunks"
    files: dict[str, str] = {}
    packed: list[str] = []
    batch: list[str] = []
    used = 0
    index = 0

    def flush() -> None:
        nonlocal batch, used, index
        if not batch:
            return
        files[f"{prefix}/{index:03d}.md"] = "\n\n".join(batch)
        index += 1
        batch = []
        used = 0

    for row in rows:
        cid = str(row["chunk_id"])
        body = load_chunk_text(cid) or ""
        block = (
            f"## `{cid}`\n"
            f"artifact: {row.get('original_name') or ''}\n"
            f"locator: {row.get('locator') or ''}\n"
            f"heading: {row.get('heading') or ''}\n\n"
            f"{body}"
        )
        if batch and used + len(block) > CHUNK_FILE_CHARS:
            flush()
        batch.append(block)
        used += len(block)
        packed.append(cid)
    flush()
    return files, packed


def list_bid_chunks(bid_id: str, project_id: str | None = None) -> str:
    """Complete chunk manifest for one bid (not top-k). Includes RFP only if bid_id is rfp."""
    rows = list_bid_chunk_rows(project_id, bid_id)
    if not rows:
        return "(no chunks)"
    lines = [
        "chunk_id\tartifact\tordinal\tlocator\ttokens\theading",
    ]
    for row in rows:
        heading = (row.get("heading") or "").replace("\t", " ")[:80]
        lines.append(
            f"{row['chunk_id']}\t{row.get('original_name') or ''}\t"
            f"{row.get('ordinal')}\t{row.get('locator') or ''}\t"
            f"{row.get('token_count') or 0}\t{heading}"
        )
    return "\n".join(lines)


def list_bid_chunk_ids(project_id: str, bid_id: str) -> list[str]:
    return [row["chunk_id"] for row in list_bid_chunk_rows(project_id, bid_id)]


def list_bid_chunk_rows(project_id: str | None, bid_id: str) -> list[dict[str, Any]]:
    pid = (project_id or "").strip() or _current_project_id()
    bid = (bid_id or "").strip()
    if not pid or not bid:
        return []
    from ai_brain.core.kb.store.search import _heading_from_json, _locator_from_location

    chunk = mate_table_name("chunk")
    artifact = mate_table_name("artifact")
    # bid_id=rfp is a virtual bid for RFP corpus (doc_role), not artifact.vendor_id.
    if bid.lower() == "rfp":
        sql = f"""
            SELECT c.id AS chunk_id, c.artifact_id, c.ordinal, c.token_count,
                   c.heading_path_json, c.location_json, a.original_name, a.vendor_id
              FROM {chunk} c
              JOIN {artifact} a ON a.id = c.artifact_id
             WHERE c.project_id = :pid AND lower(coalesce(a.doc_role, '')) = 'rfp'
             ORDER BY a.original_name, c.ordinal
        """
        params = {"pid": pid}
    else:
        sql = f"""
            SELECT c.id AS chunk_id, c.artifact_id, c.ordinal, c.token_count,
                   c.heading_path_json, c.location_json, a.original_name, a.vendor_id
              FROM {chunk} c
              JOIN {artifact} a ON a.id = c.artifact_id
             WHERE c.project_id = :pid AND a.vendor_id = :bid
             ORDER BY a.original_name, c.ordinal
        """
        params = {"pid": pid, "bid": bid}
    with session_scope() as session:
        rows = session.execute(text(sql), params).mappings().all()
    out: list[dict[str, Any]] = []
    for row in rows:
        locator = _locator_from_location(row["location_json"])
        out.append(
            {
                "chunk_id": row["chunk_id"],
                "artifact_id": row["artifact_id"],
                "original_name": row["original_name"] or "",
                "ordinal": int(row["ordinal"] or 0),
                "token_count": int(row["token_count"] or 0),
                "locator": locator,
                "heading": _heading_from_json(row["heading_path_json"]),
                "path": _virtual_path(pid, bid, row["original_name"] or ""),
            }
        )
    return out


def chunk_manifest_block(project_id: str, bid_id: str) -> str:
    rows = list_bid_chunk_rows(project_id, bid_id)
    if not rows:
        return "Chunk index: (none)"
    lines = [
        f"Chunk index ({len(rows)} chunks) is packed under "
        f"/project/*/vendors/{bid_id}/_chunks/. Use ls/grep/read_file on those files. "
        "MCP search_project_kb / read_chunk / read_chunks / read_chunk_window only to re-open a cited id."
    ]
    for row in rows:
        lines.append(
            f"- `{row['chunk_id']}` {row.get('original_name')} {row.get('locator') or ''} "
            f"ord={row.get('ordinal')} tokens={row.get('token_count')}"
        )
    return "\n".join(lines)


def read_project_file(path: str, project_id: str | None = None) -> str:
    """Read one materialized /project path (markdown) for this kb_build."""
    pid = (project_id or "").strip() or _current_project_id()
    if not pid:
        return "(no project_id)"
    files = project_files(pid)
    key = path if path.startswith("/") else f"/{path}"
    record_path(key)
    if key in files:
        return files[key]
    matches = [p for p in files if p.endswith(path) or path in p]
    if len(matches) == 1:
        record_path(matches[0])
        return files[matches[0]]
    if matches:
        return "(ambiguous path; pick one)\n" + "\n".join(matches)
    return f"(missing path {path})"


def langchain_kb_tools() -> list[Any]:
    """Sync Python callables for tests and MCP-unavailable fallback."""
    return [
        search_project_kb,
        list_bids,
        list_project_paths,
        list_bid_chunks,
        read_chunk,
        read_chunks,
        read_chunk_window,
        read_project_file,
    ]


def kb_fastmcp_server() -> Any:
    """In-process FastMCP server exposing the KB read tools."""
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("procurement-kb")
    server.add_tool(search_project_kb)
    server.add_tool(list_bids)
    server.add_tool(list_project_paths)
    server.add_tool(list_bid_chunks)
    server.add_tool(read_chunk)
    server.add_tool(read_chunks)
    server.add_tool(read_chunk_window)
    server.add_tool(read_project_file)
    return server


async def _with_optional_remote(tools: list[Any]) -> list[Any]:
    url = (os.getenv("KB_MCP_URL") or "").strip()
    if url:
        tools.extend(await _remote_mcp_tools(url))
    return tools


@asynccontextmanager
async def mcp_kb_tools_context() -> AsyncIterator[list[Any]]:
    """Yield LangChain tools from the in-process KB MCP server.

    Prefer ``MCPAdapter`` (LangChain MCP docs). Fall back to
    ``langchain-mcp-adapters`` then Python callables. Keep the session open
    for the life of this context so tool calls can round-trip.
    """
    adapter_cls = _mcp_adapter_class()
    if adapter_cls is not None:
        try:
            async with adapter_cls(kb_fastmcp_server()) as adapter:
                tools = await _with_optional_remote(list(await adapter.list_tools()))
                yield tools
                return
        except Exception:
            log.exception("langchain.mcp MCPAdapter KB tools failed")

    try:
        from langchain_mcp_adapters.tools import load_mcp_tools
        from mcp.shared.memory import create_connected_server_and_client_session
    except ImportError:
        log.warning("langchain-mcp-adapters not installed; using Python KB callables")
        yield langchain_kb_tools()
        return
    try:
        async with create_connected_server_and_client_session(
            kb_fastmcp_server(),
            raise_exceptions=True,
        ) as session:
            tools = await _with_optional_remote(list(await load_mcp_tools(session)))
            yield tools
            return
    except Exception:
        log.exception("in-process MCP KB tools failed")
    yield langchain_kb_tools()


def _mcp_adapter_class() -> Any | None:
    try:
        from langchain_core._api import LangChainBetaWarning

        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=LangChainBetaWarning)
            from langchain.mcp import MCPAdapter

        return MCPAdapter
    except ImportError:
        return None


async def _remote_mcp_tools(url: str) -> list[Any]:
    """Optional extra catalog from KB_MCP_URL (streamable HTTP)."""
    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
    except ImportError:
        return []
    try:
        client = MultiServerMCPClient({"kb": {"transport": "streamable_http", "url": url}})
        return list(await client.get_tools())
    except Exception:
        log.exception("remote MCP tools failed url={}", url)
        return []


async def load_mcp_tools() -> list[Any]:
    """Discover tools from the in-process KB server and optional KB_MCP_URL."""
    async with mcp_kb_tools_context() as tools:
        return list(tools)


def _as_id_list(raw: list[str] | str | None) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
        return [part.strip() for part in text.split(",") if part.strip()]
    return [str(item).strip() for item in raw if str(item).strip()]


def _virtual_path(project_id: str, bid_id: str, original_name: str) -> str:
    from ai_brain.core.procurement_ai.project_context import load_project

    project = load_project(project_id)
    code = project.code if project is not None else "project"
    slug = Path(original_name or "document").stem
    safe = "".join(ch if ch.isalnum() else "-" for ch in slug).strip("-").lower() or "document"
    return f"/project/{code}/vendors/{bid_id}/{safe}.md"
