"""UC backend helpers + sqlite init smoke tests."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from shared.db import connection as db_connection
from shared.db.connection import init_db, mate_table_name, qualified_table
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
    assert mate_table_name("chunk") == "chunk"
    assert mate_table_name("artifact") == "artifact"


def test_uc_qualified_table_and_volume_paths(monkeypatch, reset_db_engine):
    monkeypatch.setenv("MATE_DB_BACKEND", "uc")
    monkeypatch.setenv("MATE_UC_AUTH", "obo")
    monkeypatch.setenv("MATE_UC_CATALOG", "automation_d")
    monkeypatch.setenv("MATE_UC_SCHEMA", "bronze")
    monkeypatch.setenv("MATE_UC_VOLUME", "bronze_volume")
    assert db_backend() == "uc"
    assert qualified_table("artifact") == "automation_d.bronze.mate_artifact"
    assert qualified_table("mate_hub_module") == "automation_d.bronze.mate_hub_module"
    assert mate_table_name("chunk") == "mate_chunk"
    assert mate_table_name("artifact") == "mate_artifact"
    assert mate_table_name("kb_edge") == "mate_kb_edge"
    assert mate_table_name("chunk_embedding") == "mate_chunk_embedding"
    assert projects_data_root() == Path("/Volumes/automation_d/bronze/bronze_volume/mate")
    assert uc_volume_root() == Path("/Volumes/automation_d/bronze/bronze_volume/mate")


def test_uc_import_builds_connect_args_without_network(monkeypatch, reset_db_engine):
    """Import + connect_args construction must not require a live warehouse."""
    monkeypatch.setenv("MATE_DB_BACKEND", "uc")
    monkeypatch.setenv("MATE_UC_AUTH", "obo")
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
    monkeypatch.setenv("MATE_UC_AUTH", "obo")
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
    monkeypatch.setenv("MATE_UC_AUTH", "obo")
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
    monkeypatch.setenv("MATE_UC_AUTH", "obo")
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
    monkeypatch.setenv("MATE_UC_AUTH", "obo")
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
    monkeypatch.setattr(db_connection, "_ensure_uc_dialect", lambda: None)
    monkeypatch.setattr(db_connection, "_apply_uc_mate_table_prefix", lambda: None)

    from unittest.mock import MagicMock

    def fake_create(*_args, **_kwargs):
        engine = MagicMock()
        engine.dispose = MagicMock()
        return engine

    monkeypatch.setattr(db_connection, "create_engine", fake_create)

    init_db()
    engine = db_connection.get_engine()
    assert engine is not None
    assert called["seed"] is False
    assert called["connect"] is False


def _uc_env(monkeypatch) -> None:
    monkeypatch.setenv("MATE_DB_BACKEND", "uc")
    monkeypatch.setenv("MATE_UC_AUTH", "obo")
    monkeypatch.setenv("MATE_UC_CATALOG", "automation_d")
    monkeypatch.setenv("DATABRICKS_WAREHOUSE_ID", "69ada62b2fb9b9e2")
    monkeypatch.setenv("DATABRICKS_HOST", "https://adb-example.azuredatabricks.net")
    monkeypatch.setenv("DATABRICKS_TOKEN", "dapi-sp-token")


def _stub_uc_engines(monkeypatch):
    from unittest.mock import MagicMock

    from sqlalchemy.pool import QueuePool

    created: list[MagicMock] = []

    def fake_create(*_args, **kwargs):
        engine = MagicMock()
        engine.dispose = MagicMock()
        engine.poolclass = kwargs.get("poolclass")
        engine.create_kwargs = kwargs
        created.append(engine)
        return engine

    monkeypatch.setattr(db_connection, "_ensure_uc_dialect", lambda: None)
    monkeypatch.setattr(db_connection, "_apply_uc_mate_table_prefix", lambda: None)
    monkeypatch.setattr(db_connection, "create_engine", fake_create)
    return created, QueuePool


def test_uc_engine_reused_for_same_obo_key(monkeypatch, reset_db_engine):
    _uc_env(monkeypatch)
    created, pool_cls = _stub_uc_engines(monkeypatch)
    token = _jwt("sql", "profile")
    bind_obo_from_headers({"x-forwarded-access-token": token})
    try:
        first = db_connection.get_engine()
        second = db_connection.get_engine()
        assert first is second
        assert len(created) == 1
        assert created[0].create_kwargs["poolclass"] is pool_cls
        assert created[0].create_kwargs["pool_size"] == 2
        assert created[0].create_kwargs["max_overflow"] == 2
        assert created[0].create_kwargs["pool_recycle"] == 2700
    finally:
        clear_obo()


def test_uc_engine_differs_by_obo_key_and_reuses_previous(monkeypatch, reset_db_engine):
    _uc_env(monkeypatch)
    created, _pool_cls = _stub_uc_engines(monkeypatch)
    token_a = _jwt("sql")
    token_b = _jwt("sql", "email")
    bind_obo_from_headers({"x-forwarded-access-token": token_a})
    try:
        engine_a = db_connection.get_engine()
        bind_obo_from_headers({"x-forwarded-access-token": token_b})
        engine_b = db_connection.get_engine()
        assert engine_b is not engine_a
        assert len(created) == 2
        bind_obo_from_headers({"x-forwarded-access-token": token_a})
        engine_a_again = db_connection.get_engine()
        assert engine_a_again is engine_a
        assert len(created) == 2
    finally:
        clear_obo()


def test_uc_engine_cache_evicts_lru(monkeypatch, reset_db_engine):
    _uc_env(monkeypatch)
    created, _pool_cls = _stub_uc_engines(monkeypatch)
    monkeypatch.setattr(db_connection, "_UC_ENGINE_CACHE_MAX", 2)
    tokens = [_jwt("sql", f"s{i}") for i in range(3)]
    try:
        bind_obo_from_headers({"x-forwarded-access-token": tokens[0]})
        first = db_connection.get_engine()
        bind_obo_from_headers({"x-forwarded-access-token": tokens[1]})
        db_connection.get_engine()
        bind_obo_from_headers({"x-forwarded-access-token": tokens[2]})
        db_connection.get_engine()
        assert first.dispose.called
        assert len(db_connection._uc_engines) == 2
    finally:
        clear_obo()


def test_reset_engine_state_disposes_uc_cache(monkeypatch, reset_db_engine):
    _uc_env(monkeypatch)
    created, _pool_cls = _stub_uc_engines(monkeypatch)
    bind_obo_from_headers({"x-forwarded-access-token": _jwt("sql")})
    try:
        engine = db_connection.get_engine()
        db_connection.reset_engine_state()
        assert engine.dispose.called
        assert db_connection._uc_engines == {}
        assert db_connection._engine is None
    finally:
        clear_obo()


def test_uc_raw_sql_helpers_use_mate_prefix(monkeypatch, reset_db_engine):
    monkeypatch.setenv("MATE_DB_BACKEND", "uc")
    monkeypatch.setenv("MATE_UC_CATALOG", "automation_a")
    from ai_brain.core.kb.store.embed import _pending_chunks_sql
    from ai_brain.core.kb.store.graph import independence_cte
    from ai_brain.core.kb.store.search import _chunk_artifact_join_sql

    join_sql = _chunk_artifact_join_sql()
    assert "FROM mate_chunk c" in join_sql
    assert "JOIN mate_artifact a" in join_sql
    assert "FROM chunk " not in join_sql

    pending = _pending_chunks_sql()
    assert "FROM mate_chunk c" in pending
    assert "FROM mate_chunk_embedding" in pending
    assert "FROM chunk " not in pending
    assert "FROM chunk_embedding" not in pending

    cte = independence_cte()
    assert "FROM mate_kb_edge" in cte
    assert "FROM kb_edge" not in cte


def test_bid_chunk_stmt_is_orm_join_not_raw_chunk_sql(monkeypatch, reset_db_engine):
    monkeypatch.setenv("MATE_DB_BACKEND", "uc")
    monkeypatch.setenv("MATE_UC_CATALOG", "automation_a")
    from ai_brain.core.kb.api.mcp_tools import _bid_chunk_stmt

    stmt = _bid_chunk_stmt("7af69e4b-ee3c-4138-85ef-6b51cb215d34", "bdo")

    def _from_names(obj) -> set[str]:
        names: set[str] = set()
        stack = [obj]
        while stack:
            cur = stack.pop()
            name = getattr(cur, "name", None)
            if isinstance(name, str):
                names.add(name)
            left = getattr(cur, "left", None)
            right = getattr(cur, "right", None)
            if left is not None:
                stack.append(left)
            if right is not None:
                stack.append(right)
        return names

    froms: set[str] = set()
    for item in stmt.get_final_froms():
        froms |= _from_names(item)
    assert froms == {"chunk", "artifact"}
    compiled = str(stmt.compile())
    assert "FROM chunk c JOIN artifact a" not in " ".join(compiled.split())
    assert "vendor_id" in str(stmt.whereclause.compile())
    rfp_stmt = _bid_chunk_stmt("pid", "rfp")
    rfp_where = str(rfp_stmt.whereclause.compile()).lower()
    assert "doc_role" in rfp_where
    assert "vendor_id" not in rfp_where


def test_list_bid_chunk_rows_sqlite_vendor_and_rfp(tmp_path, monkeypatch, reset_db_engine):
    monkeypatch.delenv("MATE_DB_BACKEND", raising=False)
    monkeypatch.setenv("MATE_SQLITE_PATH", str(tmp_path / "mate-chunks.sqlite"))
    init_db()
    from shared.db.connection import session_scope
    from shared.db.models import AppUser, Artifact, Chunk, Project, utc_now_iso
    from ai_brain.core.kb.api.mcp_tools import list_bid_chunk_rows

    now = utc_now_iso()
    with session_scope() as session:
        session.add(AppUser(workspace_id="u1", created_at=now, updated_at=now))
        session.add(
            Project(
                id="p1",
                code="PRJ-TEST",
                owner_id="u1",
                module_id="procurement-ai-assistant",
                name="SWIFT",
                status="Active",
                priority="Medium",
                progress=0,
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            Artifact(
                id="art-bdo",
                project_id="p1",
                uploaded_by="u1",
                kind="upload",
                original_name="BDO_Offer.pdf",
                storage_relpath="rel/bdo",
                created_at=now,
                parse_status="ok",
                vendor_id="bdo",
                doc_role="proposal",
            )
        )
        session.add(
            Artifact(
                id="art-rfp",
                project_id="p1",
                uploaded_by="u1",
                kind="upload",
                original_name="RFP.docx",
                storage_relpath="rel/rfp",
                created_at=now,
                parse_status="ok",
                vendor_id=None,
                doc_role="rfp",
            )
        )
        session.add(
            Chunk(
                id="c-bdo",
                project_id="p1",
                artifact_id="art-bdo",
                ordinal=0,
                chunk_type="text",
                text="BDO pricing",
                token_count=2,
                heading_path_json='["Pricing"]',
                location_json='{"page":3}',
                created_at=now,
            )
        )
        session.add(
            Chunk(
                id="c-rfp",
                project_id="p1",
                artifact_id="art-rfp",
                ordinal=0,
                chunk_type="text",
                text="requirement one",
                token_count=2,
                heading_path_json='["Scope"]',
                location_json='{"page":1}',
                created_at=now,
            )
        )

    vendor_rows = list_bid_chunk_rows("p1", "bdo")
    assert [row["chunk_id"] for row in vendor_rows] == ["c-bdo"]
    assert vendor_rows[0]["locator"] == "p.3"
    rfp_rows = list_bid_chunk_rows("p1", "rfp")
    assert [row["chunk_id"] for row in rfp_rows] == ["c-rfp"]

