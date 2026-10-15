"""Databricks chat models via Unity Catalog AI Gateway (visitor OBO, or CLI / app SP)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from databricks.sdk import WorkspaceClient
from databricks_langchain import ChatDatabricks

from shared.databricks_runtime import (
    RequestScopedWorkspaceClient,
    cli_profile,
    is_databricks_app,
    obo_is_bound,
    obo_token_scopes,
    request_workspace_client,
    workspace_client,
)
from shared.db.paths import uc_catalog
from shared.logger_global import get_logger

log = get_logger(__name__, service="ai_brain")

DEFAULT_PROFILE = "adb-7181820732839861"
LLM_MAX_RETRIES = 5
DEFAULT_MAX_TOKENS = 1024
_LLM_YAML = Path(__file__).with_name("llm.yaml")
_GATEWAY_SCOPE = "ai-gateway"
_LLM_SCHEMA = "ai_models"
_GATEWAY_PREFIX_BY_CATALOG = {
    "automation_d": "gw_dev",
    "automation_a": "gw_acc",
    "automation_p": "gw_prd",
}

ModelKind = Literal["fast", "thinking"]


def _usable_model_name(raw: str | None) -> str | None:
    """Accept catalog FQNs. Ignore leftover system.ai chat ids so they cannot win."""
    value = (raw or "").strip()
    if not value:
        return None
    if value.lower().startswith("system.ai."):
        log.warning("ignoring system.ai chat model env value={}", value)
        return None
    return value


def _catalog_gateway_fqn(short_name: str) -> str:
    """``{catalog}.ai_models.{prefix}_{short}_aut`` for the current environment."""
    catalog = (uc_catalog() or "").strip()
    if not catalog:
        raise RuntimeError(
            "MATE_UC_CATALOG is required to resolve catalog chat models "
            "(or DATABRICKS_HOST must match a known workspace)."
        )
    prefix = _GATEWAY_PREFIX_BY_CATALOG.get(catalog)
    if not prefix:
        raise RuntimeError(
            f"No AI Gateway prefix for catalog={catalog}. "
            "Expected automation_d, automation_a, or automation_p."
        )
    short = short_name.strip()
    if f".{_LLM_SCHEMA}." in short:
        return short
    return f"{catalog}.{_LLM_SCHEMA}.{prefix}_{short}_aut"


@lru_cache(maxsize=1)
def _load_model_names() -> dict[str, str]:
    """Read short names from ``llm.yaml``, then env FQNs, then compose catalog routes.

    Apps set ``DATABRICKS_FAST_MODEL`` / ``DATABRICKS_THINKING_MODEL`` from bundle
    vars to full ``{catalog}.ai_models.gw_*_aut`` ids. Local runs compose the
    same pattern from ``MATE_UC_CATALOG`` (or the host → catalog map).
    """
    with _LLM_YAML.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    models = data.get("models") or {}
    yaml_fast = models.get("fast_model")
    yaml_thinking = models.get("thinking_model")
    if not yaml_fast or not yaml_thinking:
        raise ValueError(
            f"{_LLM_YAML} must define models.fast_model and models.thinking_model"
        )
    shared = _usable_model_name(os.getenv("DATABRICKS_MODEL"))
    fast = _usable_model_name(os.getenv("DATABRICKS_FAST_MODEL")) or shared
    thinking = _usable_model_name(os.getenv("DATABRICKS_THINKING_MODEL")) or shared
    return {
        "fast": _as_gateway_name(fast, str(yaml_fast)),
        "thinking": _as_gateway_name(thinking, str(yaml_thinking)),
    }


def _as_gateway_name(value: str | None, yaml_short: str) -> str:
    raw = (value or yaml_short).strip()
    if f".{_LLM_SCHEMA}." in raw:
        return raw
    return _catalog_gateway_fqn(raw)


def get_fast_model_name() -> str:
    return _load_model_names()["fast"]


def get_thinking_model_name() -> str:
    return _load_model_names()["thinking"]


def get_extract_model_kind() -> ModelKind:
    """Model tier for the heavy extraction agents (vendor analyst, emit, matrix).

    Set ``MATE_EXTRACT_MODEL_KIND=fast`` to trade extraction depth for latency.
    Only the model object changes; agent, tool and middleware wiring is identical
    either way. Defaults to ``thinking``.
    """
    raw = (os.getenv("MATE_EXTRACT_MODEL_KIND", "") or "").strip().lower()
    if raw in ("fast", "thinking"):
        return raw  # type: ignore[return-value]
    if raw:
        log.warning("ignoring invalid MATE_EXTRACT_MODEL_KIND value={}", raw)
    return "thinking"


def get_workspace_client() -> WorkspaceClient:
    """Visitor OBO when X-Forwarded-Access-Token is bound; else app SP / CLI."""
    if obo_is_bound():
        log.debug("creating WorkspaceClient from visitor OBO token")
    elif is_databricks_app():
        log.debug("creating WorkspaceClient from Databricks Apps environment")
    else:
        log.debug("creating WorkspaceClient profile={}", cli_profile())
    return request_workspace_client()


def _require_gateway_scope() -> None:
    """Fail when a parseable visitor JWT is missing ai-gateway. Do not use system.ai."""
    scopes = obo_token_scopes()
    if not scopes:
        return
    if _GATEWAY_SCOPE not in set(scopes):
        raise RuntimeError(
            "Visitor OBO token is missing scope 'ai-gateway'. "
            "Catalog chat models require AI Gateway; "
            "refusing system.ai serving-endpoint fallback."
        )


def get_llm(kind: ModelKind = "fast", *, max_tokens: int | None = None) -> ChatDatabricks:
    """ChatDatabricks for Procura via the environment's ``ai_models`` gateway routes.

    Visitor OBO (``X-Forwarded-Access-Token``) uses ``RequestScopedWorkspaceClient``.
    Local / no OBO uses the CLI profile or app SP. Always ``use_ai_gateway=True``
    with the catalog FQN — never workspace Foundation Model serving endpoints.
    """
    names = _load_model_names()
    model = names[kind]
    if obo_is_bound():
        _require_gateway_scope()
        client: WorkspaceClient = RequestScopedWorkspaceClient()
    else:
        client = workspace_client()

    if max_tokens is None:
        max_tokens_raw = os.getenv("DATABRICKS_MAX_TOKENS", str(DEFAULT_MAX_TOKENS))
        try:
            max_tokens = int(max_tokens_raw)
        except ValueError:
            max_tokens = DEFAULT_MAX_TOKENS

    temperature_raw = os.getenv("DATABRICKS_TEMPERATURE")
    temperature: float | None = None
    if temperature_raw is not None and temperature_raw.strip() != "":
        temperature = float(temperature_raw)

    log.info(
        "creating ChatDatabricks kind={} model={} gateway=true max_tokens={} obo={} client={}",
        kind,
        model,
        max_tokens,
        obo_is_bound(),
        type(client).__name__,
    )

    kwargs: dict = {
        "model": model,
        "workspace_client": client,
        "use_ai_gateway": True,
        "max_tokens": max_tokens,
        "max_retries": LLM_MAX_RETRIES,
    }
    if temperature is not None:
        kwargs["temperature"] = temperature

    return ChatDatabricks(**kwargs)


def get_fast_llm() -> ChatDatabricks:
    return get_llm("fast")


def get_thinking_llm() -> ChatDatabricks:
    return get_llm("thinking")
