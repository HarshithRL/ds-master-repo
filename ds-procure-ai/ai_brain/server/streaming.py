"""Map LangGraph astream v2 chunks to ResponsesAgentStreamEvent."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import mlflow
from langgraph.types import Command
from mlflow.entities import SpanType
from mlflow.types.responses import (
    ResponsesAgentStreamEvent,
    create_text_delta,
    create_text_output_item,
)

from ai_brain.core.utils.content import split_message_kinds
from ai_brain.server.tracing import bind_run_trace


def _as_v2(chunk: Any) -> tuple[str, tuple, Any] | None:
    if isinstance(chunk, dict) and "type" in chunk:
        return str(chunk.get("type") or ""), tuple(chunk.get("ns") or ()), chunk.get("data")
    if isinstance(chunk, tuple) and len(chunk) == 3:
        mode, ns, data = chunk
        return str(mode), tuple(ns or ()), data
    if isinstance(chunk, tuple) and len(chunk) == 2:
        first, second = chunk
        if isinstance(first, str):
            return first, (), second
        return "messages", tuple(first or ()), second
    return None



_TOOL_ROLES = frozenset({"tool", "toolmessage"})
_MISS = "I could not find that in the uploaded files."
_TOOL_LEAKS = (
    "(no matching chunks)",
    "(no hits)",
    "(no files)",
    "(no project_id)",
    "(missing chunk)",
)
# User-facing chat nodes. Nested comparison/deep-agent loops are thoughts only.
_ANSWER_NODES = frozenset({"main_agent", "deepagent"})
_THOUGHT_NODES = frozenset(
    {
        "compare_xlsx",
        "steerco_ppt",
        "comparison_orchestrator",
        "comparison_emit",
        "rfp_analyst",
        "vendor_analyst",
        "bafo_compiler",
        "extract_requirements",
        "analyze_bid",
        "audit_kb",
        "fill_overview",
        "fill_requirements",
        "fill_vendors",
        "ingest",
        "parse_one",
        "chunk_one",
        "join_docs",
        "index_docs",
    }
)


def _message_role(msg: Any) -> str:
    if isinstance(msg, dict):
        return str(msg.get("type") or msg.get("role") or "").lower()
    return str(getattr(msg, "type", None) or getattr(msg, "role", None) or "").lower()


def _tool_name(msg: Any) -> str:
    if isinstance(msg, dict):
        return str(msg.get("name") or msg.get("tool") or "tool")
    return str(getattr(msg, "name", None) or "tool")


def _is_tool_message(msg: Any) -> bool:
    if getattr(msg, "tool_call_id", None):
        return True
    if isinstance(msg, dict) and msg.get("tool_call_id"):
        return True
    return _message_role(msg) in _TOOL_ROLES


def _has_tool_calls(msg: Any) -> bool:
    calls = None
    if isinstance(msg, dict):
        calls = msg.get("tool_calls") or msg.get("tool_call_chunks")
    else:
        calls = getattr(msg, "tool_calls", None) or getattr(msg, "tool_call_chunks", None)
    return bool(calls)


def _answer_text(text: str) -> str:
    """Keep token whitespace. Strip only a finished tool leak, not each delta."""
    if text is None:
        return ""
    value = str(text)
    stripped = value.strip()
    if not stripped:
        return value
    if any(leak in stripped for leak in _TOOL_LEAKS):
        return ""
    if stripped.startswith("/project/") or stripped.startswith("[{"):
        return ""
    return value


def _message_payload(data: Any) -> tuple[Any, dict[str, Any]]:
    if isinstance(data, tuple) and len(data) == 2:
        meta = data[1] if isinstance(data[1], dict) else {}
        return data[0], meta
    return data, {}


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        try:
            return dump()
        except Exception:
            return str(value)
    return str(value)


def _interrupts_from_state(state: Any) -> list[Any]:
    interrupts: list[Any] = []
    tasks = getattr(state, "tasks", None) or ()
    for task in tasks:
        for item in getattr(task, "interrupts", None) or ():
            interrupts.append(_jsonable(item))
    values = getattr(state, "values", None) or {}
    if isinstance(values, dict) and values.get("__interrupt__"):
        interrupts.append(_jsonable(values["__interrupt__"]))
    return interrupts



def _ingest_progress(node: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    """File status only. Never file bodies."""
    events: list[dict[str, Any]] = []
    results = payload.get("file_results")
    if isinstance(results, list):
        for item in results:
            if not isinstance(item, dict):
                continue
            events.append(
                {
                    "kind": "file_progress",
                    "node": node,
                    "file_id": item.get("file_id") or "",
                    "filename": item.get("filename") or "",
                    "status": item.get("status") or "",
                    "chunk_count": item.get("chunk_count") or 0,
                    "error": item.get("error") or "",
                }
            )
    procurement = payload.get("procurement")
    if node == "index_docs" and isinstance(procurement, dict) and procurement.get("index_ready"):
        events.append(
            {
                "kind": "index_ready",
                "node": node,
                "chunk_count": procurement.get("chunk_count") or 0,
                "index_ready": True,
            }
        )
    return events


def _node_from_updates(data: Any) -> str | None:
    if not isinstance(data, dict) or not data:
        return None
    return next(iter(data.keys()), None)


def _item_key(ns: tuple, node: str) -> str:
    suffix = ":".join(str(p) for p in ns) if ns else "root"
    return f"{suffix}:{node}"


def _ns_is_nested(ns: tuple) -> bool:
    """True when chunk comes from child_runnable_config(checkpoint_ns='nested')."""
    return any("nested" in str(part).lower() for part in (ns or ()))


def _route_message_as_thought(ns: tuple, node: str) -> bool:
    """Deep-agent / pack-tool chatter → Thinking tab; main_agent stays chat answer."""
    name = (node or "").strip()
    if name in _ANSWER_NODES:
        return False
    if name in _THOUGHT_NODES:
        return True
    if _ns_is_nested(ns):
        return True
    return False


def _procurement_dict(values: Any) -> dict[str, Any]:
    if not isinstance(values, dict):
        return {}
    proc = values.get("procurement")
    return proc if isinstance(proc, dict) else {}


def _business_reply(proc: dict[str, Any]) -> str:
    """Prefer pack/compare assistant_reply (includes Download href) over raw essays."""
    reply = str(proc.get("assistant_reply") or "").strip()
    if reply:
        href = str(proc.get("xlsx_href") or proc.get("ppt_href") or "").strip()
        if href and href not in reply:
            return f"{reply.rstrip()} Download: {href}"
        return reply
    return ""


def _procurement_text(payload_out: dict[str, Any]) -> str:
    proc = payload_out.get("procurement")
    if isinstance(proc, dict):
        return str(proc.get("main_agent") or proc.get("deep_agent") or "")
    return ""


async def iter_response_events(
    graph: Any,
    *,
    payload: dict[str, Any] | Command,
    config: dict[str, Any],
    request_text: str,
    procurement: dict[str, Any],
    thread_id: str,
    user_id: str = "anonymous",
) -> AsyncIterator[ResponsesAgentStreamEvent]:
    item_ids: dict[str, str] = {}
    assembled: dict[str, str] = {}
    done_ids: set[str] = set()
    last_values: dict[str, Any] = {}
    thought_nodes: set[str] = set()
    # Pack capabilities: stream all LLM chatter to Thinking; final bubble = assistant_reply.
    pack_mode = str((procurement or {}).get("capability") or "").strip() in {
        "compare_xlsx",
        "steerco_ppt",
        "kb_build",
    }

    with mlflow.start_span(name="nexus_graph", span_type=SpanType.AGENT) as span:
        bind_run_trace(thread_id=thread_id, user_id=user_id)
        span.set_inputs(
            {
                "request": request_text,
                "procurement": procurement,
                "thread_id": thread_id,
            }
        )
        try:
            stream = graph.astream(
                payload,
                config=config,
                stream_mode=["messages", "updates"],
                subgraphs=True,
                version="v2",
            )
            async for chunk in stream:
                parsed = _as_v2(chunk)
                if parsed is None:
                    continue
                mode, ns, data = parsed

                if mode == "updates":
                    node = _node_from_updates(data) or "unknown"
                    if not isinstance(data, dict):
                        continue
                    payload_out = data.get(node) if node in data else None
                    if not isinstance(payload_out, dict):
                        continue
                    last_values = payload_out
                    thought_key = _item_key(ns, f"{node}:thought")
                    if thought_key not in thought_nodes:
                        thought_nodes.add(thought_key)
                        thought_id = item_ids.setdefault(
                            thought_key, f"thought_{uuid.uuid4().hex[:12]}"
                        )
                        yield ResponsesAgentStreamEvent(
                            **create_text_delta(delta="", item_id=thought_id),
                            custom_outputs={
                                "kind": "thought",
                                "node": node,
                                "ns": list(ns),
                            },
                        )
                    for extra in _ingest_progress(node, payload_out):
                        extra_id = item_ids.setdefault(
                            _item_key(ns, f"{node}:{extra.get('kind')}:{extra.get('file_id') or 'index'}"),
                            f"prog_{uuid.uuid4().hex[:12]}",
                        )
                        yield ResponsesAgentStreamEvent(
                            **create_text_delta(delta="", item_id=extra_id),
                            custom_outputs=extra,
                        )
                    continue

                if mode != "messages":
                    continue

                msg, meta = _message_payload(data)
                node = str(meta.get("langgraph_node") or "model")
                if _is_tool_message(msg) or _has_tool_calls(msg):
                    yield ResponsesAgentStreamEvent(
                        **create_text_delta(delta="", item_id=f"tool_{uuid.uuid4().hex[:12]}"),
                        custom_outputs={
                            "kind": "tool",
                            "node": node,
                            "name": _tool_name(msg),
                            "ns": list(ns),
                        },
                    )
                    continue
                answer, thought = split_message_kinds(msg)
                answer = _answer_text(answer)
                # Nested deep-agent / pack loops: keep chatter in Thinking only.
                if answer and (pack_mode or _route_message_as_thought(ns, node)):
                    thought = f"{thought}{answer}" if thought else answer
                    answer = ""
                if thought:
                    thought_key = _item_key(ns, f"{node}:thought")
                    thought_id = item_ids.setdefault(
                        thought_key, f"thought_{uuid.uuid4().hex[:12]}"
                    )
                    yield ResponsesAgentStreamEvent(
                        **create_text_delta(delta=thought, item_id=thought_id),
                        custom_outputs={
                            "kind": "thought",
                            "node": node,
                            "ns": list(ns),
                        },
                    )
                if not answer:
                    continue
                key = _item_key(ns, node)
                item_id = item_ids.setdefault(key, f"msg_{uuid.uuid4().hex[:12]}")
                assembled[item_id] = assembled.get(item_id, "") + answer
                yield ResponsesAgentStreamEvent(
                    **create_text_delta(delta=answer, item_id=item_id),
                    custom_outputs={
                        "kind": "answer",
                        "node": node,
                        "ns": list(ns),
                    },
                )

            state = await graph.aget_state(config)
            interrupts = _interrupts_from_state(state)
            values = getattr(state, "values", None) or last_values
            if isinstance(values, dict) and values:
                last_values = values
            span.set_outputs(
                {
                    "route": last_values.get("route") if isinstance(last_values, dict) else "",
                    "procurement": (
                        last_values.get("procurement")
                        if isinstance(last_values, dict)
                        else {}
                    ),
                    "interrupted": bool(interrupts),
                    "interrupts": interrupts,
                }
            )

            if interrupts:
                yield ResponsesAgentStreamEvent(
                    type="response.output_item.done",
                    item=create_text_output_item(
                        text="Interrupted — resume with Command to continue.",
                        id=f"interrupt_{uuid.uuid4().hex[:12]}",
                    ),
                    custom_outputs={
                        "interrupted": True,
                        "interrupts": interrupts,
                        "thread_id": thread_id,
                        "values": _jsonable(last_values),
                    },
                )
                return

            proc = _procurement_dict(last_values)
            business = _business_reply(proc)
            if business:
                # Pack/compare path: never let orchestrator essays win the chat bubble.
                item_id = f"msg_{uuid.uuid4().hex[:12]}"
                done_ids.add(item_id)
                custom_out: dict[str, Any] = {
                    "kind": "answer",
                    "thread_id": thread_id,
                    "final": True,
                    "values": _jsonable(last_values),
                }
                href = str(proc.get("xlsx_href") or proc.get("ppt_href") or "").strip()
                if href:
                    custom_out["xlsx_href" if proc.get("xlsx_href") else "ppt_href"] = href
                yield ResponsesAgentStreamEvent(
                    type="response.output_item.done",
                    item=create_text_output_item(text=business, id=item_id),
                    custom_outputs=custom_out,
                )
                return

            for item_id, text in assembled.items():
                if item_id in done_ids:
                    continue
                clean = _answer_text(text).strip()
                if not clean:
                    continue
                done_ids.add(item_id)
                yield ResponsesAgentStreamEvent(
                    type="response.output_item.done",
                    item=create_text_output_item(text=clean, id=item_id),
                    custom_outputs={
                        "kind": "answer",
                        "thread_id": thread_id,
                        "final": True,
                    },
                )

            if not done_ids:
                fallback = ""
                if proc:
                    fallback = str(
                        proc.get("main_agent")
                        or proc.get("deep_agent")
                        or ""
                    )
                if not fallback or not _answer_text(fallback):
                    fallback = _MISS
                yield ResponsesAgentStreamEvent(
                    type="response.output_item.done",
                    item=create_text_output_item(
                        text=fallback,
                        id=f"msg_{uuid.uuid4().hex[:12]}",
                    ),
                    custom_outputs={
                        "kind": "answer",
                        "thread_id": thread_id,
                        "values": _jsonable(last_values),
                        "final": True,
                    },
                )
        except Exception:
            span.set_status("ERROR")
            raise
