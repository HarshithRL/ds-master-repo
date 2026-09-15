"""LangGraph checkpointer + long-term store factory (lakebase / sqlite / memory)."""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from ai_brain.core.config.memory import get_memory_settings
from shared.databricks_runtime import is_databricks_app
from shared.logger_global import get_logger

log = get_logger(__name__, service="ai_brain")


@dataclass
class CheckpointHandle:
    saver: Any
    store: Any = None
    close: Callable[[], Awaitable[None]] | None = None
    _closers: list[Callable[[], Awaitable[None]]] = field(default_factory=list)

    async def aclose(self) -> None:
        if self.close is not None:
            await self.close()
            return
        for closer in reversed(self._closers):
            await closer()


def _embeddings(settings: Any) -> Any:
    from databricks_langchain import DatabricksEmbeddings

    endpoint = settings.embedding_endpoint
    kwargs: dict[str, Any] = {"endpoint": endpoint}
    fields = getattr(DatabricksEmbeddings, "model_fields", None) or getattr(
        DatabricksEmbeddings, "__fields__", {}
    )
    if "workspace_client" in fields:
        from shared.databricks_runtime import RequestScopedWorkspaceClient

        kwargs["workspace_client"] = RequestScopedWorkspaceClient()
    # DatabricksEmbeddings uses MLflow default auth. Set a CLI profile only
    # locally — Apps has no ~/.databrickscfg and uses injected OAuth M2M.
    if not is_databricks_app():
        os.environ.setdefault("DATABRICKS_CONFIG_PROFILE", settings.config_profile)
    return DatabricksEmbeddings(**kwargs)


def _store_index(settings: Any) -> dict[str, Any]:
    return {
        "dims": settings.embedding_dims,
        "embed": _embeddings(settings),
        "fields": ["text"],
    }


async def _open_sqlite_saver() -> tuple[Any, Callable[[], Awaitable[None]]]:
    import aiosqlite
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    path = os.getenv(
        "BRAIN_CHECKPOINT_SQLITE_PATH",
        str(Path(__file__).resolve().parents[1] / ".checkpoints" / "nexus.sqlite"),
    )
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(path)
    saver = AsyncSqliteSaver(conn)
    await saver.setup()
    log.info("checkpointer backend=sqlite path={}", path)

    async def close() -> None:
        await conn.close()

    return saver, close


async def _open_postgres_uri_saver() -> tuple[Any, Callable[[], Awaitable[None]]]:
    uri = (
        os.getenv("BRAIN_CHECKPOINT_POSTGRES_URI", "").strip()
        or os.getenv("DATABASE_URL", "").strip()
    )
    if not uri:
        raise RuntimeError(
            "BRAIN_CHECKPOINT_BACKEND=postgres requires BRAIN_CHECKPOINT_POSTGRES_URI"
        )
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    except ImportError as exc:
        raise RuntimeError(
            "Install langgraph-checkpoint-postgres for postgres checkpointer"
        ) from exc

    cm = AsyncPostgresSaver.from_conn_string(uri)
    saver = await cm.__aenter__()
    await saver.setup()
    log.info("checkpointer backend=postgres")

    async def close() -> None:
        await cm.__aexit__(None, None, None)

    return saver, close


async def _ensure_app_schema(pool: Any, schema: str) -> None:
    """Create mate_agent if missing, then refuse if the app user does not own it.

    The app service principal can create objects. It cannot write a schema a
    laptop user already owns. Do not drop that schema from here.
    """
    from psycopg import sql

    from ai_brain.server.lakebase import _schema_identifier, apply_search_path

    name = (schema or "mate_agent").strip()
    async with pool.connection() as conn:
        await conn.execute(
            sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(_schema_identifier(name))
        )
        cur = await conn.execute(
            """
            SELECT r.rolname AS owner, current_user AS me
            FROM pg_namespace n
            JOIN pg_roles r ON r.oid = n.nspowner
            WHERE n.nspname = %s
            """,
            (name,),
        )
        found = await cur.fetchone()
        if not found:
            raise RuntimeError(f"Lakebase schema {name} was not created")
        owner = found["owner"]
        me = found["me"]
        if owner != me:
            raise RuntimeError(
                f"Lakebase schema {name} is owned by {owner}, not the app user {me}. "
                "The app service principal must own this schema before checkpoint tables "
                "can be created. Do not drop it from the app process."
            )
        await apply_search_path(conn, name)
        log.info("lakebase schema ready name={} owner={}", name, me)


async def _open_lakebase_saver(pool: Any, schema: str) -> Any:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    await _ensure_app_schema(pool, schema)
    saver = AsyncPostgresSaver(conn=pool)
    await saver.setup()
    log.info("checkpointer backend=lakebase schema={}", schema)
    return saver


async def _open_lakebase_store(pool: Any, settings: Any) -> Any:
    from langgraph.store.postgres.aio import AsyncPostgresStore

    store = AsyncPostgresStore(conn=pool, index=_store_index(settings))
    await store.setup()
    log.info(
        "store backend=lakebase schema={} embed={}",
        settings.lakebase_schema,
        settings.embedding_endpoint,
    )
    return store


async def open_checkpointer() -> CheckpointHandle:
    settings = get_memory_settings()
    checkpoint_backend = settings.checkpoint_backend
    store_backend = settings.store_backend
    closers: list[Callable[[], Awaitable[None]]] = []
    pool_handle = None

    needs_lakebase = checkpoint_backend == "lakebase" or store_backend == "lakebase"
    if needs_lakebase:
        from ai_brain.server.lakebase import open_lakebase_pool

        pool_handle = await open_lakebase_pool()
        closers.append(pool_handle.close)

    if checkpoint_backend in {"memory", "inmemory", "in-memory"}:
        log.info("checkpointer backend=memory")
        saver: Any = InMemorySaver()
    elif checkpoint_backend == "sqlite":
        saver, close_sqlite = await _open_sqlite_saver()
        closers.append(close_sqlite)
    elif checkpoint_backend == "postgres":
        saver, close_pg = await _open_postgres_uri_saver()
        closers.append(close_pg)
    elif checkpoint_backend == "lakebase":
        if pool_handle is None:
            raise RuntimeError("Lakebase pool was not opened")
        saver = await _open_lakebase_saver(pool_handle.pool, settings.lakebase_schema)
    else:
        raise RuntimeError(f"Unknown BRAIN_CHECKPOINT_BACKEND: {checkpoint_backend}")

    if store_backend in {"memory", "inmemory", "in-memory"}:
        store: Any = InMemoryStore()
        log.info("store backend=memory")
    elif store_backend == "lakebase":
        if pool_handle is None:
            raise RuntimeError("Lakebase pool was not opened")
        store = await _open_lakebase_store(pool_handle.pool, settings)
    else:
        raise RuntimeError(f"Unknown BRAIN_STORE_BACKEND: {store_backend}")

    async def close() -> None:
        for closer in reversed(closers):
            await closer()

    return CheckpointHandle(saver=saver, store=store, close=close, _closers=closers)
