from __future__ import annotations

from typing import Any, Optional

import mlflow
from langchain_core.runnables import RunnableConfig
from mlflow.entities import SpanType

from ai_brain.core.procurement_ai.capabilities import project_id_from_state
from ai_brain.core.procurement_ai.packs.steerco_ppt import build_steerco_ppt


@mlflow.trace(name="procura_steerco_ppt", span_type=SpanType.TOOL)
async def steerco_ppt(
    state: dict[str, Any],
    config: Optional[RunnableConfig] = None,  # noqa: UP045
) -> dict[str, Any]:
    project_id = project_id_from_state(state)
    if not project_id:
        return {
            "procurement": {
                "steerco_ppt": "project_id missing",
                "ppt_status": "blocked",
            }
        }
    thread_id = ""
    if isinstance(config, dict):
        thread_id = str((config.get("configurable") or {}).get("thread_id") or "")
    # W8: pack reads evidence + pricing_line from SQL; no LLM in the pptx path.
    result = build_steerco_ppt(project_id, thread_id=thread_id)
    return {
        "procurement": {
            "steerco_ppt": result.get("status"),
            "ppt_status": result.get("status"),
            "ppt_href": result.get("href") or "",
        }
    }
