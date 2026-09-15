"""Unit tests for MCP tool content sanitizer and nested runnable config."""

from __future__ import annotations

from types import SimpleNamespace

from langchain_core.messages import ToolMessage

from ai_brain.core.kb.middleware.strip_tool_content_ids import (
    StripToolContentIdsMiddleware,
    strip_content_block_ids,
)
from ai_brain.server.tracing import child_runnable_config


def test_strip_content_block_ids_removes_id_from_list_dicts():
    content = [
        {"type": "text", "text": "hello", "id": "lc_abc"},
        {"type": "text", "text": "world"},
    ]
    cleaned = strip_content_block_ids(content)
    assert cleaned == [
        {"type": "text", "text": "hello"},
        {"type": "text", "text": "world"},
    ]
    assert "id" not in cleaned[0]


def test_strip_content_block_ids_leaves_string_alone():
    assert strip_content_block_ids("plain tool output") == "plain tool output"
    assert strip_content_block_ids(None) is None


def test_strip_content_block_ids_model_dump_objects():
    class Block:
        def __init__(self):
            self.type = "text"
            self.text = "via dump"
            self.id = "lc_obj"

        def model_dump(self):
            return {"type": self.type, "text": self.text, "id": self.id}

    cleaned = strip_content_block_ids([Block()])
    assert cleaned == [{"type": "text", "text": "via dump"}]


def test_strip_middleware_sanitizes_tool_message():
    mw = StripToolContentIdsMiddleware()

    def handler(_request):
        return ToolMessage(
            content=[{"type": "text", "text": "ok", "id": "lc_1"}],
            tool_call_id="call-1",
        )

    result = mw.wrap_tool_call(SimpleNamespace(tool_call={"name": "t"}), handler)
    assert isinstance(result, ToolMessage)
    assert result.content == [{"type": "text", "text": "ok"}]


def test_child_runnable_config_always_has_checkpoint_ns():
    out = child_runnable_config(
        {
            "configurable": {
                "thread_id": "t1",
                "checkpoint_id": "ck-1",
                "checkpoint_ns": "parent",
                "checkpoint_map": {"a": 1},
                "__pregel_checkpointer": object(),
            },
            "callbacks": [],
        }
    )
    cfg = out["configurable"]
    assert "checkpoint_ns" in cfg
    assert cfg["checkpoint_ns"] == "nested"
    assert cfg.get("thread_id") == "t1"
    assert "checkpoint_id" not in cfg
    assert "checkpoint_map" not in cfg
    assert "__pregel_checkpointer" not in cfg

    empty = child_runnable_config(None)
    assert "checkpoint_ns" in (empty.get("configurable") or {})
    assert empty["configurable"]["checkpoint_ns"] == "nested"

def test_compare_xlsx_surfaces_agent_failure(tmp_path, monkeypatch):
    """Agent exceptions become failed status + clear assistant_reply, not silent template."""
    import asyncio

    monkeypatch.setenv("MATE_PROJECTS_DATA_ROOT", str(tmp_path))
    from ai_brain.core.procurement_ai.subagents import compare_xlsx as compare_mod

    class _Project:
        id = "proj-fail"
        code = "PR-FAIL"
        name = "Fail project"
        business_process = "Indirect"
        category = "SWIFT CSCF"
        description = "services"

    class _Artifact:
        id = "a1"
        original_name = "BDO.pdf"
        parse_status = "ok"

    async def fake_parse(_pid):
        return None

    async def boom(_pid, insights, config=None):
        raise RuntimeError("checkpoint_ns")

    monkeypatch.setattr(compare_mod, "_ensure_corpus", fake_parse)
    monkeypatch.setattr(compare_mod, "load_context", lambda _pid: (_Project(), [_Artifact()], []))
    monkeypatch.setattr(
        compare_mod,
        "build_insight_payload",
        lambda *a, **k: {
            "process_type": "indirect_it_services",
            "vendors": [{"name": "BDO"}],
            "decision": {},
        },
    )
    monkeypatch.setattr(
        "ai_brain.core.kb.build.pipeline.ensure_vendor_bids",
        lambda _pid: ["bdo"],
    )
    monkeypatch.setattr(
        "ai_brain.core.procurement_ai.subagents.comparison_matrix.extract_comparison_matrix",
        boom,
    )

    out = asyncio.run(compare_mod.compare_xlsx({"project_id": "proj-fail", "procurement": {}}))
    proc = out["procurement"]
    assert proc["xlsx_status"] == "failed"
    assert "Comparison agent failed" in proc["assistant_reply"]
    assert "checkpoint_ns" in proc["assistant_reply"]
    assert proc["evidence_used"] is False

