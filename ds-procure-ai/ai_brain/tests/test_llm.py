from __future__ import annotations

import pytest

from ai_brain.core.config import llm as llm_mod
from ai_brain.core.config.llm import get_fast_model_name, get_thinking_model_name


@pytest.fixture(autouse=True)
def _clear_model_cache():
    llm_mod._load_model_names.cache_clear()
    yield
    llm_mod._load_model_names.cache_clear()


def test_configured_models_use_automation_gateway():
    expected = "automation_d.ai_models.gw_dev_claude-sonnet-4-6_aut"
    assert get_fast_model_name() == expected
    assert get_thinking_model_name() == expected


def test_env_overrides_use_acc_gateway(monkeypatch):
    acc = "automation_a.ai_models.gw_dev_claude-sonnet-4-6_aut"
    monkeypatch.setenv("DATABRICKS_FAST_MODEL", acc)
    monkeypatch.setenv("DATABRICKS_THINKING_MODEL", acc)
    assert get_fast_model_name() == acc
    assert get_thinking_model_name() == acc
