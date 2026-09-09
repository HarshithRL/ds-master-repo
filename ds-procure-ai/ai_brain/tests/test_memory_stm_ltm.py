"""STM checkpoint replay and LTM helper unit tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from ai_brain.core.procurement_ai.subagents.main_agent import (
    format_memory_block,
    get_procura_main_agent,
    memory_namespace,
    remember_payload,
)
from ai_brain.core.utils.content import content_text
from ai_brain.nexus_graph import build_nexes_graph
from ai_brain.server.request import graph_config, graph_payload


def _texts(messages: list) -> list[str]:
    out: list[str] = []
    for message in messages:
        if isinstance(message, dict):
            out.append(content_text(message.get("content")))
        else:
            out.append(content_text(getattr(message, "content", "")))
    return [text for text in out if text]


def test_memory_namespace_defaults():
    assert memory_namespace("alice", "proj-1") == ("alice", "proj-1", "memories")
    assert memory_namespace("", "") == ("anonymous", "_", "memories")
    assert memory_namespace("  ", "  ") == ("anonymous", "_", "memories")


def test_remember_payload():
    text = "Please remember I prefer EY for SWIFT."
    assert remember_payload(text) == text
    assert remember_payload("REMEMBER: blended rate 900") == "REMEMBER: blended rate 900"
    assert remember_payload("what is the day rate") is None
    assert remember_payload("") is None
    assert remember_payload(None) is None  # type: ignore[arg-type]


def test_format_memory_block():
    items = [
        SimpleNamespace(value={"text": "Prefers EY"}),
        SimpleNamespace(value={"data": "Budget 100k"}),
        SimpleNamespace(value="ignored"),
        SimpleNamespace(value={"text": ""}),
        SimpleNamespace(value={"text": "  "}),
    ]
    block = format_memory_block(items)
    assert block.startswith("## Long-term memories")
    assert "- Prefers EY" in block
    assert "- Budget 100k" in block
    assert format_memory_block([]) == ""
    assert format_memory_block([SimpleNamespace(value={"text": ""})]) == ""


@pytest.mark.asyncio
async def test_stm_second_turn_feeds_prior_messages(monkeypatch):
    """Two turns on the same thread_id must replay checkpointed messages into the agent."""
    get_procura_main_agent.cache_clear()
    captured: list[list] = []

    class StubAgent:
        async def ainvoke(self, payload, config=None, context=None, **_kwargs):
            messages = list(payload.get("messages") or [])
            captured.append(messages)
            reply = AIMessage(content=f"stub-reply-{len(captured)}")
            return {"messages": [*messages, reply]}

    monkeypatch.setattr(
        "ai_brain.core.procurement_ai.subagents.main_agent.get_procura_main_agent",
        lambda: StubAgent(),
    )

    graph = build_nexes_graph(checkpointer=InMemorySaver(), store=InMemoryStore())
    thread_id = "stm-thread-prior-messages"
    config = graph_config(thread_id, user_id="user-stm")
    procurement = {"mainagent": True, "deepagent": False, "project_id": "proj-stm"}

    await graph.ainvoke(graph_payload("my vendor is EY", procurement), config)
    await graph.ainvoke(graph_payload("who is my vendor", procurement), config)

    assert len(captured) == 2
    turn1 = _texts(captured[0])
    turn2 = _texts(captured[1])
    assert any("my vendor is EY" in text for text in turn1)
    assert any("my vendor is EY" in text for text in turn2)
    assert any("who is my vendor" in text for text in turn2)
    assert any("stub-reply-1" in text for text in turn2)
    get_procura_main_agent.cache_clear()
