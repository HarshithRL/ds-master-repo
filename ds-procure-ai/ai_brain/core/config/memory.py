"""Lakebase STM/LTM settings from ``memory.yaml`` (env vars override)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from shared.logger_global import get_logger

log = get_logger(__name__, service="ai_brain")

_MEMORY_YAML = Path(__file__).with_name("memory.yaml")


@dataclass(frozen=True)
class MemorySettings:
    checkpoint_backend: str
    store_backend: str
    lakebase_endpoint: str
    lakebase_schema: str
    lakebase_database: str
    lakebase_host: str
    sslmode: str
    pool_recycle_seconds: int
    token_refresh_seconds: int
    config_profile: str
    embedding_endpoint: str
    embedding_dims: int


def _as_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip() or default


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _env_or(name: str, yaml_value: str) -> str:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return yaml_value
    return str(raw).strip()


@lru_cache(maxsize=1)
def _load_yaml() -> dict[str, Any]:
    with _MEMORY_YAML.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{_MEMORY_YAML} must contain a mapping")
    return data


@lru_cache(maxsize=1)
def get_memory_settings() -> MemorySettings:
    """Effective memory config: YAML defaults, then env vars with the mapped names."""
    data = _load_yaml()
    checkpoint = data.get("checkpoint") or {}
    store = data.get("store") or {}
    lakebase = data.get("lakebase") or {}
    databricks = data.get("databricks") or {}

    yaml_host = _as_str(lakebase.get("host"))
    settings = MemorySettings(
        checkpoint_backend=_env_or(
            "BRAIN_CHECKPOINT_BACKEND", _as_str(checkpoint.get("backend"), "lakebase")
        ).lower(),
        store_backend=_env_or(
            "BRAIN_STORE_BACKEND", _as_str(store.get("backend"), "lakebase")
        ).lower(),
        lakebase_endpoint=_env_or(
            "LAKEBASE_ENDPOINT", _as_str(lakebase.get("endpoint"))
        ),
        lakebase_schema=_env_or("LAKEBASE_SCHEMA", _as_str(lakebase.get("schema"), "mate_agent")),
        lakebase_database=_env_or(
            "PGDATABASE", _as_str(lakebase.get("database"), "databricks_postgres")
        ),
        lakebase_host=_env_or("PGHOST", yaml_host),
        sslmode=_env_or("PGSSLMODE", _as_str(lakebase.get("sslmode"), "require")),
        pool_recycle_seconds=_as_int(
            os.getenv("BRAIN_POOL_RECYCLE_SECONDS") or lakebase.get("pool_recycle_seconds"),
            3000,
        ),
        token_refresh_seconds=_as_int(
            os.getenv("BRAIN_TOKEN_REFRESH_SECONDS") or lakebase.get("token_refresh_seconds"),
            2400,
        ),
        config_profile=_env_or(
            "DATABRICKS_CONFIG_PROFILE",
            _as_str(databricks.get("config_profile"), "adb-7181820732839861"),
        ),
        embedding_endpoint=_env_or(
            "DATABRICKS_EMBEDDING_ENDPOINT",
            _as_str(databricks.get("embedding_endpoint"), "databricks-gte-large-en"),
        ),
        embedding_dims=_as_int(
            os.getenv("DATABRICKS_EMBEDDING_DIMS") or databricks.get("embedding_dims"),
            1024,
        ),
    )
    log.debug(
        "memory settings checkpoint={} store={} schema={} endpoint={}",
        settings.checkpoint_backend,
        settings.store_backend,
        settings.lakebase_schema,
        settings.lakebase_endpoint,
    )
    return settings


def search_path_options(schema: str | None = None) -> str:
    """libpq ``options`` value that sets ``search_path`` for the mate_agent schema."""
    name = (schema or get_memory_settings().lakebase_schema or "mate_agent").strip()
    return f"-csearch_path={name}"
