"""Run kb_build. Excel is written only when write_xlsx=True (off by default)."""

from __future__ import annotations

import asyncio
import os

from ai_brain.core.procurement_ai.insights import build_insight_payload
from ai_brain.core.procurement_ai.packs import store as pack_store
from ai_brain.core.procurement_ai.packs.compare_xlsx import build_comparison_xlsx
from ai_brain.core.procurement_ai.procura_graph import build_procura_ai
from ai_brain.core.procurement_ai.project_context import load_context
from shared.logger_global import get_logger

log = get_logger(__name__, service="ai_brain")

# All bids fan out at once, and a 5-bid project shares one workspace tokens-per-
# minute quota: a whole vendor came back as 40 extraction_failed 429s. Bounded
# fan-out trades build time for completeness.
KB_BID_CONCURRENCY = max(1, int(os.getenv("MATE_KB_BID_CONCURRENCY", "3")))

_KB_BUILD_INPUT = {
    "request": "kb_build",
    "capability": "kb_build",
    "messages": [],
}


async def arun_kb_build(project_id: str, *, write_xlsx: bool = False) -> dict:
    pack_store.write_kb_job(
        project_id,
        status="building",
        message="Extracting vendor evidence from uploaded files…",
    )
    from ai_brain.core.kb.skills.sync import ensure_skills_store

    graph = build_procura_ai(store=ensure_skills_store())
    try:
        state = await graph.ainvoke(
            {
                **_KB_BUILD_INPUT,
                "project_id": project_id,
                "procurement": {"capability": "kb_build", "project_id": project_id},
            },
            config={"max_concurrency": KB_BID_CONCURRENCY},
        )
    except Exception as exc:
        pack_store.write_kb_job(
            project_id,
            status="failed",
            message="Knowledge base build failed.",
            error=str(exc),
        )
        raise
    procurement = state.get("procurement") or {}
    kb_status = str(procurement.get("kb_status") or "").strip()
    audit = dict(procurement.get("kb_audit") or {})
    # Trust the stored rows, not the state hand-off: nodes after audit_kb can
    # drop kb_status, and "absent" must never be read as "ready".
    failed_bids = _failed_bid_count(project_id)
    if failed_bids:
        audit["failed"] = max(int(audit.get("failed") or 0), failed_bids)
    failed = int(audit.get("failed") or 0)
    if kb_status not in {"ready", "needs_review", "staged"}:
        kb_status = "needs_review" if failed else "ready"
    if failed and kb_status == "ready":
        kb_status = "needs_review"
    pack_store.write_kb_job(
        project_id,
        status=kb_status,
        message=_finish_message(kb_status, audit),
        error=None,
    )
    xlsx = None
    if write_xlsx:
        project, artifacts, chunks = load_context(project_id)
        if project is not None:
            insights = build_insight_payload(project, artifacts, chunks or [])
            xlsx = build_comparison_xlsx(project_id, insights)
    log.info(
        "kb_build finished project_id={} bundles={} xlsx={}",
        project_id,
        audit,
        (xlsx or {}).get("evidence_used"),
    )
    return {"state": state, "xlsx": xlsx}


def run_kb_build(project_id: str, *, write_xlsx: bool = False) -> dict:
    from ai_brain.core.kb.extract.notes_corpus import materialize_notes

    materialize_notes(project_id)
    return asyncio.run(arun_kb_build(project_id, write_xlsx=write_xlsx))


def _failed_bid_count(project_id: str) -> int:
    """Bids whose evidence is extraction_failed, straight from the rows."""
    try:
        from ai_brain.core.kb.store.persist import kb_counts

        return int(kb_counts(project_id).get("failed_bids") or 0)
    except Exception:  # noqa: BLE001
        log.exception("failed-bid count unavailable project_id={}", project_id)
        return 0


def _finish_message(status: str, audit: dict) -> str:
    bundles = int(audit.get("bundle_count") or 0)
    failed = int(audit.get("failed") or 0)
    if status == "ready":
        return f"Knowledge base ready · {bundles} bid(s)."
    if status == "needs_review":
        return f"Knowledge base needs review · {failed} bid(s) failed."
    if status == "staged":
        return "Files parsed. No vendor bids to extract yet."
    return "Knowledge base updated."
