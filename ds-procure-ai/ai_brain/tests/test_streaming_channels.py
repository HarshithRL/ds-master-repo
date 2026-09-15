"""Unit tests for answer vs thought routing in brain streaming."""

from __future__ import annotations

from ai_brain.server.streaming import (
    _business_reply,
    _ns_is_nested,
    _route_message_as_thought,
)


def test_nested_ns_detected():
    assert _ns_is_nested(("procurement:abc", "nested"))
    assert _ns_is_nested(("nested:xyz",))
    assert not _ns_is_nested(("procurement:abc",))
    assert not _ns_is_nested(())


def test_main_agent_stays_answer_channel():
    assert _route_message_as_thought(("procurement:abc",), "main_agent") is False
    assert _route_message_as_thought((), "main_agent") is False
    assert _route_message_as_thought(("procurement:abc",), "deepagent") is False


def test_comparison_and_nested_go_to_thought():
    assert _route_message_as_thought(("nested",), "model") is True
    assert _route_message_as_thought(("procurement:x", "nested:y"), "agent") is True
    assert _route_message_as_thought((), "compare_xlsx") is True
    assert _route_message_as_thought((), "comparison_orchestrator") is True
    assert _route_message_as_thought((), "rfp_analyst") is True
    assert _route_message_as_thought((), "vendor_analyst") is True


def test_business_reply_prefers_assistant_reply_and_href():
    reply = _business_reply(
        {
            "assistant_reply": "Comparison workbook is ready.",
            "xlsx_href": "/api/procurement/projects/p1/packs/xlsx/download",
            "main_agent": "ignore me",
        }
    )
    assert "Comparison workbook is ready." in reply
    assert "/api/procurement/projects/p1/packs/xlsx/download" in reply
    assert "Download:" in reply
    assert "ignore me" not in reply


def test_business_reply_empty_without_assistant_reply():
    assert _business_reply({"main_agent": "hello", "xlsx_href": "/x"}) == ""
