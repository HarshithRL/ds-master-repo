"""Strip MCP tool-result content-block `id` fields rejected by Claude/FM.

langchain-mcp-adapters v0.2+ adds LangChain standard-block `id` keys on
tool_result content. Anthropic / Bedrock Claude reject them with 400:
`tool_result.content.0.text.id: Extra inputs are not permitted`.

Workaround for https://github.com/langchain-ai/langchain-mcp-adapters/issues/397
"""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage


def strip_content_block_ids(content: Any) -> Any:
    """Drop `id` from list content blocks; leave string / other content alone."""
    if not isinstance(content, list):
        return content
    cleaned: list[Any] = []
    for block in content:
        cleaned.append(_strip_block_id(block))
    return cleaned


def _strip_block_id(block: Any) -> Any:
    if isinstance(block, dict):
        if "id" not in block:
            return block
        return {key: value for key, value in block.items() if key != "id"}
    if hasattr(block, "model_dump") and callable(block.model_dump):
        try:
            dumped = block.model_dump()
        except Exception:  # noqa: BLE001
            dumped = None
        if isinstance(dumped, dict):
            return {key: value for key, value in dumped.items() if key != "id"}
    if hasattr(block, "id"):
        try:
            data = dict(vars(block))
        except TypeError:
            return block
        data.pop("id", None)
        return data
    return block


def _sanitize_tool_message(result: Any) -> Any:
    if isinstance(result, ToolMessage):
        result.content = strip_content_block_ids(result.content)
        return result
    content = getattr(result, "content", None)
    if content is not None and hasattr(result, "content"):
        try:
            result.content = strip_content_block_ids(content)
        except Exception:  # noqa: BLE001
            pass
    return result


class StripToolContentIdsMiddleware(AgentMiddleware):
    """After each tool call, strip `id` from ToolMessage content blocks."""

    def wrap_tool_call(self, request, handler):
        result = handler(request)
        return _sanitize_tool_message(result)

    async def awrap_tool_call(self, request, handler):
        result = await handler(request)
        return _sanitize_tool_message(result)
