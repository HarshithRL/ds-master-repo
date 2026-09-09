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

    from ai_brain.core.config.llm import get_workspace_client

    endpoint = settings.embedding_endpoint
    kwargs: dict[str, Any] = {"endpoint": endpoint}
    fields = getattr(DatabricksEmbeddings, "model_fields", None) or getattr(
        DatabricksEmbeddings, "__fields__", {}
    )
    if "workspace_client" in fields:
        kwargs["workspace_client"] = get_workspace_client()
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


async def _open_lakebase_saver(pool: Any) -> Any:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    saver = AsyncPostgresSaver(conn=pool)
    await saver.setup()
    log.info("checkpointer backend=lakebase")
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
        saver = await _open_lakebase_saver(pool_handle.pool)
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
