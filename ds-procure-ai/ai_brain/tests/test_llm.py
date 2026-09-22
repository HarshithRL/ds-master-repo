from __future__ import annotations

import base64
import json
from types import SimpleNamespace

import pytest

from ai_brain.core.config import llm as llm_mod
from ai_brain.core.config.llm import get_fast_model_name, get_thinking_model_name


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
    monkeypatch.setattr("ai_brain.core.config.llm.ChatDatabricks", fake_chat)
    monkeypatch.setattr("shared.databricks_runtime.WorkspaceClient", fake_ws)
    return captured


@pytest.fixture(autouse=True)
def _clear_model_cache():
    llm_mod._load_model_names.cache_clear()
    yield
    llm_mod._load_model_names.cache_clear()


def test_configured_models_use_system_ai_foundation():
    assert get_fast_model_name() == "system.ai.databricks-claude-sonnet-4-5"
    assert get_thinking_model_name() == "system.ai.databricks-claude-opus-4-6"


def test_env_overrides_use_opus_fallback(monkeypatch):
    fallback = "system.ai.databricks-claude-opus-4-5"
    monkeypatch.setenv("DATABRICKS_FAST_MODEL", fallback)
    monkeypatch.setenv("DATABRICKS_THINKING_MODEL", fallback)
    assert get_fast_model_name() == fallback
    assert get_thinking_model_name() == fallback


def test_retired_gateway_env_falls_back_to_llm_yaml(monkeypatch):
    stale = "automation_d.ai_models.gw_dev_claude-sonnet-4-6_aut"
    monkeypatch.setenv("DATABRICKS_MODEL", stale)
    monkeypatch.setenv("DATABRICKS_FAST_MODEL", stale)
    monkeypatch.setenv("DATABRICKS_THINKING_MODEL", stale)
    assert get_fast_model_name() == "system.ai.databricks-claude-sonnet-4-5"
    assert get_thinking_model_name() == "system.ai.databricks-claude-opus-4-6"


def test_gateway_scope_no_longer_switches_model_path(monkeypatch):
    """ai-gateway in the token must not route the visitor to system.ai.*."""
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
        assert captured.get("use_ai_gateway") is False
        assert captured.get("model") == "databricks-claude-sonnet-4-5"
    finally:
        clear_obo()


def test_get_llm_falls_back_to_serving_endpoint_without_gateway_scope(monkeypatch):
    captured = _install_llm_fakes(monkeypatch)
    from shared.databricks_runtime import bind_obo_from_headers, clear_obo

    bind_obo_from_headers({"x-forwarded-access-token": _jwt("postgres")})
    try:
        from ai_brain.core.config.llm import get_llm

        get_llm("fast")
        client = captured["workspace_client"]
        minted = getattr(client, "kwargs", {})
        assert minted.get("auth_type") == "oauth-m2m"
        assert minted.get("client_id") == "app-sp"
        assert captured.get("use_ai_gateway") is False
        assert captured.get("model") == "databricks-claude-sonnet-4-5"
    finally:
        clear_obo()


def test_get_llm_uses_obo_for_serving_endpoint_when_model_serving_scope(monkeypatch):
    captured = _install_llm_fakes(monkeypatch)
    token = _jwt("model-serving")
    from shared.databricks_runtime import (
        RequestScopedWorkspaceClient,
        bind_obo_from_headers,
        clear_obo,
    )

    bind_obo_from_headers({"x-forwarded-access-token": token})
    try:
        from ai_brain.core.config.llm import get_llm

        get_llm("fast")
        assert isinstance(captured["workspace_client"], RequestScopedWorkspaceClient)
        assert captured.get("use_ai_gateway") is False
        assert captured.get("model") == "databricks-claude-sonnet-4-5"
    finally:
        clear_obo()

