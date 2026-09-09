"""Harness coverage: which bid chunks the researcher actually read."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Iterator

from langchain.agents.middleware import AgentMiddleware

_state: ContextVar["CoverageState | None"] = ContextVar("kb_chunk_coverage", default=None)


@dataclass
class CoverageState:
    required: set[str] = field(default_factory=set)
    read: set[str] = field(default_factory=set)
    paths: set[str] = field(default_factory=set)
    chunk_paths: dict[str, str] = field(default_factory=dict)

    def unread(self) -> list[str]:
        return sorted(self.required - self.read)


def current_coverage() -> CoverageState | None:
    return _state.get()


@contextmanager
def coverage_scope(state: CoverageState) -> Iterator[CoverageState]:
    token = _state.set(state)
    try:
        yield state
    finally:
        _state.reset(token)


def record_chunk_ids(chunk_ids: list[str] | str | None) -> None:
    state = _state.get()
    if state is None:
        return
    for cid in _as_ids(chunk_ids):
        if cid:
            state.read.add(cid)


def record_path(path: str | None) -> None:
    state = _state.get()
    if state is None or not path:
        return
    key = path if str(path).startswith("/") else f"/{path}"
    state.paths.add(key)
    for chunk_id, mapped in state.chunk_paths.items():
        if mapped == key or key.endswith(mapped) or mapped.endswith(key):
            state.read.add(chunk_id)


def _as_ids(raw: list[str] | str | None) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        if "," in text:
            return [part.strip() for part in text.split(",") if part.strip()]
        return [text]
    return [str(item).strip() for item in raw if str(item).strip()]


def _tool_name(request: Any) -> str:
    call = getattr(request, "tool_call", None) or {}
    if isinstance(call, dict):
        return str(call.get("name") or "")
    return str(getattr(call, "name", "") or "")


def _tool_args(request: Any) -> dict[str, Any]:
    call = getattr(request, "tool_call", None) or {}
    if isinstance(call, dict):
        args = call.get("args") or {}
        return args if isinstance(args, dict) else {}
    args = getattr(call, "args", None)
    return args if isinstance(args, dict) else {}


def record_tool_request(request: Any) -> None:
    name = _tool_name(request)
    args = _tool_args(request)
    if name == "read_chunk":
        record_chunk_ids(args.get("chunk_id") or args.get("chunkId"))
    elif name == "read_chunks":
        record_chunk_ids(args.get("chunk_ids") or args.get("chunkIds") or args.get("chunk_id"))
    elif name == "read_chunk_window":
        record_chunk_ids(args.get("chunk_ids") or args.get("chunkIds"))
    elif name in {"read_file", "read_project_file"}:
        record_path(args.get("path") or args.get("file_path") or args.get("filePath"))


class CoverageMiddleware(AgentMiddleware):
    """Record chunk_id / path reads. Harness source of truth, not the model."""

    def wrap_tool_call(self, request, handler):
        result = handler(request)
        record_tool_request(request)
        return result

    async def awrap_tool_call(self, request, handler):
        result = await handler(request)
        record_tool_request(request)
        return result
