"""HTTP client for the AI Brain AgentServer (Nexus / Procura)."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from typing import Any

from ai_brain.core.procurement_ai.capabilities import capability_from_request

import httpx

from shared.databricks_runtime import FORWARDED_IDENTITY_HEADERS
from shared.logger_global import get_logger

log = get_logger(__name__)

DEFAULT_BRAIN_BASE_URL = "http://127.0.0.1:8004"
DEFAULT_TIMEOUT_S = 120.0

WORKSPACE_PROCUREMENT = {"mainagent": True, "deepagent": False}


def brain_base_url() -> str:
    return os.getenv("BRAIN_BASE_URL", DEFAULT_BRAIN_BASE_URL).rstrip("/")


def _timeout() -> httpx.Timeout:
    raw = os.getenv("BRAIN_TIMEOUT", str(DEFAULT_TIMEOUT_S))
    try:
        seconds = float(raw)
    except ValueError:
        seconds = DEFAULT_TIMEOUT_S
    return httpx.Timeout(seconds, connect=10.0)


def workspace_procurement(project_id: str = "") -> dict[str, Any]:
    flags: dict[str, Any] = dict(WORKSPACE_PROCUREMENT)
    pid = (project_id or "").strip()
    if pid:
        flags["project_id"] = pid
    return flags


def brain_request_headers(*, stream: bool = False, user_id: str = "") -> dict[str, str]:
    """Identity + SSE headers for brain /invocations. Matches AgentServer `_user_id()`."""
    headers: dict[str, str] = {}
    if stream:
        headers["Accept"] = "text/event-stream"
    uid = (user_id or "").strip()
    if uid:
        headers["x-user-id"] = uid
    headers.update(_flask_forwarded_headers())
    return headers


def _flask_forwarded_headers() -> dict[str, str]:
    """Copy Apps visitor OBO headers from the current Flask request, if any."""
    try:
        from flask import has_request_context, request
    except ImportError:
        return {}
    if not has_request_context():
        return {}
    found: dict[str, str] = {}
    for name in FORWARDED_IDENTITY_HEADERS:
        value = request.headers.get(name)
        if value and str(value).strip():
            found[name] = str(value).strip()
    return found


def invoke_body(
    request_text: str,
    thread_id: str,
    *,
    project_id: str = "",
    user_id: str = "",
) -> dict[str, Any]:
    pid = (project_id or thread_id or "").strip()
    procurement = workspace_procurement(pid)
    capability = capability_from_request(request_text)
    if capability:
        procurement["capability"] = capability
    return {
        "request": request_text,
        "procurement": procurement,
        "thread_id": thread_id,
        "project_id": pid,
    }


def invocations_body(
    request_text: str,
    thread_id: str,
    *,
    project_id: str = "",
    user_id: str = "",
) -> dict[str, Any]:
    pid = (project_id or thread_id or "").strip()
    procurement = workspace_procurement(pid)
    capability = capability_from_request(request_text)
    if capability:
        procurement["capability"] = capability
    custom: dict[str, Any] = {
        "request": request_text,
        "procurement": procurement,
        "thread_id": thread_id,
        "project_id": pid,
    }
    uid = (user_id or "").strip()
    if uid:
        custom["user_id"] = uid
    return {
        "input": [{"role": "user", "content": request_text, "type": "message"}],
        "custom_inputs": custom,
        "stream": True,
    }


def post_invoke(
    request_text: str,
    thread_id: str,
    *,
    project_id: str = "",
    user_id: str = "",
) -> dict[str, Any]:
    url = f"{brain_base_url()}/invoke"
    with httpx.Client(timeout=_timeout()) as client:
        response = client.post(
            url,
            json=invoke_body(request_text, thread_id, project_id=project_id),
            headers=brain_request_headers(user_id=user_id),
        )
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise ValueError("brain /invoke did not return an object")
        return body


def _iter_sse_buffer(buffer: str) -> tuple[list[str], str]:
    normalized = buffer.replace("\r\n", "\n").replace("\r", "\n")
    frames: list[str] = []
    while True:
        sep = normalized.find("\n\n")
        if sep == -1:
            return frames, normalized
        frames.append(normalized[:sep])
        normalized = normalized[sep + 2 :]


def parse_sse_frame(raw_event: str) -> dict[str, Any] | None:
    data_lines: list[str] = []
    for line in raw_event.split("\n"):
        if line.startswith("data:"):
            data_lines.append(line[5:].strip())
    if not data_lines:
        return None
    payload = "\n".join(data_lines)
    if payload == "[DONE]":
        return None
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        log.warning("brain SSE frame was not JSON")
        return None
    return parsed if isinstance(parsed, dict) else None


def resume_body(resume: Any, checkpoint_id: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"resume": resume}
    if checkpoint_id:
        body["checkpoint_id"] = checkpoint_id
    return body


def post_resume(
    thread_id: str,
    resume: Any,
    checkpoint_id: str | None = None,
    *,
    user_id: str = "",
) -> dict[str, Any]:
    url = f"{brain_base_url()}/v1/threads/{thread_id}/resume"
    with httpx.Client(timeout=_timeout()) as client:
        response = client.post(
            url,
            json=resume_body(resume, checkpoint_id),
            headers=brain_request_headers(user_id=user_id),
        )
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise ValueError("brain /resume did not return an object")
        return body


def _iter_sse_response(response: httpx.Response) -> Iterator[dict[str, Any]]:
    buffer = ""
    for chunk in response.iter_text():
        buffer += chunk
        frames, buffer = _iter_sse_buffer(buffer)
        for raw in frames:
            event = parse_sse_frame(raw)
            if event is not None:
                yield event
    if buffer.strip():
        event = parse_sse_frame(buffer)
        if event is not None:
            yield event


def iter_invocations_sse(
    request_text: str,
    thread_id: str,
    *,
    project_id: str = "",
    user_id: str = "",
) -> Iterator[dict[str, Any]]:
    url = f"{brain_base_url()}/invocations"
    with httpx.Client(timeout=_timeout()) as client:
        with client.stream(
            "POST",
            url,
            json=invocations_body(
                request_text, thread_id, project_id=project_id, user_id=user_id
            ),
            headers=brain_request_headers(stream=True, user_id=user_id),
        ) as response:
            response.raise_for_status()
            yield from _iter_sse_response(response)


def post_response(
    request_text: str,
    thread_id: str,
    *,
    project_id: str = "",
    user_id: str = "",
) -> dict[str, Any]:
    """Create a durable OpenResponses run and return its response metadata."""
    url = f"{brain_base_url()}/responses"
    body = invocations_body(request_text, thread_id, project_id=project_id, user_id=user_id)
    body["background"] = True
    body["stream"] = False
    with httpx.Client(timeout=httpx.Timeout(10.0, connect=10.0)) as client:
        response = client.post(url, json=body, headers=brain_request_headers(user_id=user_id))
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not payload.get("id"):
            raise ValueError("brain /responses did not return a response id")
        return payload


def iter_response_events(response_id: str, *, starting_after: int = 0, user_id: str = "") -> Iterator[dict[str, Any]]:
    """Retrieve a durable response stream, resuming after an event cursor."""
    url = f"{brain_base_url()}/responses/{response_id}"
    params = {"stream": "true", "starting_after": max(0, int(starting_after))}
    # Read timeout is intentionally unlimited: the server heartbeats and emits
    # persisted events for up to the configured durable-run deadline.
    timeout = httpx.Timeout(connect=10.0, read=None, write=30.0, pool=30.0)
    with httpx.Client(timeout=timeout) as client:
        with client.stream(
            "GET", url, params=params, headers=brain_request_headers(stream=True, user_id=user_id)
        ) as response:
            response.raise_for_status()
            yield from _iter_sse_response(response)


def iter_resume_sse(
    thread_id: str,
    resume: Any,
    checkpoint_id: str | None = None,
    *,
    user_id: str = "",
) -> Iterator[dict[str, Any]]:
    url = f"{brain_base_url()}/v1/threads/{thread_id}/resume"
    with httpx.Client(timeout=_timeout()) as client:
        with client.stream(
            "POST",
            url,
            json=resume_body(resume, checkpoint_id),
            headers=brain_request_headers(stream=True, user_id=user_id),
        ) as response:
            response.raise_for_status()
            yield from _iter_sse_response(response)
