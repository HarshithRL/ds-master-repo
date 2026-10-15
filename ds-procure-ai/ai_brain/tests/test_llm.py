from __future__ import annotations

import base64
import json
from types import SimpleNamespace

import pytest

from ai_brain.core.config import llm as llm_mod
from ai_brain.core.config.llm import get_fast_model_name, get_thinking_model_name
from ai_brain.core.config.memory import get_memory_settings


def _jwt(*scopes: str) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').decode().rstrip("=")
    payload = (
        base64.urlsafe_b64encode(json.dumps({"scope": " ".join(scopes)}).encode())
        .decode()
        .rstrip("=")
    )
    return f"{header}.{payload}.sig"


def _install_llm_fakes(monkeypatch):
    captured: dict = {}

    def fake_chat(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(kwargs=kwargs)

    def fake_ws(**kwargs):
        token = kwargs.get("token") or "sp"
        return SimpleNamespace(
            kwargs=kwargs,
            config=SimpleNamespace(
                host=kwargs.get("host"),
                authenticate=lambda: {"Authorization": f"Bearer {token}"},
            ),
        )

    monkeypatch.setenv("DATABRICKS_APP_NAME", "ds-procure-ai")
    monkeypatch.setenv("DATABRICKS_HOST", "https://adb.example.net")
    monkeypatch.setenv("DATABRICKS_CLIENT_ID", "app-sp")
    monkeypatch.setenv("DATABRICKS_CLIENT_SECRET", "app-secret")
    monkeypatch.setenv("MATE_UC_CATALOG", "automation_d")
    monkeypatch.setattr("ai_brain.core.config.llm.ChatDatabricks", fake_chat)
    monkeypatch.setattr("shared.databricks_runtime.WorkspaceClient", fake_ws)
    return captured


@pytest.fixture(autouse=True)
def _clear_model_cache():
    llm_mod._load_model_names.cache_clear()
    yield
    llm_mod._load_model_names.cache_clear()


def test_configured_models_use_catalog_gateway(monkeypatch):
    monkeypatch.setenv("MATE_UC_CATALOG", "automation_d")
    assert get_fast_model_name() == "automation_d.ai_models.gw_dev_claude-sonnet-4-6_aut"
    assert get_thinking_model_name() == "automation_d.ai_models.gw_dev_gpt-5_aut"


def test_catalog_prefix_follows_acceptance(monkeypatch):
    monkeypatch.setenv("MATE_UC_CATALOG", "automation_a")
    assert get_fast_model_name() == "automation_a.ai_models.gw_acc_claude-sonnet-4-6_aut"
    assert get_thinking_model_name() == "automation_a.ai_models.gw_acc_gpt-5_aut"


def test_env_fqn_overrides_yaml(monkeypatch):
    monkeypatch.setenv("MATE_UC_CATALOG", "automation_d")
    fast = "automation_d.ai_models.gw_dev_claude-sonnet-4-6_aut"
    thinking = "automation_d.ai_models.gw_dev_gpt-5_aut"
    monkeypatch.setenv("DATABRICKS_FAST_MODEL", fast)
    monkeypatch.setenv("DATABRICKS_THINKING_MODEL", thinking)
    assert get_fast_model_name() == fast
    assert get_thinking_model_name() == thinking


def test_catalog_gateway_env_is_used(monkeypatch):
    monkeypatch.setenv("MATE_UC_CATALOG", "automation_d")
    stale = "automation_d.ai_models.gw_dev_claude-sonnet-4-6_aut"
    monkeypatch.setenv("DATABRICKS_MODEL", stale)
    monkeypatch.setenv("DATABRICKS_FAST_MODEL", stale)
    monkeypatch.setenv("DATABRICKS_THINKING_MODEL", stale)
    assert get_fast_model_name() == stale
    assert get_thinking_model_name() == stale


def test_system_ai_env_is_ignored(monkeypatch):
    monkeypatch.setenv("MATE_UC_CATALOG", "automation_d")
    monkeypatch.setenv("DATABRICKS_FAST_MODEL", "system.ai.databricks-claude-sonnet-4-5")
    monkeypatch.setenv("DATABRICKS_THINKING_MODEL", "system.ai.databricks-claude-opus-4-6")
    assert get_fast_model_name() == "automation_d.ai_models.gw_dev_claude-sonnet-4-6_aut"
    assert get_thinking_model_name() == "automation_d.ai_models.gw_dev_gpt-5_aut"


def test_get_llm_uses_obo_gateway_catalog_fqn(monkeypatch):
    captured = _install_llm_fakes(monkeypatch)
    token = _jwt("ai-gateway", "model-serving")
    from shared.databricks_runtime import (
        RequestScopedWorkspaceClient,
        bind_obo_from_headers,
        clear_obo,
        request_workspace_client,
    )

    bind_obo_from_headers({"x-forwarded-access-token": token})
    try:
        from ai_brain.core.config.llm import get_llm

        get_llm("fast")
        client = captured["workspace_client"]
        assert isinstance(client, RequestScopedWorkspaceClient)
        assert client.config.authenticate()["Authorization"] == f"Bearer {token}"
        minted = getattr(request_workspace_client(), "kwargs", {})
        assert minted.get("auth_type") == "pat"
        assert minted.get("token") == token
        assert minted.get("client_id") != "app-sp"
        assert captured.get("use_ai_gateway") is True
        assert captured.get("model") == "automation_d.ai_models.gw_dev_claude-sonnet-4-6_aut"
    finally:
        clear_obo()


def test_get_llm_rejects_obo_without_gateway_scope(monkeypatch):
    _install_llm_fakes(monkeypatch)
    from shared.databricks_runtime import bind_obo_from_headers, clear_obo

    bind_obo_from_headers({"x-forwarded-access-token": _jwt("postgres")})
    try:
        from ai_brain.core.config.llm import get_llm

        with pytest.raises(RuntimeError, match="ai-gateway"):
            get_llm("fast")
    finally:
        clear_obo()


def test_get_llm_local_without_obo_still_uses_gateway(monkeypatch):
    captured = _install_llm_fakes(monkeypatch)
    from shared.databricks_runtime import clear_obo

    clear_obo()
    from ai_brain.core.config.llm import get_llm

    get_llm("thinking")
    assert captured.get("use_ai_gateway") is True
    assert captured.get("model") == "automation_d.ai_models.gw_dev_gpt-5_aut"
    minted = getattr(captured["workspace_client"], "kwargs", {})
    assert minted.get("client_id") == "app-sp"


def test_embedding_endpoint_stays_workspace_gte(monkeypatch):
    monkeypatch.delenv("DATABRICKS_EMBEDDING_ENDPOINT", raising=False)
    get_memory_settings.cache_clear()
    try:
        assert get_memory_settings().embedding_endpoint == "databricks-gte-large-en"
    finally:
        get_memory_settings.cache_clear()
