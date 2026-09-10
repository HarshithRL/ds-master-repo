"""DatabricksEmbeddings must not inject a CLI profile in the Apps runtime."""

from __future__ import annotations

import os
from types import SimpleNamespace

from ai_brain.server.checkpointer import _embeddings


def test_embeddings_does_not_set_cli_profile_in_app(monkeypatch):
    monkeypatch.setenv("DATABRICKS_APP_NAME", "ds-procure-ai")
    monkeypatch.delenv("DATABRICKS_CONFIG_PROFILE", raising=False)
    monkeypatch.setattr(
        "databricks_langchain.DatabricksEmbeddings",
        lambda **kwargs: SimpleNamespace(kwargs=kwargs),
        raising=False,
    )
    settings = SimpleNamespace(
        embedding_endpoint="databricks-gte-large-en",
        config_profile="adb-7181820732839861",
    )
    _embeddings(settings)
    assert "DATABRICKS_CONFIG_PROFILE" not in os.environ


def test_embeddings_sets_cli_profile_locally(monkeypatch):
    monkeypatch.delenv("DATABRICKS_APP_NAME", raising=False)
    monkeypatch.delenv("DATABRICKS_CLIENT_ID", raising=False)
    monkeypatch.delenv("DATABRICKS_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("DATABRICKS_CONFIG_PROFILE", raising=False)
    monkeypatch.setattr(
        "databricks_langchain.DatabricksEmbeddings",
        lambda **kwargs: SimpleNamespace(kwargs=kwargs),
        raising=False,
    )
    settings = SimpleNamespace(
        embedding_endpoint="databricks-gte-large-en",
        config_profile="adb-7181820732839861",
    )
    _embeddings(settings)
    assert os.environ["DATABRICKS_CONFIG_PROFILE"] == "adb-7181820732839861"


def test_embeddings_does_not_set_cli_profile_in_app(monkeypatch):
    monkeypatch.setenv("DATABRICKS_APP_NAME", "ds-procure-ai")
    monkeypatch.delenv("DATABRICKS_CONFIG_PROFILE", raising=False)

    def fake_embeddings(**kwargs):
        return SimpleNamespace(kwargs=kwargs)

    monkeypatch.setattr(
        "databricks_langchain.DatabricksEmbeddings",
        fake_embeddings,
        raising=False,
    )
    settings = SimpleNamespace(
        embedding_endpoint="databricks-gte-large-en",
        config_profile="adb-7181820732839861",
    )
    _embeddings(settings)
    assert "DATABRICKS_CONFIG_PROFILE" not in __import__("os").environ


def test_embeddings_sets_cli_profile_locally(monkeypatch):
    monkeypatch.delenv("DATABRICKS_APP_NAME", raising=False)
    monkeypatch.delenv("DATABRICKS_CLIENT_ID", raising=False)
    monkeypatch.delenv("DATABRICKS_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("DATABRICKS_CONFIG_PROFILE", raising=False)
    monkeypatch.setattr(
        "databricks_langchain.DatabricksEmbeddings",
        lambda **kwargs: SimpleNamespace(kwargs=kwargs),
        raising=False,
    )
    settings = SimpleNamespace(
        embedding_endpoint="databricks-gte-large-en",
        config_profile="adb-7181820732839861",
    )
    _embeddings(settings)
    assert __import__("os").environ["DATABRICKS_CONFIG_PROFILE"] == "adb-7181820732839861"


def test_embeddings_use_request_scoped_workspace_client(monkeypatch):
    captured: dict = {}

    class FakeEmbeddings:
        model_fields = {"workspace_client": True, "endpoint": True}

        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.delenv("DATABRICKS_APP_NAME", raising=False)
    monkeypatch.delenv("DATABRICKS_CLIENT_ID", raising=False)
    monkeypatch.delenv("DATABRICKS_CLIENT_SECRET", raising=False)
    monkeypatch.setattr("databricks_langchain.DatabricksEmbeddings", FakeEmbeddings)
    settings = SimpleNamespace(
        embedding_endpoint="databricks-gte-large-en",
        config_profile="adb-7181820732839861",
    )
    _embeddings(settings)
    from shared.databricks_runtime import RequestScopedWorkspaceClient

    assert isinstance(captured.get("workspace_client"), RequestScopedWorkspaceClient)
