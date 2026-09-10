"""MLflow AgentServer @invoke / @stream handlers for the Nexus graph."""

from __future__ import annotations

from typing import Any

from langgraph.types import Command
from mlflow.genai.agent_server import get_request_headers, invoke, stream
from mlflow.types.responses import (
    ResponsesAgentRequest,
    ResponsesAgentResponse,
)

from ai_brain.server.request import (
    graph_config,
    graph_payload,
    parse_responses_request,
)
from ai_brain.server.runtime import runtime
from ai_brain.server.streaming import iter_response_events
from shared.databricks_runtime import bind_obo_from_headers, clear_obo


def _user_id() -> str:
    headers = get_request_headers() or {}
    lowered = {str(k).lower(): v for k, v in headers.items()}
    return (
        lowered.get("x-user-id")
        or lowered.get("x-forwarded-email")
        or lowered.get("x-forwarded-preferred-username")
        or "anonymous"
    )


def user_id_from_request(request: ResponsesAgentRequest) -> str:
    """Prefer custom_inputs.user_id (Flask Mate/stream), else HTTP identity headers."""
    custom = request.custom_inputs or {}
    if isinstance(custom, dict):
        from_custom = str(custom.get("user_id") or "").strip()
        if from_custom:
            return from_custom
    return _user_id()


def _graph_input(
    text: str,
    procurement: dict[str, Any],
    resume: Any,
) -> dict[str, Any] | Command:
    if resume is not None:
        return Command(resume=resume)
    return graph_payload(text, procurement)


async def _ensure_runtime() -> None:
    if runtime.graph is None or runtime.semaphore is None:
        raise RuntimeError("Nexus graph runtime is not started")


@stream()
async def streaming(request: ResponsesAgentRequest):
    await _ensure_runtime()
    bind_obo_from_headers(get_request_headers() or {})
    try:
        async for event in _stream_graph(request):
            yield event
    finally:
        # AgentServer may iterate this generator after FastAPI middleware
        # has already returned; do not leave a visitor token on the task.
        clear_obo()


async def _stream_graph(request: ResponsesAgentRequest):
    text, procurement, thread_id, resume, checkpoint_id = parse_responses_request(request)
    if resume is None and not text:
        raise ValueError("request text is required")
    user_id = user_id_from_request(request)
    config = graph_config(
        thread_id,
        checkpoint_id,
        user_id=user_id,
        project_id=str((procurement or {}).get("project_id") or ""),
    )
    payload = _graph_input(text, procurement, resume)
    async with runtime.semaphore:
        async for event in iter_response_events(
            runtime.graph,
            payload=payload,
            config=config,
            request_text=text,
            procurement=procurement,
            thread_id=thread_id,
            user_id=user_id,
        ):
            yield event


@invoke()
async def non_streaming(request: ResponsesAgentRequest) -> ResponsesAgentResponse:
    outputs: list[Any] = []
    custom: dict[str, Any] = {}
    async for event in streaming(request):
        if event.type != "response.output_item.done":
            continue
        item = event.item if hasattr(event, "item") else None
        if item is None and isinstance(event, dict):
            item = event.get("item")
        if item is not None:
            outputs.append(item)
        extra = event.custom_outputs if hasattr(event, "custom_outputs") else None
        if extra:
            custom.update(extra)
    return ResponsesAgentResponse(output=outputs, custom_outputs=custom or None)
