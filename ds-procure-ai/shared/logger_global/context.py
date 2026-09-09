"""Request/workflow context propagated through contextvars."""

from __future__ import annotations

import contextvars
from typing import Any

_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "mate_request_id", default=None
)
_project_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "mate_project_id", default=None
)
_workflow: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "mate_workflow", default=None
)
_user_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "mate_user_id", default=None
)

_VAR_MAP: dict[str, contextvars.ContextVar[str | None]] = {
    "request_id": _request_id,
    "project_id": _project_id,
    "workflow": _workflow,
    "user_id": _user_id,
}

TokenEntry = tuple[contextvars.ContextVar[str | None], contextvars.Token[str | None]]
_bound_tokens_stack: contextvars.ContextVar[list[TokenEntry] | None] = contextvars.ContextVar(
    "mate_bound_tokens_stack",
    default=None,
)


def _active_token_stack() -> list[TokenEntry]:
    stack = _bound_tokens_stack.get()
    if stack is None:
        stack = []
        _bound_tokens_stack.set(stack)
    return stack


def bind_context(**kwargs: Any) -> None:
    stack = _active_token_stack()
    for key, value in kwargs.items():
        var = _VAR_MAP.get(key)
        if var is None or value is None:
            continue
        token = var.set(str(value))
        stack.append((var, token))


def reset_context() -> None:
    stack = _bound_tokens_stack.get()
    if not stack:
        return

    while stack:
        var, token = stack.pop()
        try:
            var.reset(token)
        except ValueError:
            # Debug reload or cross-context misuse — fall back to clearing the var.
            var.set(None)

    _bound_tokens_stack.set(None)


def get_context_dict() -> dict[str, str]:
    ctx: dict[str, str] = {}
    for key, var in _VAR_MAP.items():
        value = var.get()
        if value is not None:
            ctx[key] = value
    return ctx
