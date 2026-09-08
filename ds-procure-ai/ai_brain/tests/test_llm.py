from __future__ import annotations

from ai_brain.core.config.llm import get_fast_model_name, get_thinking_model_name


def test_configured_models_use_automation_gateway():
    expected = "automation_d.ai_models.gw_dev_claude-sonnet-4-6_aut"
    assert get_fast_model_name() == expected
    assert get_thinking_model_name() == expected
