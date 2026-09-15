"""UC backend helpers + sqlite init smoke tests."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from shared.db import connection as db_connection
from shared.db.connection import init_db, qualified_table
from shared.db.paths import db_backend, projects_data_root, uc_volume_root
from shared.databricks_runtime import bind_obo_from_headers, clear_obo


def _jwt(*scopes: str) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').decode().rstrip("=")
    payload = (
        base64.urlsafe_b64encode(json.dumps({"scope": " ".join(scopes)}).encode())
        .decode()
        .rstrip("=")
    )
    return f"{header}.{payload}.sig"


@pytest.fixture()
def reset_db_engine():
    db_connection.reset_engine_state()
    yield
    db_connection.reset_engine_state()


def test_sqlite_backend_still_initializes(tmp_path, monkeypatch, reset_db_engine):
    monkeypatch.delenv("MATE_DB_BACKEND", raising=False)
    monkeypatch.setenv("MATE_SQLITE_PATH", str(tmp_path / "mate-uc-flag.sqlite"))
    assert db_backend() == "sqlite"
    init_db()
    engine = db_connection.get_engine()
    assert engine.dialect.name == "sqlite"
    assert qualified_table("artifact") == "artifact"


def test_uc_qualified_table_and_volume_paths(monkeypatch, reset_db_engine):
    monkeypatch.setenv("MATE_DB_BACKEND", "uc")
    monkeypatch.setenv("MATE_UC_CATALOG", "automation_d")
    monkeypatch.setenv("MATE_UC_SCHEMA", "bronze")
    monkeypatch.setenv("MATE_UC_VOLUME", "bronze_volume")
    assert db_backend() == "uc"
    assert qualified_table("artifact") == "automation_d.bronze.mate_artifact"
    assert qualified_table("mate_hub_module") == "automation_d.bronze.mate_hub_module"
    assert projects_data_root() == Path("/Volumes/automation_d/bronze/bronze_volume/mate")
    assert uc_volume_root() == Path("/Volumes/automation_d/bronze/bronze_volume/mate")


def test_uc_import_builds_connect_args_without_network(monkeypatch, reset_db_engine):
    """Import + connect_args construction must not require a live warehouse."""
    monkeypatch.setenv("MATE_DB_BACKEND", "uc")
    monkeypatch.setenv("MATE_UC_CATALOG", "automation_d")
    monkeypatch.setenv("DATABRICKS_WAREHOUSE_ID", "69ada62b2fb9b9e2")
    monkeypatch.setenv("DATABRICKS_HOST", "https://adb-example.azuredatabricks.net")
    monkeypatch.setenv("DATABRICKS_TOKEN", "dapi-test-token-not-real")
    clear_obo()
    args = db_connection._uc_connect_args()
    assert args["server_hostname"] == "adb-example.azuredatabricks.net"
    assert args["http_path"] == "/sql/1.0/warehouses/69ada62b2fb9b9e2"
    assert args["catalog"] == "automation_d"
    assert args["schema"] == "bronze"
    assert args["access_token"] == "dapi-test-token-not-real"


def test_uc_connect_args_prefers_obo_token_when_sql_scope_present(
    monkeypatch, reset_db_engine
):
    monkeypatch.setenv("MATE_DB_BACKEND", "uc")
    monkeypatch.setenv("MATE_UC_CATALOG", "automation_d")
    monkeypatch.setenv("DATABRICKS_WAREHOUSE_ID", "69ada62b2fb9b9e2")
    monkeypatch.setenv("DATABRICKS_HOST", "https://adb-example.azuredatabricks.net")
    monkeypatch.setenv("DATABRICKS_TOKEN", "dapi-sp-token-should-not-win")
    token = _jwt("sql", "ai-gateway")
    bind_obo_from_headers({"x-forwarded-access-token": token})
    try:
        args = db_connection._uc_connect_args()
        assert args["access_token"] == token
        assert args["server_hostname"] == "adb-example.azuredatabricks.net"
        assert "credentials_provider" not in args
    finally:
        clear_obo()


def test_uc_connect_args_falls_back_to_m2m_without_sql_scope(
    monkeypatch, reset_db_engine
):
    monkeypatch.setenv("MATE_DB_BACKEND", "uc")
    monkeypatch.setenv("MATE_UC_CATALOG", "automation_d")
    monkeypatch.setenv("DATABRICKS_WAREHOUSE_ID", "69ada62b2fb9b9e2")
    monkeypatch.setenv("DATABRICKS_HOST", "https://adb-example.azuredatabricks.net")
    monkeypatch.setenv("DATABRICKS_TOKEN", "dapi-sp-token-should-win")
    bind_obo_from_headers({"x-forwarded-access-token": _jwt("postgres", "ai-gateway")})
    try:
        args = db_connection._uc_connect_args()
        assert args["access_token"] == "dapi-sp-token-should-win"
        assert "credentials_provider" not in args
    finally:
        clear_obo()


def test_uc_connect_args_falls_back_to_m2m_for_opaque_obo_token(
    monkeypatch, reset_db_engine
):
    monkeypatch.setenv("MATE_DB_BACKEND", "uc")
    monkeypatch.setenv("MATE_UC_CATALOG", "automation_d")
    monkeypatch.setenv("DATABRICKS_WAREHOUSE_ID", "69ada62b2fb9b9e2")
    monkeypatch.setenv("DATABRICKS_HOST", "https://adb-example.azuredatabricks.net")
    monkeypatch.setenv("DATABRICKS_TOKEN", "dapi-sp-token-should-win")
    bind_obo_from_headers({"x-forwarded-access-token": "visitor-obo-token"})
    try:
        args = db_connection._uc_connect_args()
        assert args["access_token"] == "dapi-sp-token-should-win"
        assert "credentials_provider" not in args
    finally:
        clear_obo()


def test_uc_init_db_skips_warehouse_when_no_obo(monkeypatch, reset_db_engine):
    """Boot must not open DBSQL / crash when no visitor OBO is bound."""
    monkeypatch.setenv("MATE_DB_BACKEND", "uc")
    monkeypatch.setenv("MATE_UC_CATALOG", "automation_d")
    monkeypatch.setenv("DATABRICKS_WAREHOUSE_ID", "69ada62b2fb9b9e2")
    monkeypatch.setenv("DATABRICKS_HOST", "https://adb-example.azuredatabricks.net")
    monkeypatch.setenv("DATABRICKS_TOKEN", "dapi-test-token-not-real")
    clear_obo()

    called = {"seed": False, "connect": False}

    def _boom_seed(_session):
        called["seed"] = True
        raise AssertionError("seed_hub_modules must not run without OBO at boot")

    def _boom_connect(**_kwargs):
        called["connect"] = True
        raise AssertionError("warehouse connect must not run without OBO at boot")

    monkeypatch.setattr("shared.db.seed.seed_hub_modules", _boom_seed)
    monkeypatch.setattr(db_connection, "_uc_dbapi_connect", _boom_connect)

    init_db()
    engine = db_connection.get_engine()
    assert engine is not None
    assert called["seed"] is False
    assert called["connect"] is False
