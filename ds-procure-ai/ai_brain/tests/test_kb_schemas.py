"""W5 schemas, grounding gate, create_file_data invoke shape, Send fan-out (no live LLM)."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_brain.core.kb.api.schemas import (
    EvidenceItem,
    apply_grounding_gate,
    verify_grounding,
)
from shared.db.models import utc_now_iso


@pytest.fixture()
def db_env(monkeypatch):
    from shared.db import init_db
    from shared.db import connection as db_connection

    if db_connection._engine is not None:
        db_connection._engine.dispose()
    db_connection._engine = None
    db_connection._SessionLocal = None
    tmp = tempfile.mkdtemp()
    db_path = Path(tmp) / "test.sqlite"
    monkeypatch.setenv("MATE_SQLITE_PATH", str(db_path))
    init_db()
    yield db_path
    if db_connection._engine is not None:
        db_connection._engine.dispose()
    db_connection._engine = None
    db_connection._SessionLocal = None
    shutil.rmtree(tmp, ignore_errors=True)


def _seed_project():
    from shared.db.connection import session_scope
    from shared.db.models import AppUser, Artifact, Project, QualityFlag, Vendor

    now = utc_now_iso()
    with session_scope() as session:
        session.add(AppUser(workspace_id="u1", created_at=now, updated_at=now))
        session.add(
            Project(
                id="p1",
                code="PRJ-TEST",
                owner_id="u1",
                module_id="procurement-ai-assistant",
                name="t",
                status="Active",
                priority="Medium",
                progress=0,
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            Artifact(
                id="art-ok",
                project_id="p1",
                uploaded_by="u1",
                kind="upload",
                original_name="TF Inetum Proposal Etex CSP Assessment.pdf",
                storage_relpath="rel/ok",
                created_at=now,
                parse_status="ok",
                vendor_id="trifinance-inetum",
                doc_role="proposal",
                parsed_json=json.dumps(
                    {
                        "markdown": "## Page 1\nInetum will prepare the questionnaires.\n"
                    }
                ),
            )
        )
        session.add(
            Artifact(
                id="art-fail",
                project_id="p1",
                uploaded_by="u1",
                kind="upload",
                original_name="corrupt.pdf",
                storage_relpath="rel/fail",
                created_at=now,
                parse_status="error",
                parse_error="parser exploded",
                vendor_id="bdo",
                doc_role="proposal",
            )
        )
        session.add(
            Vendor(
                id="p1:trifinance",
                project_id="p1",
                name="TriFinance",
                legal_entity="TriFinance",
                registry_id="BE-X-882734939",
                status="bidder",
                created_at=now,
            )
        )
        session.add(
            Vendor(
                id="p1:inetum",
                project_id="p1",
                name="Inetum",
                legal_entity="Inetum",
                status="bidder",
                created_at=now,
            )
        )
        session.add(
            QualityFlag(
                id="qf1",
                project_id="p1",
                artifact_id="art-fail",
                kind="orphan_parse",
                detail="parse failed",
                severity="high",
                created_at=now,
            )
        )


def test_met_without_page_or_chunk_is_rejected():
    with pytest.raises(ValidationError, match="chunk_id or artifact_id"):
        EvidenceItem(
            requirement_id="r1",
            status="met",
            claim_text="we will assess CSCF",
            artifact_id="art-ok",
            page=None,
            confidence=0.9,
        )


def test_met_with_chunk_id_without_page_is_ok():
    item = EvidenceItem(
        requirement_id="r1",
        status="met",
        claim_text="we will assess CSCF",
        chunk_id="c1",
        confidence=0.9,
    )
    assert item.chunk_id == "c1"
    assert item.page is None


def test_not_stated_without_citation_is_ok():
    item = EvidenceItem(requirement_id="r1", status="not_stated", confidence=0.4)
    assert item.page is None
    assert item.claim_text is None


def test_verify_grounding_rejects_claim_absent_from_chunk():
    item = EvidenceItem(
        requirement_id="r1",
        status="met",
        claim_text="we offer 24x7 gold support",
        artifact_id="art-ok",
        page=3,
        chunk_id="c1",
        confidence=0.9,
    )
    assert verify_grounding(item, "Inetum will prepare the questionnaires.") is False


def test_verify_grounding_accepts_normalized_substring():
    item = EvidenceItem(
        requirement_id="r1",
        status="met",
        claim_text="INETUM will   prepare the questionnaires",
        artifact_id="art-ok",
        page=1,
        chunk_id="c1",
        confidence=0.8,
    )
    chunk = "Page 1\nInetum will prepare the questionnaires.\n"
    assert verify_grounding(item, chunk) is True


def test_ungrounded_claim_downgrades_status():
    item = EvidenceItem(
        requirement_id="r1",
        status="met",
        claim_text="hallucinated SLA",
        artifact_id="art-ok",
        page=1,
        confidence=0.95,
    )
    out = apply_grounding_gate(item, "unrelated chunk text")
    assert out.status == "unclear"
    assert out.confidence == 0.0


def test_ungrounded_claim_persists_quality_flag(db_env):
    from sqlalchemy import select

    from shared.db.connection import session_scope
    from shared.db.models import QualityFlag

    _seed_project()
    item = EvidenceItem(
        requirement_id="r1",
        status="met",
        claim_text="hallucinated SLA",
        artifact_id="art-ok",
        page=1,
        confidence=0.95,
    )
    apply_grounding_gate(item, "unrelated chunk text", project_id="p1")
    with session_scope() as session:
        flags = session.scalars(
            select(QualityFlag).where(QualityFlag.kind == "ungrounded_claim")
        ).all()
        assert len(flags) == 1
        assert flags[0].artifact_id == "art-ok"


def test_files_for_invoke_wraps_create_file_data(db_env):
    from ai_brain.core.kb.extract.agents import files_for_invoke, invoke_payload

    _seed_project()
    wrapped = files_for_invoke("p1")
    quality_path = "/project/PRJ-TEST/_quality/art-fail.md"
    assert quality_path in wrapped
    file_data = wrapped[quality_path]
    assert file_data["content"].startswith("# Parse quality")
    assert file_data["encoding"] == "utf-8"
    assert "created_at" in file_data
    payload = invoke_payload("p1", "extract this bid")
    assert "files" in payload
    assert payload["files"] is wrapped or quality_path in payload["files"]


def test_vendor_analyst_checkpointer_none_and_no_todo_middleware():
    from langchain.agents.middleware import TodoListMiddleware
    from langchain_core.language_models.fake_chat_models import FakeListChatModel

    from ai_brain.core.kb.extract.agents import build_vendor_analyst, extraction_middleware

    fake = FakeListChatModel(responses=["ok"])
    names = [type(item).__name__ for item in extraction_middleware(fake)]
    assert "TodoListMiddleware" not in names
    assert not any(isinstance(item, TodoListMiddleware) for item in extraction_middleware(fake))

    agent = build_vendor_analyst(model=fake, fallback_model=fake, store=None, tools=[])
    checkpointer = getattr(agent, "checkpointer", "missing")
    assert checkpointer is None

    from ai_brain.core.kb.extract.agents import build_vendor_emit, emit_middleware

    emit_names = [type(item).__name__ for item in emit_middleware(fake)]
    assert "ToolCallLimitMiddleware" not in emit_names
    emit = build_vendor_emit(model=fake, fallback_model=fake)
    assert getattr(emit, "checkpointer", "missing") is None


def test_plan_kb_build_emits_send_per_bid(db_env):
    from langgraph.types import Send

    from ai_brain.core.kb.build.pipeline import ANALYZE_BID_TIMEOUT_S, plan_kb_build

    _seed_project()
    out = plan_kb_build({"project_id": "p1"})
    assert isinstance(out, list)
    assert all(isinstance(item, Send) for item in out)
    assert {item.node for item in out} == {"analyze_bid"}
    assert {item.arg["bid_id"] for item in out} == {"bdo", "trifinance-inetum"}
    for item in out:
        assert item.timeout.run_timeout == ANALYZE_BID_TIMEOUT_S
        assert item.arg["project_id"] == "p1"
        assert "vendor_paths" in item.arg


def test_plan_kb_build_without_bids_routes_to_audit():
    from ai_brain.core.kb.build.pipeline import plan_kb_build

    assert plan_kb_build({"project_id": ""}) == "audit_kb"


def test_plan_publish_sends_three_fill_nodes():
    from langgraph.types import Send

    from ai_brain.core.kb.build.pipeline import plan_publish

    out = plan_publish(
        {
            "project_id": "p1",
            "procurement": {"kb_audit": {"bundle_count": 2, "failed": 0}},
        }
    )
    assert isinstance(out, list)
    assert {item.node for item in out} == {
        "fill_overview",
        "fill_requirements",
        "fill_vendors",
    }
    overview = next(item for item in out if item.node == "fill_overview")
    assert isinstance(overview, Send)
    assert overview.arg["project_id"] == "p1"
    assert overview.arg["kb_audit"]["bundle_count"] == 2


@pytest.mark.asyncio
async def test_analyze_bid_persists_grounded_bundle(db_env, monkeypatch):
    from sqlalchemy import select

    from ai_brain.core.kb.build import pipeline
    from ai_brain.core.kb.store.persist import seed_swift_requirements
    from ai_brain.core.kb.api.schemas import (
        EvidenceItem,
        PricingExtraction,
        PricingLineItem,
        VendorEvidenceBundle,
    )
    from shared.db.connection import session_scope
    from shared.db.models import PricingLine

    _seed_project()
    seed_swift_requirements("p1")

    async def fake_invoke(project_id, bid_id, config=None):
        bundle = VendorEvidenceBundle(
            bid_id=bid_id,
            items=[
                EvidenceItem(
                    requirement_id="R01",
                    status="met",
                    claim_text="Inetum will prepare the questionnaires.",
                    artifact_id="art-ok",
                    page=1,
                    chunk_id=None,
                    confidence=0.9,
                )
            ],
        )
        pricing = PricingExtraction(
            bid_id=bid_id,
            lines=[
                PricingLineItem(
                    offer_type="fixed_price",
                    role="CSP assessment",
                    line_total=12000,
                    currency="EUR",
                )
            ],
        )
        return bundle, pricing, 1, None

    monkeypatch.setattr(pipeline, "invoke_vendor_analyst", fake_invoke)
    out = await pipeline.analyze_bid({"project_id": "p1", "bid_id": "trifinance-inetum"})
    bundle = out["kb_bundles"][0]
    assert bundle["status"] == "ok"
    assert bundle["persist"]["inserted"] >= 1
    assert bundle["pricing_lines"] >= 1

    from ai_brain.core.procurement_ai.packs.matrix_from_evidence import load_matrix_source

    source = load_matrix_source("p1")
    assert source.warm
    cell = source.cells.get(("R01", "trifinance-inetum"))
    assert cell is not None
    assert cell.status == "met"
    with session_scope() as session:
        rows = list(
            session.scalars(
                select(PricingLine).where(
                    PricingLine.project_id == "p1",
                    PricingLine.vendor_id == "trifinance-inetum",
                )
            ).all()
        )
        assert len(rows) == 1
        assert rows[0].role == "CSP assessment"


def test_langchain_kb_tools_include_search():
    from ai_brain.core.kb.api.mcp_tools import langchain_kb_tools, search_project_kb

    names = {getattr(t, "__name__", str(t)) for t in langchain_kb_tools()}
    assert "search_project_kb" in names
    assert "list_project_paths" in names
    assert "list_bid_chunks" in names
    assert "read_chunks" in names
    assert "read_chunk_window" in names
    assert "read_project_file" in names
    assert "mcp_loader" not in names
    assert search_project_kb.__doc__


@pytest.mark.asyncio
async def test_mcp_adapter_lists_in_process_kb_tools():
    from ai_brain.core.kb.api.mcp_tools import mcp_kb_tools_context

    async with mcp_kb_tools_context() as tools:
        names = {getattr(t, "name", "") for t in tools}
        assert "search_project_kb" in names
        assert "list_bid_chunks" in names
        assert "read_chunks" in names
        assert "read_chunk_window" in names
        assert "read_project_file" in names
        assert "mcp_loader" not in names


def test_bundle_from_result_reads_structured_response():
    from ai_brain.core.kb.build.pipeline import bundle_from_result
    from ai_brain.core.kb.api.schemas import VendorEvidenceBundle

    bundle = bundle_from_result(
        {"structured_response": {"bid_id": "kpmg", "items": []}},
        "kpmg",
    )
    assert isinstance(bundle, VendorEvidenceBundle)
    assert bundle.bid_id == "kpmg"


def test_bundle_from_result_reads_tool_call_args():
    from langchain_core.messages import AIMessage, HumanMessage

    from ai_brain.core.kb.build.pipeline import bundle_from_result

    result = {
        "messages": [
            HumanMessage(content="analyse kpmg"),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "VendorEvidenceBundle",
                        "id": "1",
                        "args": {"bid_id": "kpmg", "items": []},
                    }
                ],
            ),
        ]
    }
    bundle = bundle_from_result(result, "kpmg")
    assert bundle.bid_id == "kpmg"
    assert bundle.items == []


@pytest.mark.asyncio
async def test_extract_requirements_seeds_swift(db_env):
    from ai_brain.core.kb.build.pipeline import extract_requirements
    from ai_brain.core.kb.store.persist import requirement_ids

    _seed_project()
    out = await extract_requirements({"project_id": "p1"})
    assert out["requirements_ready"] is True
    ids = requirement_ids("p1")
    assert "R01" in ids and "R40" in ids
    assert len(ids) >= 40


def test_kb_build_capability_routes_to_extract_requirements():
    from ai_brain.core.procurement_ai.procura_graph import after_start

    assert (
        after_start(
            {
                "request": "",
                "project_id": "p1",
                "capability": "kb_build",
                "procurement": {},
                "messages": [],
            }
        )
        == "extract_requirements"
    )


def test_analyze_bid_is_async_for_send_timeout():
    import inspect

    from ai_brain.core.kb.build.pipeline import analyze_bid

    assert inspect.iscoroutinefunction(analyze_bid)


@pytest.mark.asyncio
async def test_kb_build_ainvoke_accepts_analyze_bid_timeout(db_env, tmp_path, monkeypatch):
    """Regression: Send(..., timeout=) requires an async analyze_bid + graph.ainvoke."""
    from ai_brain.core.kb.build import pipeline
    from ai_brain.core.kb.extract.runner import arun_kb_build
    from ai_brain.core.kb.api.schemas import VendorEvidenceBundle
    from ai_brain.core.procurement_ai.packs.store import read_status

    monkeypatch.setenv("MATE_PROJECTS_DATA_ROOT", str(tmp_path))
    _seed_project()

    async def fake_invoke(project_id, bid_id, config=None):
        return VendorEvidenceBundle(bid_id=bid_id, items=[]), None, 0, None

    monkeypatch.setattr(pipeline, "invoke_vendor_analyst", fake_invoke)
    out = await arun_kb_build("p1", write_xlsx=False)
    audit = (out["state"].get("procurement") or {}).get("kb_audit") or {}
    assert audit.get("bundle_count", 0) >= 1
    job = read_status("p1").get("kb") or {}
    assert job.get("status") in {"ready", "needs_review", "staged"}


def test_child_runnable_config_strips_parent_checkpointer():
    from ai_brain.server.tracing import child_runnable_config, is_checkpoint_sync_error

    bomb = object()
    out = child_runnable_config(
        {
            "checkpointer": bomb,
            "configurable": {
                "thread_id": "t1",
                "checkpoint_id": "ck-1",
                "checkpoint_ns": "ns",
                "user_id": "u1",
            },
            "callbacks": [],
        }
    )
    assert "checkpointer" not in out
    cfg = out.get("configurable") or {}
    assert cfg.get("thread_id") == "t1"
    assert cfg.get("user_id") == "u1"
    assert "checkpoint_id" not in cfg
    assert "checkpoint_ns" not in cfg
    assert out.get("callbacks")
    err = RuntimeError(
        "Synchronous calls to AsyncSqliteSaver are only allowed from a "
        "different thread."
    )
    assert is_checkpoint_sync_error(err)
    assert not is_checkpoint_sync_error(ValueError("no bundle"))


def test_child_runnable_config_accepts_async_callback_manager():
    from mlflow.langchain.langchain_tracer import MlflowLangchainTracer

    from ai_brain.server.tracing import child_runnable_config

    existing = object()

    class AsyncCallbackManager:
        def __init__(self):
            self.handlers = [existing]
            self.inheritable_handlers = [existing]

    out = child_runnable_config({"callbacks": AsyncCallbackManager()})
    assert isinstance(out["callbacks"], list)
    assert existing in out["callbacks"]
    assert any(isinstance(cb, MlflowLangchainTracer) for cb in out["callbacks"])


def test_child_runnable_config_does_not_duplicate_manager_mlflow_tracer():
    from mlflow.langchain.langchain_tracer import MlflowLangchainTracer

    from ai_brain.server.tracing import child_runnable_config

    tracer = MlflowLangchainTracer(run_inline=True)

    class AsyncCallbackManager:
        def __init__(self):
            self.handlers = [tracer]
            self.inheritable_handlers = [tracer]

    out = child_runnable_config({"callbacks": AsyncCallbackManager()})
    tracers = [cb for cb in out["callbacks"] if isinstance(cb, MlflowLangchainTracer)]
    assert tracers == [tracer]


@pytest.mark.asyncio
async def test_invoke_vendor_analyst_uses_research_transcript_fallback(db_env, monkeypatch):
    from contextlib import asynccontextmanager

    from langchain_core.messages import AIMessage, HumanMessage

    from ai_brain.core.kb.extract import agents
    from ai_brain.core.kb.build import pipeline
    from ai_brain.core.kb.api import mcp_tools
    from ai_brain.core.kb.api.schemas import VendorEvidenceBundle

    _seed_project()
    seen: dict[str, list] = {}

    @asynccontextmanager
    async def fake_tools():
        yield []

    monkeypatch.setattr(mcp_tools, "mcp_kb_tools_context", fake_tools)

    class _Research:
        async def ainvoke(self, _payload, config=None):
            assert "checkpointer" not in (config or {})
            return {
                "messages": [
                    HumanMessage(content="analyse kpmg"),
                    AIMessage(content="PwC year-1 fee 13410"),
                ]
            }

    class _Emit:
        async def ainvoke(self, _payload, config=None):
            return {"messages": [HumanMessage(content="analyse kpmg")]}

    monkeypatch.setattr(agents, "build_vendor_analyst", lambda **_k: _Research())
    monkeypatch.setattr(agents, "build_vendor_emit", lambda **_k: _Emit())
    monkeypatch.setattr(agents, "build_pricing_extractor", lambda **_k: _Emit())
    monkeypatch.setattr(agents, "build_profile_extractor", lambda **_k: _Emit())

    async def fake_fallback(schema, messages, bid_id):
        seen["messages"] = list(messages)
        return VendorEvidenceBundle(bid_id=bid_id, items=[])

    monkeypatch.setattr(pipeline, "_structured_fallback", fake_fallback)
    bundle, pricing, _n, profile = await pipeline.invoke_vendor_analyst("p1", "kpmg")
    assert bundle.bid_id == "kpmg"
    blob = " ".join(
        str(getattr(msg, "content", msg)) for msg in seen.get("messages") or []
    )
    assert "13410" in blob


@pytest.mark.asyncio
async def test_analyze_bid_extraction_failed_makes_source_warm(db_env, monkeypatch):
    from ai_brain.core.kb.build import pipeline
    from ai_brain.core.kb.store.persist import seed_swift_requirements
    from ai_brain.core.procurement_ai.packs.matrix_from_evidence import load_matrix_source

    _seed_project()
    seed_swift_requirements("p1")

    async def boom(project_id, bid_id, config=None):
        raise ValueError("vendor_analyst returned no VendorEvidenceBundle")

    monkeypatch.setattr(pipeline, "invoke_vendor_analyst", boom)
    out = await pipeline.analyze_bid({"project_id": "p1", "bid_id": "trifinance-inetum"})
    assert out["kb_bundles"][0]["status"] == "extraction_failed"
    source = load_matrix_source("p1")
    assert source.warm
    cell = source.cells.get(("R01", "trifinance-inetum"))
    assert cell is not None
    assert cell.status == "extraction_failed"


@pytest.mark.asyncio
async def test_analyze_bid_keeps_evidence_if_pricing_persist_fails(db_env, monkeypatch):
    from ai_brain.core.kb.build import pipeline
    from ai_brain.core.kb.store.persist import seed_swift_requirements
    from ai_brain.core.kb.api.schemas import (
        EvidenceItem,
        PricingExtraction,
        PricingLineItem,
        VendorEvidenceBundle,
    )
    from ai_brain.core.procurement_ai.packs.matrix_from_evidence import load_matrix_source

    _seed_project()
    seed_swift_requirements("p1")

    async def fake_invoke(project_id, bid_id, config=None):
        bundle = VendorEvidenceBundle(
            bid_id=bid_id,
            items=[
                EvidenceItem(
                    requirement_id="R01",
                    status="met",
                    claim_text="Inetum will prepare the questionnaires.",
                    artifact_id="art-ok",
                    page=1,
                    chunk_id=None,
                    confidence=0.9,
                )
            ],
        )
        pricing = PricingExtraction(
            bid_id=bid_id,
            lines=[
                PricingLineItem(
                    offer_type="fixed_price",
                    role="CSP assessment",
                    line_total=12000,
                )
            ],
        )
        return bundle, pricing, 1, None

    def boom_pricing(*_a, **_k):
        raise TypeError("'extracted_at' is an invalid keyword argument for PricingLine")

    monkeypatch.setattr(pipeline, "invoke_vendor_analyst", fake_invoke)
    monkeypatch.setattr(pipeline, "upsert_pricing", boom_pricing)
    out = await pipeline.analyze_bid({"project_id": "p1", "bid_id": "trifinance-inetum"})
    bundle = out["kb_bundles"][0]
    assert bundle["status"] == "ok"
    assert bundle["pricing_lines"] == 0
    source = load_matrix_source("p1")
    cell = source.cells.get(("R01", "trifinance-inetum"))
    assert cell is not None
    assert cell.status == "met"


@pytest.mark.asyncio
async def test_nested_ainvoke_does_not_call_async_sqlite_sync_methods():
    import inspect

    from langchain_core.language_models.fake_chat_models import FakeListChatModel

    from ai_brain.core.kb.extract.agents import build_vendor_analyst
    from ai_brain.core.procurement_ai.packs import matrix_extract
    from ai_brain.server.tracing import child_runnable_config

    src = inspect.getsource(matrix_extract)
    assert "agent.invoke(" not in src
    assert inspect.iscoroutinefunction(matrix_extract.extract_matrix)

    class _SyncBomb:
        def get(self, *args, **kwargs):
            raise RuntimeError(
                "Synchronous calls to AsyncSqliteSaver are only allowed from a "
                "different thread."
            )

        def put(self, *args, **kwargs):
            raise RuntimeError(
                "Synchronous calls to AsyncSqliteSaver are only allowed from a "
                "different thread."
            )

    fake = FakeListChatModel(responses=["ok"])
    agent = build_vendor_analyst(model=fake, fallback_model=fake, tools=[])
    nested = child_runnable_config(
        {
            "checkpointer": _SyncBomb(),
            "configurable": {"thread_id": "t-nested", "checkpoint_id": "ck"},
        }
    )
    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": "research only"}]},
        config=nested,
    )
    assert isinstance(result, dict)
    assert "messages" in result
