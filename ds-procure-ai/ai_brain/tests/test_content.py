"""Tests for splitting answer vs reasoning content."""

from __future__ import annotations

from ai_brain.core.utils.content import content_text, split_content_kinds, split_message_kinds


def test_content_text_skips_reasoning_blocks():
    content = [
        {"type": "reasoning", "text": "let me think"},
        {"type": "text", "text": "Hello"},
    ]
    assert content_text(content) == "Hello"
    answer, thought = split_content_kinds(content)
    assert answer == "Hello"
    assert thought == "let me think"


def test_split_message_kinds_additional_kwargs():
    answer, thought = split_message_kinds(
        {
            "content": "Visible",
            "additional_kwargs": {"reasoning_content": "hidden"},
        }
    )
    assert answer == "Visible"
    assert thought == "hidden"


def test_split_json_reasoning_string():
    raw = '[{"type": "reasoning", "text": "plan"}]'
    answer, thought = split_content_kinds(raw)
    assert answer == ""
    assert "reasoning" in thought
