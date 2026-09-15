"""SQLite / Unity Catalog engine, session factory, and schema bootstrap."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from shared.bootstrap import ensure_repo_root_on_path
from shared.db.paths import (
    db_backend,
    resolve_under_repo,
    uc_catalog,
    uc_schema,
)
from shared.logger_global import get_logger

ensure_repo_root_on_path()

log = get_logger(__name__)
_SQL_SCOPE = "sql"

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DB_PATH = _REPO_ROOT / "mate.sqlite"

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None
_uc_table_prefix_applied = False


def sqlite_path() -> Path:
    override = os.getenv("MATE_SQLITE_PATH", "").strip()
    if override:
        return resolve_under_repo(override)
    return _DEFAULT_DB_PATH


def database_url() -> str:
    if db_backend() == "uc":
        # Dialect registered by databricks-sql-connector; connect_args carry host/path/auth.
        return "databricks://"
    return f"sqlite:///{sqlite_path().as_posix()}"


def mate_table_name(base_name: str) -> str:
    """Unqualified table name for the active backend (mate_* when UC)."""
    name = base_name.strip()
    if db_backend() == "uc":
        return name if name.startswith("mate_") else f"mate_{name}"
    return name


def qualified_table(base_name: str) -> str:
    """Return ORM/SQLite name or catalog.schema.mate_* for UC."""
    table = mate_table_name(base_name)
    if db_backend() != "uc":
        return table
    catalog = uc_catalog()
    if not catalog:
        raise RuntimeError("MATE_UC_CATALOG is required when MATE_DB_BACKEND=uc")
    return f"{catalog}.{uc_schema()}.{table}"


def _enable_wal(dbapi_conn, _connection_record) -> None:
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


# Auto-detect warehouse from workspace ID in DATABRICKS_HOST when env var is
# not set (same pattern as ds-air-monitoring-app).
_WAREHOUSE_BY_WORKSPACE: dict[str, str] = {
    "7181820732839861": "69ada62b2fb9b9e2",   # dau-automation-sqlwh-d-01 (DEV/TEST)
    "4796304964978539": "69bb7020516c64f5",   # aut-dsprocureai-consumer-sqlwh-a (ACC)
    "4844910598668398": "",                     # PRD — fill when known
}


def _warehouse_id() -> str:
    wh = (
        os.getenv("DATABRICKS_WAREHOUSE_ID", "").strip()
        or os.getenv("MATE_UC_WAREHOUSE_ID", "").strip()
    )
    if wh:
        return wh
    host = os.getenv("DATABRICKS_HOST", "")
    for ws_id, fallback_wh in _WAREHOUSE_BY_WORKSPACE.items():
        if ws_id in host:
            return fallback_wh
    return ""


def _uc_connect_args() -> dict:
    catalog = uc_catalog()
    if not catalog:
        raise RuntimeError("MATE_UC_CATALOG is required when MATE_DB_BACKEND=uc")
    warehouse_id = _warehouse_id()
    if not warehouse_id:
        raise RuntimeError(
            "DATABRICKS_WAREHOUSE_ID (or MATE_UC_WAREHOUSE_ID) is required when MATE_DB_BACKEND=uc"
        )

    host = (os.getenv("DATABRICKS_HOST", "") or "").strip()
    # Mate UC is shared app-data. Default auth is app SP / M2M (path B).
    # Set MATE_UC_AUTH=obo only if you deliberately want visitor OBO + sql scope.
    uc_auth = (os.getenv("MATE_UC_AUTH", "sp") or "sp").strip().lower()
    obo_token = ""
    obo_scopes: list[str] = []
    if uc_auth in {"obo", "user", "visitor"}:
        try:
            from shared.databricks_runtime import (
                obo_access_token,
                obo_is_bound,
                obo_token_scopes,
            )

            if obo_is_bound():
                obo_scopes = obo_token_scopes()
                if _SQL_SCOPE in obo_scopes:
                    obo_token = (obo_access_token() or "").strip()
        except Exception:
            obo_token = ""
            obo_scopes = []

    token = ""
    cfg = None
    if not obo_token:
        token = (os.getenv("DATABRICKS_TOKEN", "") or "").strip()
        if not host or not token:
            from databricks.sdk.core import Config

            cfg = Config()
            if not host:
                host = (cfg.host or "").strip()
            if not token:
                token = (getattr(cfg, "token", None) or "").strip()
    elif not host:
        from databricks.sdk.core import Config

        cfg = Config()
        host = (cfg.host or "").strip()

    host = host.replace("https://", "").replace("http://", "").rstrip("/")
    if not host:
        raise RuntimeError("DATABRICKS_HOST (or SDK config host) is required when MATE_DB_BACKEND=uc")

    http_path = f"/sql/1.0/warehouses/{warehouse_id}"
    args: dict = {
        "server_hostname": host,
        "http_path": http_path,
        "catalog": catalog,
        "schema": uc_schema(),
    }
    if obo_token:
        args["access_token"] = obo_token
        auth = "obo"
    elif token:
        args["access_token"] = token
        auth = "m2m"
    else:
        if cfg is None:
            from databricks.sdk.core import Config

            cfg = Config()

        # Apps / M2M: reuse SDK auth headers (Bearer) without embedding secrets in code.
        def _credentials_provider():
            return cfg.authenticate

        args["credentials_provider"] = _credentials_provider
        auth = "m2m"
    log.info("uc connect auth={} scopes={}", auth, ",".join(obo_scopes) or "-")
    return args


def _uc_dbapi_connect():
    """Open a fresh DBSQL connection with current OBO/M2M connect args (NullPool creator)."""
    import databricks.sql as sql

    return sql.connect(**_uc_connect_args())


def _apply_uc_mate_table_prefix() -> None:
    """Map SQLAlchemy model tables to mate_* Delta names (UC only, once per process)."""
    global _uc_table_prefix_applied
    if _uc_table_prefix_applied or db_backend() != "uc":
        return

    from shared.db.models import Base

    rename = {
        table.name: f"mate_{table.name}"
        for table in Base.metadata.tables.values()
        if not table.name.startswith("mate_")
    }
    if not rename:
        _uc_table_prefix_applied = True
        return

    for table in list(Base.metadata.tables.values()):
        for fk in table.foreign_keys:
            colspec = getattr(fk, "_colspec", None)
            if not isinstance(colspec, str) or "." not in colspec:
                continue
            ref_table, ref_col = colspec.rsplit(".", 1)
            ref_base = ref_table.split(".")[-1]
            if ref_base in rename:
                fk._colspec = f"{rename[ref_base]}.{ref_col}"

    for old_name, new_name in rename.items():
        table = Base.metadata.tables.get(old_name)
        if table is None:
            continue
        schema = table.schema
        Base.metadata._remove_table(old_name, schema)
        table.name = new_name
        Base.metadata._add_table(new_name, schema, table)

    _uc_table_prefix_applied = True


def reset_engine_state() -> None:
    """Test helper: drop cached engine/session (does not un-prefix UC table names)."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def get_engine() -> Engine:
    global _engine, _SessionLocal
    if _engine is not None:
        return _engine

    if db_backend() == "uc":
        try:
            import databricks.sql  # noqa: F401
            # Dialect lives in separate package since connector 4.x.
            import databricks.sqlalchemy  # noqa: F401
        except ImportError as exc:  # pragma: no cover - depends on deploy extras
            raise ImportError(
                "MATE_DB_BACKEND=uc requires databricks-sql-connector and databricks-sqlalchemy. "
                "Install them or set MATE_DB_BACKEND=sqlite."
            ) from exc
        _apply_uc_mate_table_prefix()
        # NullPool + creator: each checkout rebuilds connect args so visitor OBO is current.
        # Do not pin a single SP token for the process lifetime.
        _engine = create_engine(
            database_url(),
            creator=_uc_dbapi_connect,
            poolclass=NullPool,
            pool_pre_ping=True,
        )
    else:
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

    if db_backend() == "uc":
        # Apply mate_* prefix and build NullPool engine without opening a warehouse
        # connection at gunicorn import (boot has no visitor OBO).
        get_engine()
        try:
            from shared.databricks_runtime import obo_is_bound

            if not obo_is_bound():
                # Seed needs a live DBSQL session; skip safely at worker boot.
                return
            with session_scope() as session:
                seed_hub_modules(session)
        except Exception:
            # Never crash the worker on missing warehouse SP perms at boot.
            return
        return

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    _ensure_table_columns(engine, "project", _PROJECT_COLUMN_MIGRATIONS)
    _ensure_table_columns(engine, "artifact", _ARTIFACT_COLUMN_MIGRATIONS)
    _ensure_table_columns(engine, "chunk", _CHUNK_COLUMN_MIGRATIONS)
    from shared.db.migrate import apply_kb_foundation

    apply_kb_foundation(engine)
    with session_scope() as session:
        seed_hub_modules(session)
