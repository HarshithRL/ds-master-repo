"""Procura AI procurement subgraph."""

from __future__ import annotations

from typing import Any

__all__ = ["deepagent", "main_agent"]


def __getattr__(name: str) -> Any:
    if name == "deepagent":
        from ai_brain.core.procurement_ai.subagents.deepagents import deepagent

        return deepagent
    if name == "main_agent":
        from ai_brain.core.procurement_ai.subagents.main_agent import main_agent

        return main_agent
    raise AttributeError(f"module {name!r} has no attribute {name}")
