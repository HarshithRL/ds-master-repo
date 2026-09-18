"""Nexus MLflow AgentServer wrapping the Procura AI graph."""

from __future__ import annotations

import argparse
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

# Running as a script (``python ai_brain/brain_server.py``) puts ai_brain/ on
# sys.path instead of the repo root, so the package is not importable yet.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_brain.server.bootstrap import ensure_repo_root

_REPO_ROOT = ensure_repo_root()

from dotenv import load_dotenv

_ENV_PATH = _REPO_ROOT / ".env"
_loaded = load_dotenv(_ENV_PATH, override=False)

from shared.logger_global import get_logger, setup_logging

setup_logging(service="ai_brain")

log = get_logger(__name__, service="ai_brain")
_DI_NAMES = (
    "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT",
    "AZURE_DOCUMENT_INTELLIGENCE_KEY",
)
try:
    from shared.artifacts.parsers.azure_docintelligence import _credentials as _ensure_di

    _ensure_di()
except Exception as _di_exc:  # noqa: BLE001
    log.warning("azure DI credentials not ready yet: {}", _di_exc)
_di_status = {name: bool((__import__("os").getenv(name) or "").strip()) for name in _DI_NAMES}
log.info(
    "dotenv loaded path={} loaded={} azure_di_endpoint={} azure_di_key={}",
    str(_ENV_PATH),
    bool(_loaded or _ENV_PATH.is_file()),
    _di_status["AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT"],
    _di_status["AZURE_DOCUMENT_INTELLIGENCE_KEY"],
)

from ai_brain.server.tracing import configure_tracing

configure_tracing()

from ai_brain.server import agent as _agent_handlers  # noqa: F401  # registers @invoke/@stream
from ai_brain.server.middleware import install_middleware
from ai_brain.server.routes import register_routes
from ai_brain.server.runtime import runtime
from fastapi import FastAPI
from databricks_ai_bridge.long_running import LongRunningAgentServer
import mlflow

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8004


@asynccontextmanager
async def lifespan(_app: Any):
    await runtime.start()
    try:
        yield
    finally:
        await runtime.stop()
        try:
            mlflow.flush_trace_async_logging()
        except Exception:
            pass


class NexusAgentServer(LongRunningAgentServer):
    """Durable ResponsesAgent server backed by the app's existing Lakebase."""

    def __init__(self) -> None:
        # Apps already provide LAKEBASE_ENDPOINT for the LangGraph checkpointer.
        # AI Bridge expects the autoscaling spelling, so expose the same attached
        # resource before its route setup decides whether durability is enabled.
        endpoint = os.getenv("LAKEBASE_ENDPOINT", "").strip()
        if endpoint:
            os.environ.setdefault("LAKEBASE_AUTOSCALING_ENDPOINT", endpoint)
        super().__init__(
            "ResponsesAgent",
            db_autoscaling_endpoint=endpoint or None,
            task_timeout_seconds=float(os.getenv("BRAIN_RUN_TIMEOUT", "3600")),
        )
        self.app.title = "AI Brain Agent Server"
        self.app.description = "Durable MLflow ResponsesAgent wrapping the Nexus LangGraph"
        self.app.max_body_size = None

        # LongRunningAgentServer installs its Lakebase lifecycle. Compose it
        # with the graph/checkpointer lifecycle rather than replacing either.
        durable_lifespan = self.app.router.lifespan_context

        @asynccontextmanager
        async def combined_lifespan(app: Any):
            await runtime.start()
            try:
                async with durable_lifespan(app):
                    yield
            finally:
                await runtime.stop()
                try:
                    mlflow.flush_trace_async_logging()
                except Exception:
                    pass

        self.app.router.lifespan_context = combined_lifespan


agent_server = NexusAgentServer()
app = agent_server.app
install_middleware(app)
register_routes(app)


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Brain MLflow AgentServer")
    parser.add_argument("--host", default=os.getenv("BRAIN_HOST", DEFAULT_HOST))
    parser.add_argument("--port", type=int, default=int(os.getenv("BRAIN_PORT", str(DEFAULT_PORT))))
    args = parser.parse_args()
    import uvicorn

    log.info("starting ai_brain AgentServer on {}:{}", args.host, args.port)
    run_kwargs: dict[str, Any] = {
        "host": args.host,
        "port": args.port,
        "reload": False,
    }
    if sys.platform == "win32":
        # psycopg async (Lakebase STM/LTM) cannot use Windows ProactorEventLoop.
        run_kwargs["loop"] = "ai_brain.server.lakebase:psycopg_loop_factory"
    uvicorn.run(
        "ai_brain.brain_server:app",
        **run_kwargs,
    )


if __name__ == "__main__":
    main()
