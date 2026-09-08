"""SQLite engine, session factory, and schema bootstrap."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from shared.bootstrap import ensure_repo_root_on_path
from shared.db.paths import resolve_under_repo

ensure_repo_root_on_path()

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DB_PATH = _REPO_ROOT / "mate.sqlite"

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def sqlite_path() -> Path:
    override = os.getenv("MATE_SQLITE_PATH", "").strip()
    if override:
        return resolve_under_repo(override)
    return _DEFAULT_DB_PATH


def database_url() -> str:
    return f"sqlite:///{sqlite_path().as_posix()}"


def _enable_wal(dbapi_conn, _connection_record) -> None:
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def get_engine() -> Engine:
    global _engine, _SessionLocal
    if _engine is not None:
        return _engine

    db_path = sqlite_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    _engine = create_engine(
        database_url(),
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )
    event.listen(_engine, "connect", _enable_wal)
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    return _engine


def get_session() -> Session:
    if _SessionLocal is None:
        get_engine()
    assert _SessionLocal is not None
    return _SessionLocal()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


_PROJECT_COLUMN_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("workflow_entry_point", "TEXT"),
    ("business_process", "TEXT"),
    ("requester", "TEXT"),
    ("dept", "TEXT"),
)

_ARTIFACT_COLUMN_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("parsed_json", "TEXT"),
    ("parse_status", "TEXT"),
    ("parse_error", "TEXT"),
    ("parsed_relpath", "TEXT"),
    ("vendor_id", "VARCHAR"),
    ("doc_role", "VARCHAR"),
    ("role_confidence", "REAL"),
    ("content_hash", "VARCHAR"),
    ("superseded_by", "VARCHAR"),
)

_CHUNK_COLUMN_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("table_json", "TEXT"),
    ("page_kind", "VARCHAR"),
    ("reconstructor", "VARCHAR"),
)


def _ensure_table_columns(
    engine: Engine,
    table_name: str,
    migrations: tuple[tuple[str, str], ...],
) -> None:
    with engine.connect() as conn:
        rows = conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
        existing = {row[1] for row in rows}
        if not existing:
            return
        for column_name, column_type in migrations:
            if column_name in existing:
                continue
            conn.execute(
                text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
            )
        conn.commit()


def init_db() -> None:
    from shared.db.models import Base
    from shared.db.seed import seed_hub_modules

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    _ensure_table_columns(engine, "project", _PROJECT_COLUMN_MIGRATIONS)
    _ensure_table_columns(engine, "artifact", _ARTIFACT_COLUMN_MIGRATIONS)
    _ensure_table_columns(engine, "chunk", _CHUNK_COLUMN_MIGRATIONS)
    from shared.db.migrate import apply_kb_foundation

    apply_kb_foundation(engine)
    with session_scope() as session:
        seed_hub_modules(session)
