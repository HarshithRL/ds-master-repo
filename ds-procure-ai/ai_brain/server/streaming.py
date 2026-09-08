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
                answer, thought = split_message_kinds(msg)
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

            for item_id, text in assembled.items():
                if item_id in done_ids:
                    continue
                done_ids.add(item_id)
                yield ResponsesAgentStreamEvent(
                    type="response.output_item.done",
                    item=create_text_output_item(text=text, id=item_id),
                    custom_outputs={
                        "kind": "answer",
                        "thread_id": thread_id,
                        "final": True,
                    },
                )

            if not done_ids:
                proc = last_values.get("procurement") if isinstance(last_values, dict) else {}
                fallback = ""
                if isinstance(proc, dict):
                    fallback = str(proc.get("main_agent") or proc.get("deep_agent") or "")
                if not fallback:
                    fallback = str(
                        (last_values or {}).get("route") or request_text or "done"
                    )
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
