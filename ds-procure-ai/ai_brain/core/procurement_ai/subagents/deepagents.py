from __future__ import annotations

from functools import lru_cache
from typing import Any, Optional

import mlflow
from langchain_core.runnables import RunnableConfig
from mlflow.entities import SpanType

from ai_brain.core.utils.content import content_text


def _conversation_messages(state: dict[str, Any]) -> list[Any]:
    existing = list(state.get("messages") or [])
    if existing:
        return existing
    return [{"role": "user", "content": state.get("request") or "Hello"}]


@lru_cache(maxsize=1)
def get_deep_agent():
    from deepagents import create_deep_agent

    from ai_brain.core.config import get_llm

    return create_deep_agent(
        model=get_llm(),
        tools=[],
        system_prompt="You are a helpful assistant",
    )


@mlflow.trace(name="procura_deep_agent", span_type=SpanType.AGENT)
async def deepagent(
    state: dict[str, Any],
    # LangGraph matches this annotation literally; ``RunnableConfig | None``
    # is rejected and config is then never injected.
    config: Optional[RunnableConfig] = None,  # noqa: UP045
) -> dict[str, Any]:
    # LangChain: pass parent RunnableConfig into nested ainvoke so callbacks
    # (MlflowLangchainTracer) and token streaming propagate.
    result = await get_deep_agent().ainvoke(
        {"messages": _conversation_messages(state)},
        config=config,
    )
    messages = result.get("messages") or []
    last = messages[-1] if messages else None
    text = content_text(getattr(last, "content", "") if last is not None else "")
    return {"procurement": {"deep_agent": text}}
