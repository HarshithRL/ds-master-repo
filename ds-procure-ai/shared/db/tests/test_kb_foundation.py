"""W0 KB foundation migration tests. Copies mate.sqlite; never mutates it."""

from __future__ import annotations

import shutil
import sqlite3
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError

from shared.db import init_db
from shared.db import connection as db_connection
from shared.db.migrate import apply_kb_foundation
from shared.db.models import Evidence, utc_now_iso

ROOT = Path(__file__).resolve().parents[3]
MATE_SQLITE = ROOT / "mate.sqlite"


@pytest.fixture()
def db_env(monkeypatch):
    if db_connection._engine is not None:
        db_connection._engine.dispose()
    db_connection._engine = None
    db_connection._SessionLocal = None
    tmp = tempfile.mkdtemp()
    db_path = Path(tmp) / "test.sqlite"
    monkeypatch.setenv("MATE_SQLITE_PATH", str(db_path))
    init_db()
    yield db_path
    if db_connection._engine is not None:
        db_connection._engine.dispose()
    db_connection._engine = None
    db_connection._SessionLocal = None
    shutil.rmtree(tmp, ignore_errors=True)


def test_kb_tables_exist_after_init(db_env):
    conn = sqlite3.connect(db_env)
    names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    for table in (
        "vendor",
        "requirement",
        "evidence",
        "pricing_line",
        "bid_profile",
        "kb_node",
        "kb_edge",
        "quality_flag",
    ):
        assert table in names, table


def test_artifact_and_chunk_kb_columns(db_env):
    conn = sqlite3.connect(db_env)
    artifact_cols = {row[1] for row in conn.execute("PRAGMA table_info(artifact)")}
    chunk_cols = {row[1] for row in conn.execute("PRAGMA table_info(chunk)")}
    conn.close()
    for col in ("vendor_id", "doc_role", "role_confidence", "content_hash", "superseded_by"):
        assert col in artifact_cols, col
    for col in ("table_json", "page_kind", "reconstructor"):
        assert col in chunk_cols, col


def test_evidence_status_check_rejects_unknown(db_env):
    from shared.db.connection import session_scope

    with pytest.raises(IntegrityError):
        with session_scope() as session:
            session.add(
                Evidence(
                    id="ev-bad",
                    project_id="p1",
                    requirement_id="r1",
                    vendor_id="v1",
                    status="invented",
                    claim_text="x",
                    model_version="m",
                    prompt_version="p",
                    extracted_at=utc_now_iso(),
                )
            )


def test_null_parse_status_backfilled_to_pending(db_env):
    conn = sqlite3.connect(db_env)
    conn.execute(
        "INSERT INTO app_user (workspace_id, created_at, updated_at) VALUES ('u1','t','t')"
    )
    conn.execute(
        "INSERT INTO project (id, code, owner_id, module_id, name, status, priority, progress, created_at, updated_at) "
        "VALUES ('p1','C1','u1','procurement-ai-assistant','n','Active','Medium',0,'t','t')"
    )
    conn.execute(
        "INSERT INTO artifact (id, project_id, uploaded_by, kind, original_name, storage_relpath, created_at) "
        "VALUES ('a1','p1','u1','upload','f.pdf','rel/a','t')"
    )
    conn.commit()
    conn.close()

    from shared.db.connection import get_engine

    apply_kb_foundation(get_engine())
    conn = sqlite3.connect(db_env)
    status = conn.execute("SELECT parse_status FROM artifact WHERE id='a1'").fetchone()[0]
    conn.close()
    assert status == "pending"


def test_migration_on_copy_of_mate_sqlite(tmp_path):
    if not MATE_SQLITE.exists():
        pytest.skip("mate.sqlite not present")
    copy = tmp_path / "mate-copy.sqlite"
    shutil.copy2(MATE_SQLITE, copy)
    engine = create_engine(f"sqlite:///{copy.as_posix()}")
    extras = apply_kb_foundation(engine)
    assert extras["vector"] == "skipped"
    conn = sqlite3.connect(copy)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    nulls = conn.execute(
        "SELECT count(*) FROM artifact WHERE parse_status IS NULL"
    ).fetchone()[0]
    conn.close()
    engine.dispose()
    assert "evidence" in tables
    assert "vendor" in tables
    assert nulls == 0
