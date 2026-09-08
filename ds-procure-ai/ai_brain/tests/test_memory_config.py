"""Unit tests for memory.yaml load, env overlay, and search_path options."""

from __future__ import annotations

from ai_brain.core.config.memory import get_memory_settings, search_path_options

_MEMORY_ENV = (
    "BRAIN_CHECKPOINT_BACKEND",
    "BRAIN_STORE_BACKEND",
    "LAKEBASE_ENDPOINT",
    "LAKEBASE_SCHEMA",
    "PGDATABASE",
    "PGHOST",
    "PGSSLMODE",
    "BRAIN_POOL_RECYCLE_SECONDS",
    "BRAIN_TOKEN_REFRESH_SECONDS",
    "DATABRICKS_CONFIG_PROFILE",
    "DATABRICKS_EMBEDDING_ENDPOINT",
    "DATABRICKS_EMBEDDING_DIMS",
)


def _clear_overlay(monkeypatch) -> None:
    for name in _MEMORY_ENV:
        monkeypatch.delenv(name, raising=False)


def test_yaml_defaults_when_env_unset(monkeypatch):
    _clear_overlay(monkeypatch)
    settings = get_memory_settings()
    assert settings.checkpoint_backend == "lakebase"
    assert settings.store_backend == "lakebase"
    assert settings.lakebase_schema == "mate_agent"
    assert settings.lakebase_database == "databricks_postgres"
    assert settings.lakebase_host == ""
    assert settings.sslmode == "require"
    assert settings.pool_recycle_seconds == 3000
    assert settings.token_refresh_seconds == 2400
    assert settings.config_profile == "adb-7181820732839861"
    assert settings.embedding_endpoint == "databricks-gte-large-en"
    assert settings.embedding_dims == 1024
    assert "ds-vendor-agent" in settings.lakebase_endpoint
    assert settings.lakebase_endpoint.endswith("/endpoints/primary")


def test_env_overrides_yaml(monkeypatch):
    _clear_overlay(monkeypatch)
    monkeypatch.setenv("BRAIN_CHECKPOINT_BACKEND", "sqlite")
    monkeypatch.setenv("BRAIN_STORE_BACKEND", "memory")
    monkeypatch.setenv("LAKEBASE_SCHEMA", "custom_schema")
    monkeypatch.setenv("PGDATABASE", "other_db")
    monkeypatch.setenv("PGHOST", "example.db.host")
    monkeypatch.setenv("PGSSLMODE", "verify-full")
    monkeypatch.setenv("BRAIN_POOL_RECYCLE_SECONDS", "100")
    monkeypatch.setenv("BRAIN_TOKEN_REFRESH_SECONDS", "90")
    monkeypatch.setenv("DATABRICKS_CONFIG_PROFILE", "other-profile")
    monkeypatch.setenv("DATABRICKS_EMBEDDING_ENDPOINT", "system.ai.other")
    monkeypatch.setenv("DATABRICKS_EMBEDDING_DIMS", "512")
    monkeypatch.setenv("LAKEBASE_ENDPOINT", "projects/x/branches/y/endpoints/z")

    settings = get_memory_settings()
    assert settings.checkpoint_backend == "sqlite"
    assert settings.store_backend == "memory"
    assert settings.lakebase_schema == "custom_schema"
    assert settings.lakebase_database == "other_db"
    assert settings.lakebase_host == "example.db.host"
    assert settings.sslmode == "verify-full"
    assert settings.pool_recycle_seconds == 100
    assert settings.token_refresh_seconds == 90
    assert settings.config_profile == "other-profile"
    assert settings.embedding_endpoint == "system.ai.other"
    assert settings.embedding_dims == 512
    assert settings.lakebase_endpoint == "projects/x/branches/y/endpoints/z"
    assert search_path_options() == "-csearch_path=custom_schema"


def test_search_path_options_mate_agent():
    assert search_path_options("mate_agent") == "-csearch_path=mate_agent"
    assert search_path_options("  mate_agent  ") == "-csearch_path=mate_agent"


def test_search_path_options_uses_settings_schema(monkeypatch):
    _clear_overlay(monkeypatch)
    monkeypatch.setenv("LAKEBASE_SCHEMA", "mate_agent")
    assert search_path_options() == "-csearch_path=mate_agent"


def test_conninfo_skips_startup_options_on_pooler():
    from ai_brain.server.lakebase import _conninfo, host_from_endpoint_status, is_pooler_host

    pooler = "ep-delicate-violet-e267idel-pooler.database.westeurope.azuredatabricks.net"
    assert is_pooler_host(pooler)
    pooled = _conninfo(
        host=pooler,
        dbname="databricks_postgres",
        user="u",
        sslmode="require",
        schema="mate_agent",
    )
    assert "options=" not in pooled
    direct = _conninfo(
        host="ep-delicate-violet-e267idel.database.westeurope.azuredatabricks.net",
        dbname="databricks_postgres",
        user="u",
        sslmode="require",
        schema="mate_agent",
    )
    assert "options=-csearch_path=mate_agent" in direct

    emailed = _conninfo(
        host="db.example.net",
        dbname="databricks_postgres",
        user="alice@etex.com",
        sslmode="require",
        schema="mate_agent",
    )
    assert "user='alice@etex.com'" in emailed

    from types import SimpleNamespace

    endpoint = SimpleNamespace(
        status=SimpleNamespace(
            hosts=SimpleNamespace(
                host="ep-direct.example.net",
                read_write_pooled_host=pooler,
            )
        )
    )
    assert host_from_endpoint_status(endpoint) == "ep-direct.example.net"


def test_apply_search_path_does_not_fall_back_to_public():
    import inspect

    from ai_brain.server.lakebase import apply_search_path

    source = inspect.getsource(apply_search_path)
    assert "SET search_path TO {}" in source
    assert "public" not in source
