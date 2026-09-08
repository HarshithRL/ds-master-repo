"""Proxy project workspace chat to the AI Brain AgentServer."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from services import brain_client
from services import procurement_serializers as serializers
from shared.db.repos import projects as project_repo
from shared.logger_global import bind_context, get_logger

log = get_logger(__name__)

_STEP_NODES = frozenset(
    {
        "skip",
        "skip_main",
        "skip_deepagent",
        "procurement",
        "mark_procurement_route",
    }
)

_STEP_TITLES = {
    "skip_deepagent": "Skipped Deep Agents",
    "skip_main": "Skipped main agent",
    "skip": "Skipped procurement",
    "procurement": "Routed to procurement",
    "mark_procurement_route": "Started procurement",
}

_THOUGHT_LABEL = "Thought"
_TERMINAL_TYPES = frozenset({"done", "interrupt", "error"})


def step_title(node: str | None) -> str | None:
    value = (node or "").strip()
    if not value:
        return None
    return _STEP_TITLES.get(value)


def _item_text(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    content = item.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                parts.append(str(block.get("text") or ""))
        return "".join(parts)
    return str(item.get("text") or "")


def _custom(event: dict[str, Any]) -> dict[str, Any]:
    extra = event.get("custom_outputs")
    return extra if isinstance(extra, dict) else {}


@dataclass
class StreamAcc:
    answer: str = ""
    thoughts: list[dict[str, Any]] = field(default_factory=list)

    def add_step(self, title: str) -> dict[str, Any] | None:
        title = (title or "").strip()
        if not title:
            return None
        last = self.thoughts[-1] if self.thoughts else None
        if last is not None and last.get("kind") == "step" and last.get("label") == title:
            return None
        item = {"kind": "step", "label": title, "detail": ""}
        self.thoughts.append(item)
        return {"type": "thought", **item}

    def add_reasoning(self, detail: str) -> dict[str, Any] | None:
        piece = detail or ""
        if not piece:
            return None
        last = self.thoughts[-1] if self.thoughts else None
        if last is not None and last.get("kind") == "thought":
            last["detail"] = f"{last['detail']}{piece}"
            return {"type": "thought", **last}
        item = {"kind": "thought", "label": _THOUGHT_LABEL, "detail": piece}
        self.thoughts.append(item)
        return {"type": "thought", **item}


def map_brain_event(
    event: dict[str, Any],
    acc: StreamAcc,
) -> Iterator[dict[str, Any]]:
    """Translate one ResponsesAgent SSE object into workspace chat events."""
    event_type = str(event.get("type") or "")
    custom = _custom(event)
    kind = str(custom.get("kind") or "")
    node = str(custom.get("node") or "")

    if kind == "file_progress":
        yield {
            "type": "file_progress",
            "file_id": custom.get("file_id") or "",
            "filename": custom.get("filename") or "",
            "status": custom.get("status") or "",
            "chunk_count": custom.get("chunk_count") or 0,
            "error": custom.get("error") or "",
        }
        return

    if kind == "index_ready":
        yield {
            "type": "index_ready",
            "chunk_count": custom.get("chunk_count") or 0,
            "index_ready": True,
        }
        return

    if event_type == "response.output_text.delta":
        delta = str(event.get("delta") or "")
        if kind == "thought" or node in _STEP_NODES:
            if delta.strip():
                mapped = acc.add_reasoning(delta)
            else:
                mapped = acc.add_step(step_title(node) or "")
            if mapped is not None:
                yield mapped
            return
        if delta:
            acc.answer += delta
            yield {"type": "token", "text": delta}
        return

    if event_type != "response.output_item.done":
        return

    if custom.get("interrupted"):
        yield _interrupt_event(custom)
        return

    text = _item_text(event.get("item"))
    is_trace = kind == "thought" or node in _STEP_NODES
    if is_trace and not custom.get("final"):
        if text.strip():
            mapped = acc.add_reasoning(text)
        else:
            mapped = acc.add_step(step_title(node) or "")
        if mapped is not None:
            yield mapped
        return

    if not custom.get("final"):
        return

    if text:
        acc.answer = text
    done_text = acc.answer.strip() or "I could not generate a reply. Please try again."
    payload: dict[str, Any] = {
        "type": "done",
        "role": "ai",
        "text": done_text,
    }
    if acc.thoughts:
        payload["thoughts"] = list(acc.thoughts)
    yield payload


def _interrupt_event(custom: dict[str, Any]) -> dict[str, Any]:
    """HITL interrupt — SSE `event: interrupt`, never a generic error."""
    from ai_brain.core.kb.hitl import ACTIONS, GATE_ORDER, hitl_request_from_interrupts

    interrupts = custom.get("interrupts") or []
    request = hitl_request_from_interrupts(interrupts)
    event: dict[str, Any] = {
        "type": "interrupt",
        "thread_id": custom.get("thread_id"),
        "request": request,
        "interrupts": interrupts,
        "actions": list(ACTIONS),
        "gates": list(GATE_ORDER),
    }
    gate = request.get("gate") if isinstance(request, dict) else None
    if gate:
        event["gate"] = gate
    if custom.get("values") is not None:
        event["values"] = custom.get("values")
    return event


def _reply_from_resume(body: dict[str, Any]) -> dict[str, Any]:
    if body.get("interrupted"):
        return _interrupt_event(
            {
                "interrupted": True,
                "interrupts": body.get("interrupts") or [],
                "thread_id": body.get("thread_id"),
                "values": body.get("values"),
            }
        )
    text = _reply_from_invoke(body)
    return {"type": "done", "role": "ai", "text": text}


def _prepare(
    project_id: str,
    owner_id: str,
    message: str,
) -> tuple[dict[str, Any], str] | None:
    bind_context(project_id=project_id, workflow="chat.prepare")
    try:
        project_row = project_repo.get_for_owner(project_id, owner_id)
    except project_repo.ProjectNotFoundError:
        log.warning("workspace chat project not found project_id={}", project_id)
        return None
    user_text = (message or "").strip()
    if not user_text:
        raise ValueError("message is required")
    return serializers.chat_project_dict(project_row), user_text


def _reply_from_invoke(body: dict[str, Any]) -> str:
    procurement = body.get("procurement") if isinstance(body, dict) else None
    if isinstance(procurement, dict):
        text = str(procurement.get("main_agent") or procurement.get("deep_agent") or "")
        if text.strip():
            return text.strip()
    return "I could not generate a reply. Please try again."


def run_workspace_chat(
    project_id: str,
    owner_id: str,
    message: str,
    history: list | None = None,
) -> dict | None:
    """Invoke ai_brain /invoke. Returns AI reply or None if the project is missing."""
    del history
    bind_context(project_id=project_id, workflow="chat.sync")
    log.info("workspace chat sync started")

    prepared = _prepare(project_id, owner_id, message)
    if prepared is None:
        return None
    _project, user_text = prepared

    started = time.perf_counter()
    try:
        body = brain_client.post_invoke(
            user_text, thread_id=project_id, user_id=owner_id
        )
    except Exception:
        bind_context(workflow="chat.error")
        log.exception("workspace chat sync failed")
        raise

    text = _reply_from_invoke(body)
    bind_context(workflow="chat.done")
    log.info(
        "workspace chat sync done reply_len={} duration_ms={}",
        len(text),
        round((time.perf_counter() - started) * 1000, 2),
    )
    return {"role": "ai", "text": text}


def iter_workspace_chat_events(
    project_id: str,
    owner_id: str,
    message: str,
    history: list | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield SSE events from ai_brain /invocations: thought → token → done/error."""
    del history
    bind_context(project_id=project_id, workflow="chat.stream")
    log.info("workspace chat stream started")

    try:
        prepared = _prepare(project_id, owner_id, message)
    except ValueError as exc:
        bind_context(workflow="chat.error")
        log.warning("workspace chat validation error: {}", exc)
        yield {"type": "error", "detail": str(exc)}
        return

    if prepared is None:
        bind_context(workflow="chat.error")
        yield {"type": "error", "detail": "not_found"}
        return

    _project, user_text = prepared
    acc = StreamAcc()
    started = time.perf_counter()
    emitted_done = False

    try:
        for event in brain_client.iter_invocations_sse(
            user_text, thread_id=project_id, user_id=owner_id
        ):
            for mapped in map_brain_event(event, acc):
                if mapped.get("type") in _TERMINAL_TYPES:
                    emitted_done = True
                yield mapped
    except Exception as exc:  # noqa: BLE001
        bind_context(workflow="chat.error")
        log.exception("workspace chat stream failed: {}", exc)
        yield {
            "type": "error",
            "detail": f"{type(exc).__name__}: {str(exc)[:300]}",
        }
        return

    if not emitted_done:
        done_text = acc.answer.strip() or "I could not generate a reply. Please try again."
        payload: dict[str, Any] = {"type": "done", "role": "ai", "text": done_text}
        if acc.thoughts:
            payload["thoughts"] = list(acc.thoughts)
        yield payload

    bind_context(workflow="chat.done")
    log.info(
        "workspace chat stream done reply_len={} duration_ms={}",
        len(acc.answer),
        round((time.perf_counter() - started) * 1000, 2),
    )


def _load_project(project_id: str, owner_id: str) -> dict[str, Any] | None:
    try:
        project_row = project_repo.get_for_owner(project_id, owner_id)
    except project_repo.ProjectNotFoundError:
        log.warning("workspace chat project not found project_id={}", project_id)
        return None
    return serializers.chat_project_dict(project_row)


def run_workspace_resume(
    project_id: str,
    owner_id: str,
    resume: Any,
    checkpoint_id: str | None = None,
) -> dict[str, Any] | None:
    """Pass-through to brain `POST /v1/threads/{id}/resume`. None if project missing."""
    bind_context(project_id=project_id, workflow="chat.resume")
    if _load_project(project_id, owner_id) is None:
        return None
    if resume is None:
        raise ValueError("resume is required")
    started = time.perf_counter()
    try:
        body = brain_client.post_resume(
            project_id, resume, checkpoint_id=checkpoint_id, user_id=owner_id
        )
    except Exception:
        bind_context(workflow="chat.error")
        log.exception("workspace chat resume failed")
        raise
    mapped = _reply_from_resume(body)
    bind_context(workflow="chat.done")
    log.info(
        "workspace chat resume done type={} duration_ms={}",
        mapped.get("type"),
        round((time.perf_counter() - started) * 1000, 2),
    )
    return mapped


def iter_workspace_resume_events(
    project_id: str,
    owner_id: str,
    resume: Any,
    checkpoint_id: str | None = None,
) -> Iterator[dict[str, Any]]:
    """Stream resume SSE from the brain; interrupts stay `event: interrupt`."""
    bind_context(project_id=project_id, workflow="chat.resume_stream")
    if _load_project(project_id, owner_id) is None:
        yield {"type": "error", "detail": "not_found"}
        return
    if resume is None:
        yield {"type": "error", "detail": "resume is required"}
        return

    acc = StreamAcc()
    started = time.perf_counter()
    emitted_terminal = False
    try:
        for event in brain_client.iter_resume_sse(
            project_id, resume, checkpoint_id=checkpoint_id, user_id=owner_id
        ):
            for mapped in map_brain_event(event, acc):
                if mapped.get("type") in _TERMINAL_TYPES:
                    emitted_terminal = True
                yield mapped
    except Exception as exc:  # noqa: BLE001
        bind_context(workflow="chat.error")
        log.exception("workspace chat resume stream failed: {}", exc)
        yield {
            "type": "error",
            "detail": f"{type(exc).__name__}: {str(exc)[:300]}",
        }
        return

    if not emitted_terminal:
        done_text = acc.answer.strip() or "I could not generate a reply. Please try again."
        payload: dict[str, Any] = {"type": "done", "role": "ai", "text": done_text}
        if acc.thoughts:
            payload["thoughts"] = list(acc.thoughts)
        yield payload

    bind_context(workflow="chat.done")
    log.info(
        "workspace chat resume stream done duration_ms={}",
        round((time.perf_counter() - started) * 1000, 2),
    )


def sse_format(event: dict[str, Any]) -> str:
    """Encode one SSE frame (event name = type, data = JSON)."""
    event_type = event.get("type") or "message"
    payload = {k: v for k, v in event.items() if k != "type"}
    return f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
