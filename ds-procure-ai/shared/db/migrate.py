"""Apply KB foundation migrations. Sqlite in dev; Postgres/Lakebase optional."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from shared.logger_global import get_logger

log = get_logger(__name__)

_MIGRATIONS = Path(__file__).resolve().parents[2] / "backend" / "migrations"

_ARTIFACT_COLUMNS: tuple[tuple[str, str], ...] = (
    ("vendor_id", "VARCHAR"),
    ("doc_role", "VARCHAR"),
    ("role_confidence", "REAL"),
    ("content_hash", "VARCHAR"),
    ("superseded_by", "VARCHAR"),
)

_CHUNK_COLUMNS: tuple[tuple[str, str], ...] = (
    ("table_json", "TEXT"),
    ("page_kind", "VARCHAR"),
    ("reconstructor", "VARCHAR"),
)


def _table_columns(engine: Engine, table: str) -> set[str]:
    inspector = inspect(engine)
    if table not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns(table)}


def _add_missing_columns(
    engine: Engine, table: str, columns: tuple[tuple[str, str], ...]
) -> None:
    existing = _table_columns(engine, table)
    with engine.begin() as conn:
        for name, typedef in columns:
            if name in existing:
                continue
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {typedef}"))
            log.info("kb migration added {}.{}", table, name)


def apply_kb_foundation(engine: Engine) -> dict[str, str]:
    """Idempotent W0 schema. Returns status per dialect extra (vector/tsv)."""
    dialect = engine.dialect.name
    _add_missing_columns(engine, "artifact", _ARTIFACT_COLUMNS)
    _add_missing_columns(engine, "chunk", _CHUNK_COLUMNS)

    sqlite_sql = (_MIGRATIONS / "001_kb_foundation.sqlite.sql").read_text(encoding="utf-8")
    _run_sqlite_create_statements(engine, sqlite_sql)

    with engine.begin() as conn:
        conn.execute(
            text("UPDATE artifact SET parse_status = 'pending' WHERE parse_status IS NULL")
        )

    extras = {"vector": "skipped", "tsv": "skipped"}
    if dialect in {"postgresql", "postgres"}:
        extras = _apply_postgres_search(engine)
    else:
        log.info("kb migration skipped Lakebase vector/tsv dialect={}", dialect)
    return extras


def _run_sqlite_create_statements(engine: Engine, sql: str) -> None:
    """Execute CREATE TABLE / INDEX statements; ignore comments and ALTER comments."""
    statements: list[str] = []
    buf: list[str] = []
    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.startswith("--") or not stripped:
            continue
        buf.append(line)
        if stripped.endswith(";"):
            statements.append("\n".join(buf).strip())
            buf = []
    if buf:
        statements.append("\n".join(buf).strip())
    with engine.begin() as conn:
        for stmt in statements:
            if not stmt:
                continue
            conn.execute(text(stmt))


def _apply_postgres_search(engine: Engine) -> dict[str, str]:
    sql_path = _MIGRATIONS / "001_kb_foundation.postgres.sql"
    try:
        with engine.begin() as conn:
            conn.execute(text(sql_path.read_text(encoding="utf-8")))
        return {"vector": "applied", "tsv": "applied"}
    except Exception as exc:  # noqa: BLE001
        log.warning("Lakebase vector/tsv migration failed: {}", exc)
        return {"vector": f"blocked:{exc}", "tsv": f"blocked:{exc}"}


def lakebase_configured() -> bool:
    return bool(
        os.getenv("LAKEBASE_ENDPOINT", "").strip()
        or os.getenv("BRAIN_CHECKPOINT_POSTGRES_URI", "").strip()
        or os.getenv("DATABASE_URL", "").strip()
    )
