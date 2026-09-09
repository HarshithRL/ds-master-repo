"""Studio exports must remain independent from the application runtime."""

from __future__ import annotations

import asyncio


def test_studio_exports_compile_and_skip_without_runtime():
    from ai_brain.studio import nexus, procura

    async def run():
        result = await nexus.ainvoke(
            {
                "request": "skip",
                "project_id": "studio-project",
                "procurement": {"mainagent": False, "deepagent": False},
                "messages": [{"role": "user", "content": "skip"}],
            }
        )
        assert result["route"] == "skip"

    assert nexus.name == "nexus"
    assert procura.name == "procura"
    asyncio.run(run())
