"""Apps vs local WorkspaceClient construction (no live Databricks calls)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from databricks.sdk import WorkspaceClient
from pydantic import BaseModel, ConfigDict, ValidationError

from shared.databricks_runtime import (
    DEFAULT_PROFILE,
    cli_profile,
    is_databricks_app,
    obo_workspace_client,
    prepare_app_environ,
    workspace_client,
)

_APP_ENV = (
    "DATABRICKS_APP_NAME",
    "DATABRICKS_CLIENT_ID",
    "DATABRICKS_CLIENT_SECRET",
    "DATABRICKS_HOST",
    "DATABRICKS_CONFIG_PROFILE",
)


def _clear(monkeypatch) -> None:
    for name in _APP_ENV:
        monkeypatch.delenv(name, raising=False)


def test_is_databricks_app_from_app_name(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("DATABRICKS_APP_NAME", "ds-procure-ai")
    assert is_databricks_app() is True


def test_is_databricks_app_from_m2m_env(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("DATABRICKS_CLIENT_ID", "client")
    monkeypatch.setenv("DATABRICKS_CLIENT_SECRET", "secret")
    assert is_databricks_app() is True


def test_is_databricks_app_false_locally(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("DATABRICKS_CONFIG_PROFILE", "adb-7181820732839861")
    assert is_databricks_app() is False


def test_cli_profile_default_and_override(monkeypatch):
    _clear(monkeypatch)
    assert cli_profile() == DEFAULT_PROFILE
    monkeypatch.setenv("DATABRICKS_CONFIG_PROFILE", "other")
    assert cli_profile() == "other"


def test_prepare_app_environ_strips_profile():
    env = {
        "DATABRICKS_APP_NAME": "ds-procure-ai",
        "DATABRICKS_CONFIG_PROFILE": "adb-7181820732839861",
        "KEEP": "1",
    }
    prepare_app_environ(env)
    assert "DATABRICKS_CONFIG_PROFILE" not in env
    assert env["KEEP"] == "1"


def test_prepare_app_environ_keeps_profile_locally():
    env = {"DATABRICKS_CONFIG_PROFILE": "adb-7181820732839861"}
    prepare_app_environ(env)
    assert env["DATABRICKS_CONFIG_PROFILE"] == "adb-7181820732839861"


def test_workspace_client_apps_uses_oauth_m2m(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("DATABRICKS_APP_NAME", "ds-procure-ai")
    monkeypatch.setenv("DATABRICKS_HOST", "https://adb.example.net")
    monkeypatch.setenv("DATABRICKS_CLIENT_ID", "cid")
    monkeypatch.setenv("DATABRICKS_CLIENT_SECRET", "csecret")
    monkeypatch.setenv("DATABRICKS_CONFIG_PROFILE", "must-not-win")
    captured: dict = {}

    def fake_client(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(config=SimpleNamespace(host=kwargs.get("host")))

    monkeypatch.setattr("shared.databricks_runtime.WorkspaceClient", fake_client)
    workspace_client()
    assert captured["auth_type"] == "oauth-m2m"
    assert captured["host"] == "https://adb.example.net"
    assert captured["client_id"] == "cid"
    assert captured["client_secret"] == "csecret"
    assert "profile" not in captured


def test_workspace_client_local_uses_profile(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("DATABRICKS_CONFIG_PROFILE", "adb-7181820732839861")
    captured: dict = {}

    def fake_client(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace()

    monkeypatch.setattr("shared.databricks_runtime.WorkspaceClient", fake_client)
    workspace_client()
    assert captured == {"profile": "adb-7181820732839861"}


def test_obo_workspace_client_forces_pat(monkeypatch):
    captured: dict = {}

    def fake_client(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace()

    monkeypatch.setattr("shared.databricks_runtime.WorkspaceClient", fake_client)
    obo_workspace_client(host="https://adb.example.net", token="user-obo")
    assert captured == {
        "host": "https://adb.example.net",
        "token": "user-obo",
        "auth_type": "pat",
    }


def test_request_workspace_client_uses_obo_when_bound(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("DATABRICKS_APP_NAME", "ds-procure-ai")
    monkeypatch.setenv("DATABRICKS_HOST", "https://adb.example.net")
    monkeypatch.setenv("DATABRICKS_CLIENT_ID", "cid")
    monkeypatch.setenv("DATABRICKS_CLIENT_SECRET", "csecret")
    captured: dict = {}

    def fake_client(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(config=SimpleNamespace(host=kwargs.get("host")))

    monkeypatch.setattr("shared.databricks_runtime.WorkspaceClient", fake_client)
    from shared.databricks_runtime import bind_obo_from_headers, clear_obo, request_workspace_client

    bind_obo_from_headers({"X-Forwarded-Access-Token": "visitor-token"})
    try:
        request_workspace_client()
        assert captured["auth_type"] == "pat"
        assert captured["token"] == "visitor-token"
        assert captured["host"] == "https://adb.example.net"
    finally:
        clear_obo()


def test_request_workspace_client_falls_back_without_token(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("DATABRICKS_APP_NAME", "ds-procure-ai")
    monkeypatch.setenv("DATABRICKS_HOST", "https://adb.example.net")
    monkeypatch.setenv("DATABRICKS_CLIENT_ID", "cid")
    monkeypatch.setenv("DATABRICKS_CLIENT_SECRET", "csecret")
    captured: dict = {}

    def fake_client(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(config=SimpleNamespace(host=kwargs.get("host")))

    monkeypatch.setattr("shared.databricks_runtime.WorkspaceClient", fake_client)
    from shared.databricks_runtime import clear_obo, request_workspace_client

    clear_obo()
    request_workspace_client()
    assert captured["auth_type"] == "oauth-m2m"
    assert "token" not in captured


def test_request_scoped_client_authenticate_follows_bind(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("DATABRICKS_HOST", "https://adb.example.net")
    captured: list[str] = []

    def fake_client(**kwargs):
        token = kwargs.get("token") or "sp"

        def authenticate():
            captured.append(str(token))
            return {"Authorization": f"Bearer {token}"}

        return SimpleNamespace(
            config=SimpleNamespace(host=kwargs.get("host"), authenticate=authenticate)
        )

    monkeypatch.setattr("shared.databricks_runtime.WorkspaceClient", fake_client)
    from shared.databricks_runtime import (
        RequestScopedWorkspaceClient,
        bind_obo_from_headers,
        clear_obo,
    )

    proxy = RequestScopedWorkspaceClient()
    auth = proxy.config.authenticate
    bind_obo_from_headers({"x-forwarded-access-token": "visitor-a"})
    try:
        assert auth()["Authorization"] == "Bearer visitor-a"
        bind_obo_from_headers({"x-forwarded-access-token": "visitor-b"})
        assert auth()["Authorization"] == "Bearer visitor-b"
    finally:
        clear_obo()
    assert captured == ["visitor-a", "visitor-b"]


def test_request_scoped_client_is_workspace_client_for_pydantic():
    """ChatDatabricks rejects a non-WorkspaceClient with is_instance_of."""
    from shared.databricks_runtime import RequestScopedWorkspaceClient

    class _ChatLike(BaseModel):
        model_config = ConfigDict(arbitrary_types_allowed=True)
        workspace_client: WorkspaceClient

    proxy = RequestScopedWorkspaceClient()
    assert isinstance(proxy, WorkspaceClient)
    _ChatLike(workspace_client=proxy)

    class _NotAClient:
        pass

    with pytest.raises(ValidationError):
        _ChatLike(workspace_client=_NotAClient())
