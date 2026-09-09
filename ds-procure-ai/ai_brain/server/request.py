"""Map ResponsesAgentRequest / Mate payloads onto Nexus graph input."""

from __future__ import annotations

import uuid
from typing import Any

from mlflow.types.responses import ResponsesAgentRequest

from ai_brain.core.utils.content import content_text
from ai_brain.server.schemas import InvokeRequest, ProcurementFlags


def new_thread_id() -> str:
    return str(uuid.uuid4())


def normalize_thread_id(raw: str | None) -> str:
    value = (raw or "").strip() or new_thread_id()
    return value[:255]


def user_text_from_responses(request: ResponsesAgentRequest) -> str:
    custom = request.custom_inputs or {}
    if custom.get("request"):
        return str(custom["request"]).strip()
    for item in request.input or []:
        role = getattr(item, "role", None)
        if role != "user":
            continue
        return content_text(getattr(item, "content", "")).strip()
    return ""


def procurement_from_custom(custom: dict[str, Any] | None) -> dict[str, Any]:
    flags = (custom or {}).get("procurement") or {}
    parsed = ProcurementFlags.model_validate(flags if isinstance(flags, dict) else {})
    data = parsed.model_dump()
    data.setdefault("main_agent", "")
    data.setdefault("deep_agent", "")
    return data


def graph_config(
    thread_id: str,
    checkpoint_id: str | None = None,
    user_id: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    from ai_brain.server.tracing import langchain_callbacks

    configurable: dict[str, Any] = {"thread_id": thread_id}
    if checkpoint_id:
        configurable["checkpoint_id"] = checkpoint_id
    if user_id:
        configurable["user_id"] = user_id
    pid = (project_id or "").strip()
    if pid:
        configurable["project_id"] = pid
    metadata: dict[str, Any] = {
        "thread_id": thread_id,
        "mlflow.trace.session": thread_id,
    }
    if user_id:
        metadata["user_id"] = user_id
    if pid:
        metadata["project_id"] = pid
    return {
        "configurable": configurable,
        "metadata": metadata,
        "tags": ["ai_brain", "nexus"],
        "callbacks": langchain_callbacks(),
    }


def graph_payload(request_text: str, procurement: dict[str, Any]) -> dict[str, Any]:
    text = request_text or ""
    payload: dict[str, Any] = {
        "request": text,
        "project_id": str(procurement.get("project_id") or "").strip(),
        "capability": str(procurement.get("capability") or "").strip(),
        "procurement": procurement,
        "route": "",
    }
    if text:
        payload["messages"] = [{"role": "user", "content": text}]
    return payload


def parse_responses_request(
    request: ResponsesAgentRequest,
) -> tuple[str, dict[str, Any], str, Any, str | None]:
    custom = request.custom_inputs or {}
    text = user_text_from_responses(request)
    procurement = procurement_from_custom(custom)
    thread_id = normalize_thread_id(str(custom.get("thread_id") or "") or None)
    resume = custom.get("resume")
    checkpoint_id = custom.get("checkpoint_id")
    checkpoint = str(checkpoint_id) if checkpoint_id else None
    return text, procurement, thread_id, resume, checkpoint


def parse_mate_request(
    body: InvokeRequest,
) -> tuple[str, dict[str, Any], str, Any, str | None]:
    text = (body.request or "").strip()
    flags = body.procurement.model_dump()
    if body.capability:
        flags["capability"] = body.capability
    if body.project_id:
        flags["project_id"] = body.project_id
    procurement = procurement_from_custom({"procurement": flags})
    thread_id = normalize_thread_id(body.thread_id or None)
    return text, procurement, thread_id, body.resume, body.checkpoint_id
