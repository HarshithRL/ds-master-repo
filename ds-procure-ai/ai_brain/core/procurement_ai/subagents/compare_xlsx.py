from __future__ import annotations

from typing import Any, Optional

import mlflow
from langchain_core.runnables import RunnableConfig
from mlflow.entities import SpanType

from ai_brain.core.procurement_ai.capabilities import project_id_from_state
from ai_brain.core.procurement_ai.insights import build_insight_payload
from ai_brain.core.procurement_ai.packs import store as pack_store
from ai_brain.core.procurement_ai.packs.compare_xlsx import build_comparison_xlsx
from ai_brain.core.procurement_ai.project_context import load_context
from ai_brain.server.tracing import is_checkpoint_sync_error


@mlflow.trace(name="procura_compare_xlsx", span_type=SpanType.TOOL)
async def compare_xlsx(
    state: dict[str, Any],
    config: Optional[RunnableConfig] = None,  # noqa: UP045
) -> dict[str, Any]:
    project_id = project_id_from_state(state)
    if not project_id:
        return {
            "procurement": {
                "compare_xlsx": "project_id missing",
                "xlsx_status": "blocked",
                "evidence_used": False,
            }
        }
    if pack_store.kb_is_building(project_id):
        return {
            "procurement": {
                "compare_xlsx": "kb still building",
                "xlsx_status": "running",
                "xlsx_href": "",
                "evidence_used": False,
            }
        }
    project, artifacts, chunks = load_context(project_id)
    if project is None:
        return {
            "procurement": {
                "compare_xlsx": "project not found",
                "xlsx_status": "blocked",
                "evidence_used": False,
            }
        }
    # W8: pack reads evidence + pricing_line from SQL; no LLM in the xlsx path.
    insights = build_insight_payload(project, artifacts, chunks)
    thread_id = ""
    if isinstance(config, dict):
        thread_id = str((config.get("configurable") or {}).get("thread_id") or "")
    try:
        result = build_comparison_xlsx(
            project_id,
            insights,
            thread_id=thread_id,
        )
    except Exception as exc:  # noqa: BLE001
        if is_checkpoint_sync_error(exc):
            pack_store.write_status(
                project_id,
                "xlsx",
                status="failed",
                error=str(exc),
                thread_id=thread_id or None,
            )
        raise
    href = result.get("href") or ""
    status = result.get("status") or "blocked"
    if href:
        reply = (
            "Comparison workbook is ready. "
            "Rows that do not apply to this process type are N/A. "
            "Unevidenced cells are ?. Scorecard is left for the Etex team. "
            f"Download: {href}"
        )
    else:
        reply = f"Comparison workbook was not written ({status})."
    return {
        "procurement": {
            "compare_xlsx": status,
            "xlsx_status": status,
            "xlsx_href": href,
            "evidence_used": bool(result.get("evidence_used")),
            "assistant_reply": reply,
        }
    }
