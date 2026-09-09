from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import pytest
from langchain_core.messages import AIMessage

from ai_brain.core.procurement_ai.knowledge import (
    knowledge_prompt_block,
    search_chunks,
)
from ai_brain.core.procurement_ai.subagents.main_agent import (
    ProcuraContext,
    _runtime_project_id,
    get_procura_main_agent,
    project_id_for_agent,
    procura_kb_prompt,
)


class _Project:
    id = "proj-demo"
    code = "PR-100"
    name = "SWIFT CSP assessment"
    business_process = "Indirect"
    category = "SWIFT CSCF"
    description = "Professional services days"


class _Artifact:
    def __init__(self, artifact_id: str, name: str):
        self.id = artifact_id
        self.original_name = name
        self.parse_status = "ok"


class _Chunk:
    def __init__(self, artifact_id: str, text: str, ordinal: int = 0, page: int = 1):
        self.id = f"c-{ordinal}"
        self.artifact_id = artifact_id
        self.ordinal = ordinal
        self.text = text
        self.location_json = f'{{"page": {page}}}'
        self.heading_path_json = '["Pricing"]'


def test_search_ranks_price_chunk_first():
    artifacts = [
        _Artifact("a1", "EY_proposal.pdf"),
        _Artifact("a2", "KPMG_proposal.pdf"),
    ]
    chunks = [
        _Chunk("a1", "Team bios and office locations in Brussels.", ordinal=0),
        _Chunk("a1", "Day rate is 1,250 EUR for the senior manager.", ordinal=1, page=4),
        _Chunk("a2", "Approach to SWIFT CSP independent assessment.", ordinal=2),
    ]
    hits = search_chunks("what is the day rate", artifacts, chunks)
    assert hits
    assert hits[0]["file"] == "EY_proposal.pdf"
    assert hits[0]["locator"] == "p.4"
    assert "1,250 EUR" in hits[0]["text"]


def test_search_falls_back_when_query_has_no_overlap():
    artifacts = [_Artifact("a1", "EY_proposal.pdf")]
    chunks = [_Chunk("a1", "SWIFT CSP independent assessment proposal.", ordinal=0)]
    hits = search_chunks("zzzz-no-match", artifacts, chunks)
    assert len(hits) == 1
    assert "SWIFT CSP" in hits[0]["text"]


def test_knowledge_prompt_block_empty_project_id():
    assert knowledge_prompt_block("", "hello") == ""
    assert knowledge_prompt_block("   ", "hello") == ""


def test_knowledge_prompt_block_includes_excerpts(monkeypatch):
    def fake_load(_pid: str):
        return _Project(), [_Artifact("a1", "EY_proposal.pdf")], [
            _Chunk("a1", "Blended rate 900 EUR per day.", ordinal=0, page=2)
        ]

    monkeypatch.setattr(
        "ai_brain.core.procurement_ai.knowledge.load_context",
        fake_load,
    )
    monkeypatch.setattr(
        "ai_brain.core.procurement_ai.knowledge._matrix_source",
        lambda _pid: None,
    )
    monkeypatch.setattr(
        "ai_brain.core.procurement_ai.knowledge._hybrid_excerpts",
        lambda *_a, **_k: "",
    )
    block = knowledge_prompt_block("proj-demo", "blended rate")
    assert "## Project knowledge base" in block
    assert "PR-100" in block
    assert "EY_proposal.pdf" in block
    assert "p.2" in block
    assert "900 EUR" in block


def test_knowledge_prompt_block_includes_sql_evidence(monkeypatch):
    def fake_load(_pid: str):
        return _Project(), [_Artifact("a1", "EY_proposal.pdf")], [
            _Chunk("a1", "Team bios.", ordinal=0, page=1)
        ]

    cell = SimpleNamespace(status="met", text="Two BICs in scope", page=4)
    req = SimpleNamespace(
        id="R01",
        text="SWIFT BIC scope",
        ordinal=1,
        section="scope",
        category="",
    )
    source = SimpleNamespace(
        warm=True,
        summary="Matrix from SQL evidence (1 bids, 1 requirements). 1 met.",
        flags=["low_parse (art-1)"],
        requirements=[req],
        bids=["ey"],
        cells={("R01", "ey"): cell},
        bid_labels={"ey": "EY"},
        sources_by_bid={"ey": ["EY_proposal.pdf"]},
        pricing_lines=[
            SimpleNamespace(
                vendor_id="ey",
                offer_type="time_and_materials",
                role="senior manager",
                seniority="",
                rate=1250,
                rate_unit="day",
                currency="EUR",
                line_total=None,
                page=4,
            )
        ],
    )
    monkeypatch.setattr(
        "ai_brain.core.procurement_ai.knowledge.load_context",
        fake_load,
    )
    monkeypatch.setattr(
        "ai_brain.core.procurement_ai.knowledge._matrix_source",
        lambda _pid: source,
    )
    monkeypatch.setattr(
        "ai_brain.core.procurement_ai.knowledge._hybrid_excerpts",
        lambda *_a, **_k: "",
    )
    block = knowledge_prompt_block("proj-demo", "BIC rate")
    assert "Structured evidence" in block
    assert "R01" in block
    assert "EY" in block
    assert "1250" in block
    assert "Quality flags" in block


def test_project_id_for_agent_prefers_state_then_thread():
    assert project_id_for_agent({"project_id": "p-state"}, None) == "p-state"
    assert (
        project_id_for_agent(
            {"procurement": {"project_id": "p-flag"}},
            {"configurable": {"thread_id": "p-thread"}},
        )
        == "p-flag"
    )
    assert (
        project_id_for_agent({}, {"configurable": {"project_id": "p-cfg", "thread_id": "p-thread"}})
        == "p-cfg"
    )
    assert (
        project_id_for_agent({}, {"configurable": {"thread_id": "p-thread"}})
        == "p-thread"
    )


def test_runtime_project_id_prefers_context_over_thread():
    request = SimpleNamespace(
        runtime=SimpleNamespace(
            context=ProcuraContext(project_id="p-ctx"),
            config={"configurable": {"thread_id": "p-thread"}},
        )
    )
    assert _runtime_project_id(request) == "p-ctx"
    request.runtime.context = ProcuraContext(project_id="")
    assert _runtime_project_id(request) == "p-thread"


def test_create_agent_wires_kb_middleware(monkeypatch):
    get_procura_main_agent.cache_clear()
    captured: dict = {}

    def fake_create_agent(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(name="agent")

    fake_config = ModuleType("ai_brain.core.config")
    fake_config.get_llm = lambda **_k: object()
    monkeypatch.setitem(sys.modules, "ai_brain.core.config", fake_config)
    monkeypatch.setattr("langchain.agents.create_agent", fake_create_agent)
    try:
        agent = get_procura_main_agent()
        assert agent.name == "agent"
        names = {
            getattr(tool, "name", None) or getattr(tool, "__name__", "")
            for tool in captured["tools"]
        }
        assert "search_project_kb" in names
        assert "list_bid_chunks" in names
        assert captured["context_schema"] is ProcuraContext
        assert procura_kb_prompt in captured["middleware"]
    finally:
        get_procura_main_agent.cache_clear()


@pytest.mark.asyncio
async def test_main_agent_sets_kb_project_id_for_search(monkeypatch):
    from ai_brain.core.kb.store.search import current_project_id
    from ai_brain.core.procurement_ai.subagents import main_agent as ma

    seen: list[str] = []

    class StubAgent:
        async def ainvoke(self, payload, config=None, context=None, **_kwargs):
            seen.append(current_project_id())
            messages = list(payload.get("messages") or [])
            return {"messages": [*messages, AIMessage(content="from-kb")]}

    async def no_ltm(*_a, **_k):
        return ""

    monkeypatch.setattr(ma, "get_procura_main_agent", lambda: StubAgent())
    monkeypatch.setattr(ma, "load_memory_block", no_ltm)
    monkeypatch.setattr(ma, "maybe_remember", no_ltm)
    out = await ma.main_agent(
        {
            "project_id": "proj-kb",
            "request": "what is the day rate",
            "messages": [],
            "procurement": {},
        },
        {"configurable": {}},
    )
    assert seen == ["proj-kb"]
    assert out["procurement"]["main_agent"] == "from-kb"
    with pytest.raises(RuntimeError):
        current_project_id()
