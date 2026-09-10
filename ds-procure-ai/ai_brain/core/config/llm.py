"""Databricks chat model via AI Gateway (visitor OBO, or app SP / CLI fallback)."""

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
from shared.logger_global import get_logger

log = get_logger(__name__, service="ai_brain")

DEFAULT_PROFILE = "adb-7181820732839861"
DEFAULT_MODEL = "system.ai.claude-opus-4-5"
DEFAULT_MAX_TOKENS = 1024
_LLM_YAML = Path(__file__).with_name("llm.yaml")
# Retired Unity Gateway model-service ids. Env leftover from older deploys
# must not override llm.yaml (that 404 is "I could not generate a reply").
_RETIRED_MODEL_MARKERS = (
    "automation_d.ai_models.",
    "automation_a.ai_models.",
    "automation_p.ai_models.",
    "gw_dev_claude",
)
_GATEWAY_SCOPE = "ai-gateway"
_SERVING_SCOPES = frozenset({"model-serving", "serving.serving-endpoints"})
_SERVING_ENDPOINTS: dict[str, str] = {
    "fast": "databricks-claude-sonnet-4-5",
    "thinking": "databricks-claude-opus-4-6",
}

ModelKind = Literal["fast", "thinking"]


def _usable_model_name(raw: str | None) -> str | None:
    value = (raw or "").strip()
    if not value:
        return None
    lowered = value.lower()
    if any(marker in lowered for marker in _RETIRED_MODEL_MARKERS):
        log.warning("ignoring retired DATABRICKS_* model env value={}", value)
        return None
    return value


@lru_cache(maxsize=1)
def _load_model_names() -> dict[str, str]:
    """Read ``fast_model`` / ``thinking_model`` from env, then ``llm.yaml``.

    Apps set ``DATABRICKS_FAST_MODEL`` / ``DATABRICKS_THINKING_MODEL`` (and
    ``DATABRICKS_MODEL``) from bundle vars. Defaults are workspace Foundation
    Model APIs under ``system.ai`` (same names on D/T/A/P).
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
    fast = (
        _usable_model_name(os.getenv("DATABRICKS_FAST_MODEL"))
        or shared
        or str(yaml_fast)
    )
    thinking = (
        _usable_model_name(os.getenv("DATABRICKS_THINKING_MODEL"))
        or shared
        or str(yaml_thinking)
    )
    return {"fast": fast, "thinking": thinking}


def get_fast_model_name() -> str:
    return _load_model_names()["fast"]


def get_thinking_model_name() -> str:
    return _load_model_names()["thinking"]


def _serving_endpoint_name(kind: ModelKind) -> str:
    env_key = (
        "DATABRICKS_FAST_ENDPOINT" if kind == "fast" else "DATABRICKS_THINKING_ENDPOINT"
    )
    return (os.getenv(env_key) or "").strip() or _SERVING_ENDPOINTS[kind]


def get_workspace_client() -> WorkspaceClient:
    """Visitor OBO when X-Forwarded-Access-Token is bound; else app SP / CLI."""
    if obo_is_bound():
        log.debug("creating WorkspaceClient from visitor OBO token")
    elif is_databricks_app():
        log.debug("creating WorkspaceClient from Databricks Apps environment")
    else:
        log.debug("creating WorkspaceClient profile={}", cli_profile())
    return request_workspace_client()


def get_llm(kind: ModelKind = "fast", *, max_tokens: int | None = None) -> ChatDatabricks:
    """
    ChatDatabricks for Procura.

    Prefer Unity AI Gateway ``system.ai.*`` with visitor
    ``X-Forwarded-Access-Token`` when that JWT includes ``ai-gateway``.
    Otherwise use the attached Foundation Model serving endpoints (app SP
    unless the token already has ``model-serving`` /
    ``serving.serving-endpoints``). Cached agents keep the first path;
    serving endpoints are the safe default until visitors re-consent.
    """
    names = _load_model_names()
    scopes = set(obo_token_scopes())
    use_ai_gateway = obo_is_bound() and _GATEWAY_SCOPE in scopes
    if use_ai_gateway:
        model = names.get(kind) or DEFAULT_MODEL
        client: WorkspaceClient = RequestScopedWorkspaceClient()
    else:
        model = _serving_endpoint_name(kind)
        if obo_is_bound() and scopes & _SERVING_SCOPES:
            client = RequestScopedWorkspaceClient()
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
        "creating ChatDatabricks kind={} model={} gateway={} max_tokens={} obo={} client={}",
        kind,
        model,
        use_ai_gateway,
        max_tokens,
        obo_is_bound(),
        type(client).__name__,
    )

    kwargs: dict = {
        "model": model,
        "workspace_client": client,
        "use_ai_gateway": use_ai_gateway,
        "max_tokens": max_tokens,
    }
    if temperature is not None:
        kwargs["temperature"] = temperature

    return ChatDatabricks(**kwargs)


def get_fast_llm() -> ChatDatabricks:
    return get_llm("fast")


def get_thinking_llm() -> ChatDatabricks:
    return get_llm("thinking")
