"""Compatibility alias after rename to ``main_agent``."""

from __future__ import annotations

from typing import Any

from ai_brain.core.procurement_ai.subagents.main_agent import main_agent

vendor_agent = main_agent
vendor_comparison = main_agent

__all__ = [
    "main_agent",
    "procura_main_agent",
    "vendor_agent",
    "vendor_comparison",
    "vendor_comparison_agent",
]


def __getattr__(name: str) -> Any:
    if name in {"procura_main_agent", "vendor_comparison_agent"}:
        from ai_brain.core.procurement_ai.subagents.main_agent import get_procura_main_agent

        return get_procura_main_agent()
    raise AttributeError(f"module {__name__!r} has no attribute {name}")
