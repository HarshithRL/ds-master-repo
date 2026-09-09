"""Extract visible text from LangChain / Responses message payloads."""

from __future__ import annotations

from typing import Any

_THOUGHT_TYPES = frozenset(
    {
        "reasoning",
        "thinking",
        "reasoning_content",
        "thought",
        "reasoning_text",
    }
)
_ANSWER_TYPES = frozenset({"text", "output_text", "input_text"})
_REASONING_KEYS = ("reasoning_content", "reasoning", "thinking")


def content_text(content: Any) -> str:
    answer, _thought = split_content_kinds(content)
    return answer


def _block_text(block: Any) -> str:
    if isinstance(block, str):
        return block
    if isinstance(block, dict):
        return str(block.get("text") or "")
    text = getattr(block, "text", None)
    return str(text) if text else ""


def _block_type(block: Any) -> str:
    if isinstance(block, dict):
        return str(block.get("type") or "")
    return str(getattr(block, "type", "") or "")


def _reasoning_string(value: str) -> bool:
    stripped = value.strip()
    return stripped.startswith("[{") and '"reasoning"' in stripped


def split_content_kinds(content: Any) -> tuple[str, str]:
    """Return ``(answer_text, thought_text)`` from a message content payload."""
    if content is None:
        return "", ""
    if isinstance(content, str):
        if _reasoning_string(content):
            return "", content
        return content, ""
    if isinstance(content, list):
        answers: list[str] = []
        thoughts: list[str] = []
        for block in content:
            if isinstance(block, str):
                if _reasoning_string(block):
                    thoughts.append(block)
                else:
                    answers.append(block)
                continue
            kind = _block_type(block)
            piece = _block_text(block)
            if not piece:
                continue
            if kind in _THOUGHT_TYPES:
                thoughts.append(piece)
            elif kind in _ANSWER_TYPES or not kind:
                answers.append(piece)
            elif "text" in (block if isinstance(block, dict) else {}):
                answers.append(piece)
        return "".join(answers), "".join(thoughts)
    text = getattr(content, "text", None)
    if text:
        value = str(text)
        if _reasoning_string(value):
            return "", value
        return value, ""
    return str(content), ""


def split_message_kinds(msg: Any) -> tuple[str, str]:
    """Split a LangChain / dict message into answer vs reasoning text."""
    if msg is None:
        return "", ""
    if isinstance(msg, dict):
        content = msg.get("content")
        additional = msg.get("additional_kwargs") or {}
    else:
        content = getattr(msg, "content", None)
        additional = getattr(msg, "additional_kwargs", None) or {}
    answer, thought = split_content_kinds(content)
    if isinstance(additional, dict):
        extras: list[str] = []
        for key in _REASONING_KEYS:
            extra = additional.get(key)
            if extra:
                extras.append(str(extra))
        if extras:
            thought = f"{thought}{''.join(extras)}"
    return answer, thought
