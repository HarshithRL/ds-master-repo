"""Databricks chat model via AI Gateway (Apps OAuth M2M, or CLI profile locally)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from databricks.sdk import WorkspaceClient
from databricks_langchain import ChatDatabricks

from shared.databricks_runtime import cli_profile, is_databricks_app, workspace_client
from shared.logger_global import get_logger

log = get_logger(__name__, service="ai_brain")

DEFAULT_PROFILE = "adb-7181820732839861"
DEFAULT_MODEL = "automation_d.ai_models.gw_dev_claude-sonnet-4-6_aut"
DEFAULT_MAX_TOKENS = 1024
_LLM_YAML = Path(__file__).with_name("llm.yaml")

ModelKind = Literal["fast", "thinking"]


@lru_cache(maxsize=1)
def _load_model_names() -> dict[str, str]:
    """Read ``fast_model`` / ``thinking_model`` from ``llm.yaml``."""
    with _LLM_YAML.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    models = data.get("models") or {}
    fast = models.get("fast_model")
    thinking = models.get("thinking_model")
    if not fast or not thinking:
        raise ValueError(
            f"{_LLM_YAML} must define models.fast_model and models.thinking_model"
        )
    return {"fast": str(fast), "thinking": str(thinking)}


def get_fast_model_name() -> str:
    return _load_model_names()["fast"]


def get_thinking_model_name() -> str:
    return _load_model_names()["thinking"]


def get_workspace_client() -> WorkspaceClient:
    """WorkspaceClient: Apps service principal in the app runtime, CLI profile locally."""
    if is_databricks_app():
        log.debug("creating WorkspaceClient from Databricks Apps environment")
    else:
        log.debug("creating WorkspaceClient profile={}", cli_profile())
    return workspace_client()


def get_llm(kind: ModelKind = "fast", *, max_tokens: int | None = None) -> ChatDatabricks:
    """
    ChatDatabricks pointed at Unity AI Gateway MLflow path.

    ``kind`` selects the model id from ``llm.yaml``:
    - ``fast`` → ``models.fast_model``
    - ``thinking`` → ``models.thinking_model``

    Routes to ``{host}/ai-gateway/mlflow/v1`` — same surface as:
    ``POST /ai-gateway/mlflow/v1/chat/completions``.
    """
    names = _load_model_names()
    model = os.getenv("DATABRICKS_MODEL") or names.get(kind) or DEFAULT_MODEL

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

    log.debug("creating ChatDatabricks kind={} model={} max_tokens={}", kind, model, max_tokens)

    kwargs: dict = {
        "model": model,
        "workspace_client": get_workspace_client(),
        "use_ai_gateway": True,
        "max_tokens": max_tokens,
    }
    if temperature is not None:
        kwargs["temperature"] = temperature

    return ChatDatabricks(**kwargs)


def get_fast_llm() -> ChatDatabricks:
    return get_llm("fast")


def get_thinking_llm() -> ChatDatabricks:
    return get_llm("thinking")
