"""Health, Mate /invoke alias, and LangGraph HITL thread routes."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from mlflow.types.responses import ResponsesAgentRequest

from ai_brain.server.agent import non_streaming, streaming
from ai_brain.server.request import graph_config, parse_mate_request
from ai_brain.server.runtime import runtime
from ai_brain.server.schemas import (
    InvokeRequest,
    InvokeResponse,
    ProcurementResult,
    ResumeRequest,
)
from ai_brain.server.streaming import _interrupts_from_state, _jsonable


def _require_graph() -> Any:
    if runtime.graph is None or not runtime.ready:
        raise HTTPException(status_code=503, detail="graph runtime not ready")
    return runtime.graph


def _procurement_custom_inputs(procurement: dict[str, Any]) -> dict[str, Any]:
    """Keep flags Flask already set; do not drop project_id / capability."""
    return {
        "mainagent": bool(procurement.get("mainagent")),
        "deepagent": bool(procurement.get("deepagent")),
        "project_id": str(procurement.get("project_id") or ""),
        "capability": str(procurement.get("capability") or ""),
    }


def _responses_custom_inputs(
    *,
    text: str,
    procurement: dict[str, Any],
    thread_id: str,
    resume: Any = None,
    checkpoint_id: str | None = None,
    user_id: str = "",
) -> dict[str, Any]:
    custom: dict[str, Any] = {
        "request": text,
        "procurement": _procurement_custom_inputs(procurement),
        "thread_id": thread_id,
        "resume": resume,
        "checkpoint_id": checkpoint_id,
    }
    uid = (user_id or "").strip()
    if uid:
        custom["user_id"] = uid
    return custom


def _values_to_invoke_response(
    values: dict[str, Any],
    *,
    request_text: str,
    thread_id: str,
    interrupts: list[Any],
) -> InvokeResponse:
    procurement = values.get("procurement") or {}
    return InvokeResponse(
        request=values.get("request", request_text),
        route=str(values.get("route") or ""),
        thread_id=thread_id,
        interrupted=bool(interrupts),
        interrupts=interrupts,
        procurement=ProcurementResult.model_validate(procurement),
    )


async def _thread_state_or_404(thread_id: str, checkpoint_id: str | None = None):
    graph = _require_graph()
    config = graph_config(thread_id, checkpoint_id)
    state = await graph.aget_state(config)
    values = getattr(state, "values", None) or {}
    if not values and not getattr(state, "next", None):
        raise HTTPException(status_code=404, detail="thread not found")
    return graph, config, state, values


def register_routes(app: FastAPI) -> None:
    @app.get("/")
    async def root() -> dict[str, Any]:
        return {
            "status": "ok" if runtime.ready and runtime.graph is not None else "starting",
            "service": "ai_brain",
            "health": "/health",
            "ready": "/ready",
        }

    @app.get("/ready")
    async def ready() -> dict[str, Any]:
        return {
            "status": "ok" if runtime.ready and runtime.graph is not None else "starting",
            "service": "ai_brain",
            "graph": runtime.graph is not None,
        }

    @app.post("/invoke", response_model=InvokeResponse)
    async def mate_invoke(
        body: InvokeRequest,
        x_user_id: str | None = Header(default=None, alias="x-user-id"),
    ) -> InvokeResponse:
        text, procurement, thread_id, resume, checkpoint_id = parse_mate_request(body)
        if resume is None and not text:
            raise HTTPException(status_code=400, detail="request is required")
        request = ResponsesAgentRequest(
            input=[{"role": "user", "content": text or "resume", "type": "message"}],
            custom_inputs=_responses_custom_inputs(
                text=text,
                procurement=procurement,
                thread_id=thread_id,
                resume=resume,
                checkpoint_id=checkpoint_id,
                user_id=x_user_id or "",
            ),
        )
        result = await non_streaming(request)
        custom = result.custom_outputs or {}
        _, _, state, values = await _thread_state_or_404(thread_id, checkpoint_id)
        return _values_to_invoke_response(
            values if isinstance(values, dict) else {},
            request_text=text,
            thread_id=str(custom.get("thread_id") or thread_id),
            interrupts=list(custom.get("interrupts") or _interrupts_from_state(state)),
        )

    @app.get("/v1/threads/{thread_id}/state")
    async def thread_state(thread_id: str) -> dict[str, Any]:
        _, config, state, values = await _thread_state_or_404(thread_id)
        return {
            "thread_id": thread_id,
            "values": _jsonable(values),
            "next": list(getattr(state, "next", None) or ()),
            "interrupts": _interrupts_from_state(state),
            "config": _jsonable(config),
        }

    @app.get("/v1/threads/{thread_id}/history")
    async def thread_history(thread_id: str, limit: int = 20) -> dict[str, Any]:
        graph, config, _, _ = await _thread_state_or_404(thread_id)
        snapshots: list[dict[str, Any]] = []
        async for snap in graph.aget_state_history(config, limit=max(1, min(limit, 100))):
            snap_config = getattr(snap, "config", None) or {}
            configurable = (
                snap_config.get("configurable") if isinstance(snap_config, dict) else {}
            )
            snapshots.append(
                {
                    "checkpoint_id": (configurable or {}).get("checkpoint_id"),
                    "next": list(getattr(snap, "next", None) or ()),
                    "values": _jsonable(getattr(snap, "values", None) or {}),
                }
            )
        return {"thread_id": thread_id, "history": snapshots}

    @app.post("/v1/threads/{thread_id}/update")
    async def thread_update(thread_id: str, body: dict[str, Any]) -> dict[str, Any]:
        graph, config, _, _ = await _thread_state_or_404(thread_id)
        values = body.get("values")
        if not isinstance(values, dict):
            raise HTTPException(status_code=400, detail="values object is required")
        as_node = body.get("as_node")
        result_config = await graph.aupdate_state(config, values, as_node=as_node)
        return {"thread_id": thread_id, "config": _jsonable(result_config)}

    @app.post("/v1/threads/{thread_id}/resume", response_model=None)
    async def thread_resume(
        thread_id: str,
        body: ResumeRequest,
        accept: str | None = Header(default=None),
        x_user_id: str | None = Header(default=None, alias="x-user-id"),
    ):
        await _thread_state_or_404(thread_id)
        custom: dict[str, Any] = {
            "request": "",
            "thread_id": thread_id,
            "resume": body.resume,
            "checkpoint_id": body.checkpoint_id,
        }
        uid = (x_user_id or "").strip()
        if uid:
            custom["user_id"] = uid
        request = ResponsesAgentRequest(
            input=[{"role": "user", "content": "resume", "type": "message"}],
            custom_inputs=custom,
        )
        if accept and "text/event-stream" in accept:
            async def event_bytes():
                async for event in streaming(request):
                    yield f"data: {event.model_dump_json(exclude_none=True)}\n\n"
                yield "data: [DONE]\n\n"

            return StreamingResponse(event_bytes(), media_type="text/event-stream")

        result = await non_streaming(request)
        custom = result.custom_outputs or {}
        _, _, state, values = await _thread_state_or_404(thread_id, body.checkpoint_id)
        return _values_to_invoke_response(
            values if isinstance(values, dict) else {},
            request_text="",
            thread_id=thread_id,
            interrupts=list(custom.get("interrupts") or _interrupts_from_state(state)),
        )

    from ai_brain.server.project_routes import register_project_routes

    register_project_routes(app)
