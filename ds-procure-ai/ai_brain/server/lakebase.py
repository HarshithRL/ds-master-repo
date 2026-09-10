"""Lakebase Postgres pool with OAuth token refresh (no native PG password)."""

from __future__ import annotations

import asyncio
import os
import selectors
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from ai_brain.core.config.memory import get_memory_settings, search_path_options
from shared.databricks_runtime import workspace_client
from shared.logger_global import get_logger

log = get_logger(__name__, service="ai_brain")

_DEFAULT_PORT = 5432


def psycopg_loop_factory() -> asyncio.AbstractEventLoop:
    """Selector loop — psycopg async cannot run on Windows ProactorEventLoop."""
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop(selectors.SelectSelector())
    return asyncio.new_event_loop()


@dataclass
class TokenHolder:
    token: str = ""
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


@dataclass
class LakebasePoolHandle:
    pool: AsyncConnectionPool
    close: Callable[[], Awaitable[None]]


def host_from_endpoint_status(endpoint: Any) -> str:
    """Prefer the primary host (OAuth + session GUCs). Pooler is a fallback.

    Databricks connectivity docs use ``endpoint.status.hosts.host``. The
    Neon-style ``-pooler`` host rejects ``search_path`` as a startup GUC and
    currently fails SASL with Lakebase OAuth tokens.
    """
    hosts = getattr(getattr(endpoint, "status", None), "hosts", None)
    if hosts is None:
        return ""
    host = getattr(hosts, "host", None)
    if host:
        return str(host).strip()
    pooled = getattr(hosts, "read_write_pooled_host", None)
    return str(pooled or "").strip()


def is_pooler_host(host: str) -> bool:
    """Neon-style poolers reject ``search_path`` as a libpq startup GUC."""
    return "-pooler" in (host or "").lower()


def _schema_identifier(schema: str) -> sql.Identifier:
    name = (schema or "mate_agent").strip()
    if not name or not name.replace("_", "").isalnum():
        raise ValueError(f"invalid Lakebase schema name: {schema!r}")
    return sql.Identifier(name)


async def apply_search_path(conn: Any, schema: str) -> None:
    """SET search_path on an open connection (pooler-safe; not a startup option)."""
    await conn.execute(
        sql.SQL("SET search_path TO {}").format(_schema_identifier(schema))
    )


def _mint_token(workspace: Any, endpoint: str) -> str:
    cred = workspace.postgres.generate_database_credential(endpoint=endpoint)
    token = getattr(cred, "token", None)
    if not token:
        raise RuntimeError("generate_database_credential returned no token")
    return str(token)


def _resolve_username(workspace: Any, *, allow_pguser: bool = True) -> str:
    """Lakebase role is always the app SP (or injected PGUSER), never the visitor."""
    if allow_pguser:
        injected = os.getenv("PGUSER", "").strip()
        if injected:
            return injected
    user = workspace.current_user.me()
    name = getattr(user, "user_name", None)
    if not name:
        raise RuntimeError("Unable to infer Lakebase username")
    return str(name)


def _resolve_host(workspace: Any, endpoint: str, explicit_host: str) -> str:
    if explicit_host:
        return explicit_host
    ep = workspace.postgres.get_endpoint(name=endpoint)
    host = host_from_endpoint_status(ep)
    if not host:
        raise RuntimeError(f"Lakebase host not found for endpoint {endpoint}")
    return host


def _conninfo_value(value: str) -> str:
    """Quote libpq keyword values that contain ``@`` or whitespace."""
    if any(ch in value for ch in " '\\"):
        escaped = value.replace("\\", "\\\\").replace("'", "\\'")
        return f"'{escaped}'"
    if "@" in value:
        return f"'{value}'"
    return value


def _conninfo(*, host: str, dbname: str, user: str, sslmode: str, schema: str) -> str:
    port = os.getenv("PGPORT", str(_DEFAULT_PORT)).strip() or str(_DEFAULT_PORT)
    base = (
        f"host={_conninfo_value(host)} port={port} "
        f"dbname={_conninfo_value(dbname)} user={_conninfo_value(user)} "
        f"sslmode={sslmode}"
    )
    # Poolers (Neon/Lakebase -pooler hosts) reject options=-csearch_path=...
    # as a startup parameter. Direct hosts can take the libpq options GUC.
    if is_pooler_host(host):
        return base
    return f"{base} options={search_path_options(schema)}"


async def open_lakebase_pool() -> LakebasePoolHandle:
    """Open an async pool as the Apps service principal (WorkspaceClient M2M).

    Visitor OBO is not used here. Password is always ``generate_database_credential``
    from ``workspace_client()``.
    """
    settings = get_memory_settings()
    if not settings.lakebase_endpoint:
        raise RuntimeError("LAKEBASE_ENDPOINT is required for the lakebase backend")

    workspace = workspace_client()
    endpoint = settings.lakebase_endpoint
    host, username, token = await asyncio.gather(
        asyncio.to_thread(_resolve_host, workspace, endpoint, settings.lakebase_host),
        asyncio.to_thread(_resolve_username, workspace),
        asyncio.to_thread(_mint_token, workspace, endpoint),
    )
    holder = TokenHolder(token=token)
    schema_name = settings.lakebase_schema or "mate_agent"
    conninfo = _conninfo(
        host=host,
        dbname=settings.lakebase_database,
        user=username,
        sslmode=settings.sslmode or "require",
        schema=schema_name,
    )

    class _RotatingConnection(psycopg.AsyncConnection):
        @classmethod
        async def connect(cls, conninfo: str = "", **kwargs: Any):
            kwargs["password"] = holder.token
            return await super().connect(conninfo, **kwargs)

    async def _configure(conn: Any) -> None:
        await conn.execute(
            sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(
                _schema_identifier(schema_name)
            )
        )
        await apply_search_path(conn, schema_name)

    pool = AsyncConnectionPool(
        conninfo=conninfo,
        connection_class=_RotatingConnection,
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
        },
        configure=_configure,
        min_size=1,
        max_size=10,
        max_lifetime=float(settings.pool_recycle_seconds),
        open=False,
    )
    await pool.open()

    refresh_seconds = max(30, settings.token_refresh_seconds)

    async def _refresh_loop() -> None:
        while True:
            await asyncio.sleep(refresh_seconds)
            try:
                async with holder.lock:
                    holder.token = await asyncio.to_thread(_mint_token, workspace, endpoint)
                log.debug("lakebase oauth token refreshed")
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("lakebase oauth token refresh failed")

    refresh_task = asyncio.create_task(_refresh_loop(), name="lakebase-token-refresh")
    log.info(
        "lakebase pool open host={} db={} schema={} user={} recycle={}s refresh={}s",
        host,
        settings.lakebase_database,
        settings.lakebase_schema,
        username,
        settings.pool_recycle_seconds,
        refresh_seconds,
    )

    async def close() -> None:
        refresh_task.cancel()
        try:
            await refresh_task
        except asyncio.CancelledError:
            pass
        await pool.close()
        log.info("lakebase pool closed")

    return LakebasePoolHandle(pool=pool, close=close)
