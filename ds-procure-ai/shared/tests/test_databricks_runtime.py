"""Apps vs local WorkspaceClient construction (no live Databricks calls)."""

from __future__ import annotations

from types import SimpleNamespace

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
