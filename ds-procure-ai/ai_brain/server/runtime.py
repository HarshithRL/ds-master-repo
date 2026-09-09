"""Process-wide compiled Nexus graph, checkpointer, and store."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from ai_brain.nexus_graph import build_nexes_graph
from ai_brain.server.checkpointer import CheckpointHandle, open_checkpointer
from shared.logger_global import get_logger

log = get_logger(__name__, service="ai_brain")


class GraphRuntime:
    graph: Any = None
    checkpointer: Any = None
    store: Any = None
    semaphore: asyncio.Semaphore | None = None
    ready: bool = False
    _handle: CheckpointHandle | None = None

    async def start(self) -> None:
        self._handle = await open_checkpointer()
        self.checkpointer = self._handle.saver
        self.store = self._handle.store
        self.graph = build_nexes_graph(checkpointer=self.checkpointer, store=self.store)
        max_runs = max(1, int(os.getenv("BRAIN_MAX_CONCURRENT_RUNS", "8")))
        self.semaphore = asyncio.Semaphore(max_runs)
        self.ready = True
        log.info("nexus graph compiled concurrent_runs={}", max_runs)

    async def stop(self) -> None:
        self.ready = False
        self.graph = None
        self.checkpointer = None
        self.store = None
        if self._handle is not None:
            await self._handle.aclose()
        self._handle = None
        log.info("nexus graph runtime stopped")


runtime = GraphRuntime()
