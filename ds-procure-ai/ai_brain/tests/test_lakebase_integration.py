"""Lakebase saver/store smoke — skipped unless env or Databricks profile is available."""

from __future__ import annotations

import os
import uuid
from functools import lru_cache
from typing import TypedDict

import pytest

_PROFILE = "adb-7181820732839861"


@lru_cache(maxsize=1)
def _databricks_profile_works() -> bool:
    try:
        from databricks.sdk import WorkspaceClient

        client = WorkspaceClient(profile=_PROFILE)
        client.current_user.me()
        return True
    except Exception:
        return False


def _lakebase_smoke_ready() -> bool:
    if os.getenv("BRAIN_LAKEBASE_SMOKE", "").strip() == "1":
        return True
    return _databricks_profile_works()


@pytest.mark.asyncio
async def test_lakebase_saver_store_roundtrip():
    if not _lakebase_smoke_ready():
        pytest.skip(
            "Lakebase smoke disabled (set BRAIN_LAKEBASE_SMOKE=1) and "
            f"Databricks profile {_PROFILE} is unavailable"
        )

    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from langgraph.graph import END, START, StateGraph
    from langgraph.store.postgres.aio import AsyncPostgresStore

    from ai_brain.server.lakebase import open_lakebase_pool

    pool_handle = await open_lakebase_pool()
    thread_id = f"lakebase-smoke-{uuid.uuid4()}"
    namespace = ("smoke", thread_id, "memories")
    key = "roundtrip"
    try:
        saver = AsyncPostgresSaver(conn=pool_handle.pool)
        await saver.setup()
        store = AsyncPostgresStore(conn=pool_handle.pool)
        await store.setup()

        await store.aput(namespace, key, {"text": "lakebase-smoke"})
        item = await store.aget(namespace, key)
        assert item is not None
        assert item.value["text"] == "lakebase-smoke"

        class CounterState(TypedDict):
            n: int

        def inc(state: CounterState) -> dict:
            return {"n": int(state["n"]) + 1}

        builder = StateGraph(CounterState)
        builder.add_node("inc", inc)
        builder.add_edge(START, "inc")
        builder.add_edge("inc", END)
        graph = builder.compile(checkpointer=saver)
        config = {"configurable": {"thread_id": thread_id}}
        result = await graph.ainvoke({"n": 0}, config)
        assert result["n"] == 1

        restored = builder.compile(checkpointer=saver)
        snapshot = await restored.aget_state(config)
        assert snapshot.values["n"] == 1
    finally:
        await pool_handle.close()
