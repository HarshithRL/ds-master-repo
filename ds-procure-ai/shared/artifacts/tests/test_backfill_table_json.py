"""W1 backfill: re-chunk from parsed_json on a copy of mate.sqlite."""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from shared.db import connection as db_connection
from shared.db.migrate import apply_kb_foundation

ROOT = Path(__file__).resolve().parents[3]
MATE_SQLITE = ROOT / "mate.sqlite"


@pytest.fixture()
def isolated_engine():
    if db_connection._engine is not None:
        db_connection._engine.dispose()
    db_connection._engine = None
    db_connection._SessionLocal = None
    yield
    if db_connection._engine is not None:
        db_connection._engine.dispose()
    db_connection._engine = None
    db_connection._SessionLocal = None


def test_backfill_on_copy_of_mate_sqlite(tmp_path, monkeypatch, isolated_engine):
    if not MATE_SQLITE.exists():
        pytest.skip("mate.sqlite not present")
    copy = tmp_path / "mate-copy.sqlite"
    shutil.copy2(MATE_SQLITE, copy)
    monkeypatch.setenv("MATE_SQLITE_PATH", str(copy))

    from sqlalchemy import create_engine

    engine = create_engine(f"sqlite:///{copy.as_posix()}")
    apply_kb_foundation(engine)
    engine.dispose()

    from scripts.backfill_table_json import backfill_ok_artifacts

    stats = backfill_ok_artifacts()
    assert stats["artifacts"] > 0
    assert stats["table_chunks"] > 0

    conn = sqlite3.connect(copy)
    nulls = conn.execute(
        "SELECT count(*) FROM chunk WHERE chunk_type='table' AND table_json IS NULL"
    ).fetchone()[0]
    assert nulls == 0

    inetum = conn.execute(
        "SELECT parsed_json FROM artifact "
        "WHERE parse_status='ok' AND original_name LIKE '%Inetum%' "
        "AND parsed_json IS NOT NULL LIMIT 1"
    ).fetchone()
    conn.close()
    assert inetum is not None
    doc = json.loads(inetum[0])
    page5 = [
        block
        for block in doc.get("blocks") or []
        if block.get("type") == "table" and (block.get("location") or {}).get("page") == 5
    ]
    assert page5, "expected Inetum page-5 table in parsed_json"
    table = page5[0]["table"]
    assert max(len(row) for row in table) == 3
