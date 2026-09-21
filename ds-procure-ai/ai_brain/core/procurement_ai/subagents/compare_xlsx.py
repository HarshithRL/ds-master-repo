from __future__ import annotations

import asyncio
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
from shared.logger_global import get_logger

log = get_logger(__name__, service="ai_brain")


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
    await _ensure_corpus(project_id)
    project, artifacts, chunks = await asyncio.to_thread(load_context, project_id)
    if project is None:
        return {
            "procurement": {
                "compare_xlsx": "project not found",
                "xlsx_status": "blocked",
                "evidence_used": False,
            }
        }
    parsed_ok = [a for a in artifacts if (getattr(a, "parse_status", "") or "") == "ok"]
    if not parsed_ok:
        return {
            "procurement": {
                "compare_xlsx": "no parsed files",
                "xlsx_status": "blocked",
                "xlsx_href": "",
                "evidence_used": False,
                "assistant_reply": "Upload vendor / RFP files and wait for parse before building the matrix.",
            }
        }
    from ai_brain.core.kb.build.pipeline import ensure_vendor_bids
    from ai_brain.core.procurement_ai.subagents.comparison_matrix import (
        extract_comparison_matrix,
    )

    await asyncio.to_thread(ensure_vendor_bids, project_id)
    insights = await asyncio.to_thread(build_insight_payload, project, artifacts, chunks)
    thread_id = ""
    if isinstance(config, dict):
        thread_id = str((config.get("configurable") or {}).get("thread_id") or "")
    matrix = None
    agent_error: str | None = None
    try:
        matrix = await extract_comparison_matrix(project_id, insights, config=config)
    except Exception as exc:  # noqa: BLE001
        if is_checkpoint_sync_error(exc):
            # Still attempt a template workbook before re-raising checkpoint sync.
            try:
                await asyncio.to_thread(
                    build_comparison_xlsx,
                    project_id,
                    insights,
                    thread_id=thread_id,
                    matrix=None,
                )
            except Exception:
                log.exception("template xlsx after checkpoint sync failed project_id={}", project_id)
            pack_store.write_status(
                project_id,
                "xlsx",
                status="failed",
                error=str(exc),
                thread_id=thread_id or None,
                href=pack_store.flask_href(project_id, "xlsx"),
                filename="comparison_matrix.xlsx",
            )
            raise
        log.exception("comparison matrix agent failed project_id={}", project_id)
        agent_error = str(exc) or exc.__class__.__name__
    try:
        result = await asyncio.to_thread(
            build_comparison_xlsx,
            project_id,
            insights,
            thread_id=thread_id,
            matrix=matrix,
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
    href = result.get("href") or pack_store.flask_href(project_id, "xlsx") or ""
    status = result.get("status") or "blocked"
    pack_error = result.get("error")
    if agent_error is not None:
        # Keep workbook downloadable: template + Download href, surface agent error in message.
        status = result.get("status") or "template"
        pack_error = agent_error
        pack_store.write_status(
            project_id,
            "xlsx",
            status=status,
            href=href or None,
            filename=result.get("filename") or "comparison_matrix.xlsx",
            thread_id=thread_id or None,
            error=f"Comparison agent failed: {agent_error}",
        )
        reply = (
            f"Comparison agent failed: {agent_error}. "
            + (
                f"A template workbook was written (extraction_failed / unevidenced cells). Download: {href}"
                if href
                else "No comparison workbook was produced."
            )
        )
    elif status == "template":
        detail = f" ({pack_error})" if pack_error else ""
        reply = (
            f"Comparison workbook is a template only{detail}. "
            "Unevidenced cells are ?. Scorecard is left for the Etex team."
            + (f" Download: {href}" if href else "")
        )
    elif href:
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
            "evidence_used": bool(result.get("evidence_used")) and agent_error is None,
            "assistant_reply": reply,
        }
    }


async def _ensure_corpus(project_id: str) -> None:
    from ai_brain.core.kb.extract.ingest import ensure_parsed_for_matrix

    await ensure_parsed_for_matrix(project_id)
