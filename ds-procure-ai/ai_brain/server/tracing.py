"""MLflow tracing for AI Brain — autolog LangChain/LangGraph, session metadata."""

from __future__ import annotations

import os
from typing import Any

import mlflow
from mlflow.genai.agent_server import setup_mlflow_git_based_version_tracking

from shared.logger_global import get_logger

log = get_logger(__name__, service="ai_brain")

_configured = False


def configure_tracing() -> None:
    """Enable LangChain autolog and tracking. Call before importing agent graphs.

    Honors ``MLFLOW_TRACKING_URI`` / ``MLFLOW_EXPERIMENT_ID`` when already set.
    On Databricks Apps, defaults tracking URI to ``databricks``. Locally uses
    MLflow's default file store and experiment ``ai_brain`` unless overridden.

    ``mlflow.langchain.autolog(run_tracer_inline=True)`` is required so
    ``MlflowLangchainTracer`` runs on the LangGraph async task and nests with
    manual ``start_span`` / ``@mlflow.trace`` around ``astream`` / ``ainvoke``.
    """
    global _configured
    if _configured:
        return

    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "").strip()
    if not tracking_uri and (
        os.getenv("DATABRICKS_APP_NAME") or os.getenv("DATABRICKS_RUNTIME_VERSION")
    ):
        mlflow.set_tracking_uri("databricks")

    if os.getenv("MLFLOW_EXPERIMENT_ID", "").strip():
        pass
    else:
        experiment_name = os.getenv("MLFLOW_EXPERIMENT_NAME", "").strip() or "ai_brain"
        try:
            _bind_experiment(experiment_name)
        except Exception:
            log.warning("mlflow experiment bind skipped name={}", experiment_name)

    async_flag = os.getenv("MLFLOW_ENABLE_ASYNC_LOGGING", "true").strip().lower()
    if async_flag not in {"0", "false", "no", "off"}:
        mlflow.config.enable_async_logging(True)

    # Before LangChain/LangGraph agent imports. Inline tracer: LangGraph ainvoke/astream.
    mlflow.langchain.autolog(log_traces=True, run_tracer_inline=True)
    try:
        setup_mlflow_git_based_version_tracking()
    except Exception:
        log.warning("mlflow git version tracking skipped")

    _configured = True
    log.info(
        "mlflow tracing configured experiment={}",
        os.getenv("MLFLOW_EXPERIMENT_NAME", "").strip() or "ai_brain",
    )


def _bind_experiment(experiment_name: str) -> None:
    catalog = os.getenv("MLFLOW_UC_CATALOG", "").strip()
    schema = os.getenv("MLFLOW_UC_SCHEMA", "").strip()
    prefix = os.getenv("MLFLOW_UC_TABLE_PREFIX", "").strip()
    warehouse = os.getenv("MLFLOW_TRACING_SQL_WAREHOUSE_ID", "").strip()
    if catalog and schema and prefix and warehouse:
        from mlflow.entities.trace_location import UnityCatalog

        mlflow.set_experiment(
            experiment_name=experiment_name,
            trace_location=UnityCatalog(
                catalog_name=catalog,
                schema_name=schema,
                table_prefix=prefix,
            ),
        )
        return
    tracking_uri = (os.getenv("MLFLOW_TRACKING_URI") or "").strip().lower()
    if tracking_uri == "databricks" and not experiment_name.startswith("/"):
        experiment_name = f"/Shared/ds-procure-ai/{experiment_name}"
    mlflow.set_experiment(experiment_name)


def langchain_callbacks() -> list[Any]:
    """MLflow LangChain callback with inline async context (same as autolog)."""
    from mlflow.langchain.langchain_tracer import MlflowLangchainTracer

    return [MlflowLangchainTracer(run_inline=True)]


def _as_callback_list(raw: Any) -> list[Any]:
    """LangChain may pass a list or an AsyncCallbackManager, not both."""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        return list(raw)
    handlers = getattr(raw, "handlers", None)
    if handlers is None:
        handlers = getattr(raw, "inheritable_handlers", None)
    if handlers is not None:
        return list(handlers)
    return [raw]


def _has_mlflow_tracer(callbacks: list[Any]) -> bool:
    from mlflow.langchain.langchain_tracer import MlflowLangchainTracer

    for item in callbacks:
        if isinstance(item, MlflowLangchainTracer):
            return True
        handlers = getattr(item, "handlers", None) or getattr(
            item, "inheritable_handlers", None
        )
        if handlers and any(isinstance(h, MlflowLangchainTracer) for h in handlers):
            return True
    return False


_CHECKPOINT_CONFIG_KEYS = frozenset(
    {"checkpoint_id", "checkpoint_ns", "checkpoint_map", "__pregel_checkpointer"}
)


def is_checkpoint_sync_error(exc: BaseException) -> bool:
    """True when AsyncSqliteSaver was called via graph.invoke() on the event-loop thread."""
    text = str(exc).lower()
    return "asyncsqlitesaver" in text and "synchronous" in text


def child_runnable_config(config: dict[str, Any] | None) -> dict[str, Any]:
    """Config for nested ``ainvoke``: MLflow callbacks, no parent AsyncSqliteSaver.

    LangGraph/LangChain do not always propagate callbacks into nested compiled
    graphs invoked from a Python node. Passing this config nests LLM spans
    under the AgentServer / ``nexus_graph`` span.

    Nested ``create_agent`` / ``create_deep_agent`` graphs are compiled with
    ``checkpointer=None``. Dropping parent checkpoint keys prevents
    ``Synchronous calls to AsyncSqliteSaver are only allowed from a different thread``.

    After stripping parent checkpoint state we still set ``checkpoint_ns`` so
    LangGraph nested runs do not KeyError on a missing ns (deepagents + nested
    checkpointer=None). Keep the same ``thread_id``; use ns ``nested`` rather
    than resuming the parent checkpoint map/id.
    """
    merged: dict[str, Any] = dict(config or {})
    callbacks = _as_callback_list(merged.get("callbacks"))
    if not _has_mlflow_tracer(callbacks):
        callbacks.extend(langchain_callbacks())
    merged["callbacks"] = callbacks
    merged.pop("checkpointer", None)
    configurable = dict(merged.get("configurable") or {})
    for key in _CHECKPOINT_CONFIG_KEYS:
        configurable.pop(key, None)
    # Parent ns/id/map stripped above; nested agents need the key present.
    configurable["checkpoint_ns"] = "nested"
    merged["configurable"] = configurable
    return merged



def bind_run_trace(*, thread_id: str, user_id: str = "anonymous") -> None:
    """Attach session/user metadata to the active MLflow trace."""
    try:
        mlflow.update_current_trace(
            metadata={
                "mlflow.trace.session": thread_id,
                "mlflow.trace.user": user_id,
            }
        )
    except Exception:
        return
    span = mlflow.get_current_active_span()
    if span is not None:
        span.set_attributes({"thread_id": thread_id, "user_id": user_id})
