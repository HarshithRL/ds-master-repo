"""KB-build graph nodes: seed requirements, Send vendor_analyst, persist SQL."""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, Optional

from langchain_core.runnables import RunnableConfig
from langgraph.types import Send

from ai_brain.core.kb.store.materialize import list_bid_ids, vendor_paths
from ai_brain.core.kb.store.persist import (
    fill_extraction_failed,
    seed_swift_requirements,
    upsert_bid_profile,
    upsert_evidence_bundle,
    upsert_pricing,
)
from ai_brain.core.kb.api.schemas import (
    INCOMPLETE_RESEARCH_NOTE,
    BidProfile,
    PricingExtraction,
    VendorEvidenceBundle,
)
from ai_brain.core.kb.store.search import set_current_project_id
from ai_brain.server.tracing import is_checkpoint_sync_error
from shared.logger_global import get_logger

log = get_logger(__name__, service="ai_brain")

# 240s was too tight for the multi-turn vendor_analyst + pricing/profile passes on larger bids.
ANALYZE_BID_TIMEOUT_S = 960.0
# Self-guard must fire before LangGraph's Send timeout. LangGraph enforces that
# one by cancelling the task (CancelledError is a BaseException), which this
# node cannot catch — one slow bid would fail the whole build with no record of
# which bid stalled. Timing out ourselves keeps the failure scoped to one bid.
# The gap must also cover fill_extraction_failed; at 60s a real run was killed
# mid-cleanup and left the project with no evidence at all.
ANALYZE_BID_SOFT_TIMEOUT_S = 780.0
# Research is bounded so the emit stage always gets to run. Previously a slow
# researcher consumed the whole budget and the outer timeout cancelled emit too,
# so a slow bid produced no evidence at all instead of partial evidence.
# Emit gets EMIT_RESERVE_S - BID_RETURN_MARGIN_S - STRUCTURED_FALLBACK_TIMEOUT_S.
# At 150 that was 65s for work measured at 221.5s (PERF extractors, bid=bdo), so
# any bid whose research ran to its deadline emitted nothing.
EMIT_RESERVE_S = 340.0
# The reserve above only sized the research deadline — the extractors themselves
# ran unbounded, so a bid reached 832s against the 600s node timeout and failed
# the whole build. Both stages are now bounded.
EMIT_MIN_BUDGET_S = 45.0
STRUCTURED_FALLBACK_TIMEOUT_S = 60.0
# invoke_vendor_analyst must RETURN before the caller's wait_for fires. Being
# cancelled there discards every finding, which is how a bid ends up with 40
# extraction_failed rows after spending its full budget.
BID_RETURN_MARGIN_S = 25.0


def classify_unpinned_artifacts(project_id: str) -> int:
    """Pin unclassified artifacts, and re-pin stem-fallback guesses once the
    parsed text that can actually name the bidder exists."""
    from ai_brain.core.kb.extract.classify import (
        STEM_FALLBACK_CONFIDENCE,
        artifact_snippets,
        classify_and_pin,
    )
    from ai_brain.core.procurement_ai.project_context import load_artifacts, load_project

    project = load_project(project_id)
    if project is None:
        return 0
    artifacts = list(load_artifacts(project.id))

    def _provisional(artifact) -> bool:
        return float(getattr(artifact, "role_confidence", 0.0) or 0.0) <= (
            STEM_FALLBACK_CONFIDENCE
        )

    known = sorted(
        {
            (a.vendor_id or "").strip()
            for a in artifacts
            if (a.vendor_id or "").strip() and not _provisional(a)
        }
    )
    pinned = 0
    for artifact in artifacts:
        if (artifact.doc_role or "").strip() == "rfp":
            continue
        current = (artifact.vendor_id or "").strip()
        if current and not _provisional(artifact):
            continue
        snippets = artifact_snippets(artifact.id)
        if current and not snippets:
            # Nothing to re-read, so the retry would only re-derive the same
            # filename slug. Record it instead of leaving a wrong bidder silent.
            _flag_unresolved_vendor(project.id, artifact, current)
            continue
        result = classify_and_pin(
            project.id,
            artifact.id,
            artifact.original_name or "",
            snippets=snippets,
            known_bids=known,
        )
        if result:
            pinned += 1
            new_bid = str(result.get("vendor_id") or "").strip()
            if new_bid and new_bid not in known:
                known.append(new_bid)
    return pinned


VENDOR_UNRESOLVED_KIND = "vendor_unresolved"


def _flag_unresolved_vendor(project_id: str, artifact, guessed_bid: str) -> None:
    """Surface a bidder still named after its filename because nothing parsed."""
    import uuid

    from sqlalchemy import delete

    from shared.db.connection import session_scope
    from shared.db.models import QualityFlag, utc_now_iso

    name = getattr(artifact, "original_name", "") or artifact.id
    parse_status = (getattr(artifact, "parse_status", "") or "unknown").strip()
    detail = (
        f"{name}: no parsed text, so the bidder is still the filename guess "
        f"'{guessed_bid}' (parse_status={parse_status}). Re-upload or fix the "
        "parse to classify it properly."
    )
    try:
        with session_scope() as session:
            session.execute(
                delete(QualityFlag).where(
                    QualityFlag.artifact_id == artifact.id,
                    QualityFlag.kind == VENDOR_UNRESOLVED_KIND,
                )
            )
            session.add(
                QualityFlag(
                    id=str(uuid.uuid4()),
                    project_id=project_id,
                    artifact_id=artifact.id,
                    kind=VENDOR_UNRESOLVED_KIND,
                    detail=detail,
                    severity="warn",
                    created_at=utc_now_iso(),
                )
            )
    except Exception:
        log.warning("could not flag unresolved vendor artifact_id={}", artifact.id)


def ensure_vendor_bids(project_id: str) -> list[str]:
    """Classify unpinned files, then list bids. Stem-pin leftover parse-ok vendor files."""
    if not project_id:
        return []
    classify_unpinned_artifacts(project_id)
    bids = list_bid_ids(project_id)
    if bids:
        return bids
    from ai_brain.core.kb.extract.classify import classify_and_pin
    from ai_brain.core.procurement_ai.project_context import load_artifacts, load_project

    project = load_project(project_id)
    if project is None:
        return []
    for artifact in load_artifacts(project.id):
        role = (artifact.doc_role or "").strip().lower()
        if role == "rfp" or (artifact.parse_status or "").strip() != "ok":
            continue
        if (artifact.vendor_id or "").strip():
            continue
        classify_and_pin(project.id, artifact.id, artifact.original_name or "")
    return list_bid_ids(project_id)


async def extract_requirements(
    state: dict[str, Any],
    config: Optional[RunnableConfig] = None,  # noqa: UP045
) -> dict[str, Any]:
    """Seed R01–R40 (SWIFT overlay). Optional requirement deepagent is additive."""
    project_id = str(state.get("project_id") or "").strip()

    def _seed() -> int:
        # Both are synchronous DBSQL; under NullPool each one is a fresh
        # warehouse handshake, so on the loop they stall every concurrent node.
        ensure_vendor_bids(project_id)
        return seed_swift_requirements(project_id)

    seeded = await asyncio.to_thread(_seed) if project_id else 0
    extra = (
        await invoke_requirement_extractor(project_id, config=config)
        if project_id
        else None
    )
    return {
        "requirements_ready": True,
        "procurement": {
            "kb_status": "building",
            "requirements_seeded": seeded,
            "requirement_agent": extra or "skipped",
        },
    }


def plan_kb_build(state: dict[str, Any]) -> list[Send] | str:
    """Deterministic dispatch — bid list from SQL, never from the model."""
    project_id = str(state.get("project_id") or "").strip()
    bids = ensure_vendor_bids(project_id) if project_id else []
    if not bids:
        return "audit_kb"
    targets = _bids_needing_extraction(project_id, bids)
    _drop_orphan_evidence(project_id, bids)
    if not targets:
        log.info("kb_build nothing changed project_id={} bids={}", project_id, len(bids))
        return "audit_kb"
    log.info(
        "kb_build extracting project_id={} bids={}/{} skipped={}",
        project_id,
        len(targets),
        len(bids),
        sorted(set(bids) - set(targets)),
    )
    return [
        Send(
            "analyze_bid",
            {
                "project_id": project_id,
                "bid_id": bid_id,
                "vendor_paths": vendor_paths(project_id, bid_id),
            },
            timeout=ANALYZE_BID_TIMEOUT_S,
        )
        for bid_id in targets
    ]


def _incremental_enabled() -> bool:
    return (os.getenv("MATE_KB_INCREMENTAL", "1") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )


def _drop_orphan_evidence(project_id: str, bids: list[str]) -> int:
    """Evidence for a bid no file carries any more.

    Re-classification moves files between bid ids (five filename guesses
    collapsing onto one real bidder), and the rows written under the old id
    would otherwise keep showing up as extra vendor columns forever.
    """
    if not bids:
        return 0
    try:
        from sqlalchemy import delete

        from shared.db.connection import session_scope
        from shared.db.models import Evidence

        with session_scope() as session:
            result = session.execute(
                delete(Evidence).where(
                    Evidence.project_id == project_id,
                    Evidence.vendor_id.not_in(bids),
                )
            )
        dropped = int(getattr(result, "rowcount", 0) or 0)
    except Exception as exc:  # noqa: BLE001 - cleanup must never fail a build
        log.warning("orphan evidence sweep failed project_id={}: {}", project_id, exc)
        return 0
    if dropped:
        log.info(
            "dropped orphan evidence project_id={} rows={} kept_bids={}",
            project_id,
            dropped,
            bids,
        )
    return dropped


def _bids_needing_extraction(project_id: str, bids: list[str]) -> list[str]:
    """Bids with no evidence, a failed pass, or inputs newer than their evidence.

    Re-reading an unchanged bid costs a full agent run, and a five-bid project
    spends ~20 minutes doing it. Anything uncertain falls back to the full list.
    """
    if not _incremental_enabled():
        return list(bids)
    try:
        from sqlalchemy import case, func, select

        from shared.db.connection import session_scope
        from shared.db.models import Artifact, Evidence

        with session_scope() as session:
            ev_rows = session.execute(
                select(
                    Evidence.vendor_id,
                    func.min(Evidence.extracted_at),
                    func.sum(
                        case((Evidence.status == "extraction_failed", 1), else_=0)
                    ),
                )
                .where(Evidence.project_id == project_id)
                .group_by(Evidence.vendor_id)
            ).all()
            art_rows = session.execute(
                select(Artifact.vendor_id, func.max(Artifact.created_at))
                .where(
                    Artifact.project_id == project_id,
                    Artifact.superseded_by.is_(None),
                )
                .group_by(Artifact.vendor_id)
            ).all()
    except Exception as exc:  # noqa: BLE001 - a planning query must never block a build
        log.warning("incremental plan failed, extracting every bid: {}", exc)
        return list(bids)

    evidence = {str(r[0]): (str(r[1] or ""), int(r[2] or 0)) for r in ev_rows}
    newest_input = {str(r[0]): str(r[1] or "") for r in art_rows}

    targets: list[str] = []
    for bid_id in bids:
        oldest_evidence, failed = evidence.get(bid_id, ("", 0))
        if not oldest_evidence or failed:
            targets.append(bid_id)
            continue
        if newest_input.get(bid_id, "") > oldest_evidence:
            targets.append(bid_id)
    return targets


def _tool_call_stats(messages: Any) -> tuple[int, int]:
    """(assistant turns, tool calls) — each assistant turn is one model round trip."""
    turns = 0
    tool_calls = 0
    for msg in list(messages or []):
        calls = getattr(msg, "tool_calls", None)
        if calls:
            tool_calls += len(calls)
        msg_type = getattr(msg, "type", None) or type(msg).__name__
        if str(msg_type).lower() in {"ai", "aimessage"}:
            turns += 1
    return turns, tool_calls


async def analyze_bid(
    task: dict[str, Any],
    config: Optional[RunnableConfig] = None,  # noqa: UP045
) -> dict[str, Any]:
    """Invoke vendor_analyst, ground, upsert evidence + pricing.

    Async so LangGraph can honour Send(..., timeout=ANALYZE_BID_TIMEOUT_S).
    Nested agents use child_runnable_config (no parent AsyncSqliteSaver).
    """
    project_id = str(task.get("project_id") or "").strip()
    bid_id = str(task.get("bid_id") or "").strip()
    set_current_project_id(project_id)
    try:
        bundle, pricing, file_count, profile = await asyncio.wait_for(
            invoke_vendor_analyst(project_id, bid_id, config=config),
            timeout=ANALYZE_BID_SOFT_TIMEOUT_S,
        )
        if not bundle.items:
            # An empty bundle writes nothing, so last run's rows would stand and
            # audit_kb would report the project ready on stale data.
            raise ValueError(f"vendor_analyst returned no evidence for bid {bid_id}")
        # bid_id comes from the fan-out, not from model output: the persist
        # layer deletes by vendor, so an echoed-back wrong id would delete
        # another bid's rows.
        counts = await asyncio.to_thread(
            upsert_evidence_bundle,
            project_id,
            bundle,
            bid_id=bid_id,
            unverified_absence=any(
                INCOMPLETE_RESEARCH_NOTE in (note or "") for note in (bundle.notes or [])
            ),
        )
        try:
            pricing_n = (
                await asyncio.to_thread(
                    upsert_pricing, project_id, pricing, bid_id=bid_id
                )
                if pricing and pricing.lines
                else 0
            )
            profile_n = (
                await asyncio.to_thread(
                    upsert_bid_profile, project_id, profile, bid_id=bid_id
                )
                if profile
                else 0
            )
        except Exception as persist_exc:  # noqa: BLE001
            if is_checkpoint_sync_error(persist_exc):
                raise
            log.exception(
                "pricing/profile persist failed project_id={} bid_id={}",
                project_id,
                bid_id,
            )
            pricing_n = 0
            profile_n = 0
        status = "ok"
    except Exception as exc:  # noqa: BLE001
        if is_checkpoint_sync_error(exc):
            raise
        if isinstance(exc, asyncio.TimeoutError):
            detail = (
                f"vendor_analyst exceeded {ANALYZE_BID_SOFT_TIMEOUT_S:.0f}s for bid {bid_id}"
            )
            log.error(
                "vendor_analyst timed out project_id={} bid_id={} limit_s={}",
                project_id,
                bid_id,
                ANALYZE_BID_SOFT_TIMEOUT_S,
            )
        else:
            detail = str(exc)
            log.exception("vendor_analyst failed project_id={} bid_id={}", project_id, bid_id)
        # Off the loop: this is ~40 Delta row writes under NullPool and it runs
        # in the narrow window between the soft timeout and the node deadline.
        # Left synchronous, two bids failing at once serialise here and drag the
        # whole node past ANALYZE_BID_TIMEOUT_S (observed: 621.9s of a 600s cap).
        await asyncio.to_thread(
            fill_extraction_failed, project_id, bid_id, detail=detail
        )
        counts = {"error": detail}
        pricing_n = 0
        file_count = 0
        profile_n = 0
        status = "extraction_failed"
    finally:
        set_current_project_id(None)
    return {
        "kb_bundles": [
            {
                "bid_id": bid_id,
                "file_count": file_count,
                "status": status,
                "persist": counts,
                "pricing_lines": pricing_n,
                "profile": profile_n,
            }
        ]
    }


def audit_kb(state: dict[str, Any]) -> dict[str, Any]:
    bundles = list(state.get("kb_bundles") or [])
    failed = sum(1 for b in bundles if b.get("status") == "extraction_failed")
    return {
        "procurement": {
            "kb_audit": {"bundle_count": len(bundles), "failed": failed},
            "kb_status": "ready" if bundles and not failed else ("needs_review" if bundles else "staged"),
        }
    }


def plan_publish(state: dict[str, Any]) -> list[Send]:
    """Deterministic hand-off — Overview / Requirements / Vendors from SQL."""
    project_id = str(state.get("project_id") or "").strip()
    audit = (state.get("procurement") or {}).get("kb_audit") or {}
    return [
        Send("fill_overview", {"project_id": project_id, "kb_audit": audit}),
        Send("fill_requirements", {"project_id": project_id}),
        Send("fill_vendors", {"project_id": project_id}),
    ]


def fill_overview(task: dict[str, Any]) -> dict[str, Any]:
    from ai_brain.core.kb.api.views import build_overview_view, write_view

    project_id = str(task.get("project_id") or "").strip()
    payload = build_overview_view(project_id, kb_audit=task.get("kb_audit"))
    write_view(project_id, "overview", payload)
    return {"procurement": {"views": {"overview": True}}}


def fill_requirements(task: dict[str, Any]) -> dict[str, Any]:
    from ai_brain.core.kb.api.views import build_requirements_view, write_view

    project_id = str(task.get("project_id") or "").strip()
    payload = build_requirements_view(project_id)
    write_view(project_id, "requirements", payload)
    return {"procurement": {"views": {"requirements": True}}}


def fill_vendors(task: dict[str, Any]) -> dict[str, Any]:
    from ai_brain.core.kb.api.views import build_vendors_view, write_view

    project_id = str(task.get("project_id") or "").strip()
    payload = build_vendors_view(project_id)
    write_view(project_id, "vendors", payload)
    return {"procurement": {"views": {"vendors": True}}}


async def invoke_requirement_extractor(
    project_id: str,
    config: Optional[RunnableConfig] = None,  # noqa: UP045
) -> str | None:
    """Optional RFP-only deepagent. Default skip unless KB_REQUIREMENT_AGENT=1."""
    if os.getenv("KB_REQUIREMENT_AGENT", "").strip() not in {"1", "true", "yes"}:
        return None
    try:
        from ai_brain.core.kb.extract.agents import build_requirement_extractor, invoke_payload
        from ai_brain.server.tracing import child_runnable_config

        agent = build_requirement_extractor()
        payload = invoke_payload(
            project_id,
            "Extract requirements from /project/*/rfp/. Align to R01–R40. "
            "Add extras as R-E-NNN with page citations.",
        )
        await agent.ainvoke(
            {"messages": payload["messages"]},
            config=child_runnable_config(_config_dict(config)),
        )
        return "invoked"
    except Exception as exc:  # noqa: BLE001
        log.warning("requirement_extractor skipped: {}", exc)
        return f"error:{exc}"


def _config_dict(config: Optional[RunnableConfig]) -> dict[str, Any]:  # noqa: UP045
    if config is None:
        return {}
    if isinstance(config, dict):
        return dict(config)
    return dict(config)


async def invoke_vendor_analyst(
    project_id: str,
    bid_id: str,
    config: Optional[RunnableConfig] = None,  # noqa: UP045
) -> tuple[VendorEvidenceBundle, PricingExtraction | None, int, BidProfile | None]:
    """Phase A deep-agent research (files + MCP), then ToolStrategy emit."""
    bid_t0 = time.monotonic()
    from ai_brain.core.kb.extract.agents import (
        MAX_COVERAGE_REFILLS,
        bid_invoke_payload,
        build_pricing_extractor,
        build_profile_extractor,
        build_vendor_analyst,
        build_vendor_emit,
        coverage_refill_message,
        emit_user_message,
    )
    from ai_brain.core.kb.build.coverage import CoverageState, coverage_scope
    from ai_brain.core.kb.api.mcp_tools import list_bid_chunk_ids, list_bid_chunk_rows, mcp_kb_tools_context
    from ai_brain.server.tracing import child_runnable_config, is_checkpoint_sync_error

    def _load_inputs() -> tuple[dict[str, Any], set[str], dict[str, str]]:
        data = bid_invoke_payload(project_id, bid_id)
        ids = set(list_bid_chunk_ids(project_id, bid_id, for_coverage=True))
        paths = {
            row["chunk_id"]: row.get("path") or ""
            for row in list_bid_chunk_rows(project_id, bid_id)
            if row.get("path")
        }
        return data, ids, paths

    # All three are synchronous DBSQL; on the loop they stall it long enough
    # that the surrounding asyncio timeouts never get a chance to fire.
    payload, required, chunk_paths = await asyncio.to_thread(_load_inputs)
    file_count = sum(
        1 for path in payload.get("files") or {} if f"/vendors/{bid_id}/" in path
    )
    nested = child_runnable_config(_config_dict(config))
    packed_ids = [str(cid) for cid in (payload.get("packed_chunk_ids") or []) if cid]
    coverage = CoverageState(required=required, chunk_paths=chunk_paths)
    coverage.read.update(packed_ids)
    state: dict[str, Any] = {
        "messages": list(payload["messages"]),
        "files": payload.get("files") or {},
    }
    research: dict[str, Any] = {"messages": payload["messages"]}
    research_t0 = time.monotonic()
    research_cut = False
    research_deadline = bid_t0 + ANALYZE_BID_SOFT_TIMEOUT_S - EMIT_RESERVE_S
    async with mcp_kb_tools_context() as tools:
        researcher = build_vendor_analyst(tools=tools)
        with coverage_scope(coverage):
            for turn in range(1 + MAX_COVERAGE_REFILLS):
                turn_t0 = time.monotonic()
                remaining = research_deadline - turn_t0
                if remaining <= 0:
                    research_cut = True
                    log.warning(
                        "vendor_analyst research budget spent before turn={} project_id={} bid_id={}",
                        turn + 1,
                        project_id,
                        bid_id,
                    )
                    break
                try:
                    # Stream, don't await: wait_for cancelling ainvoke() throws
                    # away everything the agent read. A 582-chunk bid spent its
                    # whole 330s budget and still reported zero turns because of
                    # that. Keeping the last streamed state means a cut-off turn
                    # still hands emit the chunks it managed to gather.
                    partial: dict[str, Any] | None = None
                    async with asyncio.timeout(remaining):
                        async for step in researcher.astream(
                            state, config=nested, stream_mode="values"
                        ):
                            if isinstance(step, dict) and step.get("messages"):
                                partial = step
                    research = partial or research
                except (TimeoutError, asyncio.TimeoutError):
                    research_cut = True
                    salvaged, salvaged_calls = _tool_call_stats(
                        (partial or {}).get("messages")
                    )
                    if partial is not None:
                        research = partial
                    log.warning(
                        "vendor_analyst research cut at {:.0f}s, emitting from what was gathered "
                        "llm_turns={} tool_calls={} project_id={} bid_id={}",
                        time.monotonic() - research_t0,
                        salvaged,
                        salvaged_calls,
                        project_id,
                        bid_id,
                    )
                    break
                turns, tool_calls = _tool_call_stats(research.get("messages"))
                log.info(
                    "PERF vendor_analyst turn={} elapsed_s={:.1f} llm_turns={} tool_calls={} project_id={} bid_id={}",
                    turn + 1,
                    time.monotonic() - turn_t0,
                    turns,
                    tool_calls,
                    project_id,
                    bid_id,
                )
                unread = coverage.unread()
                if not unread:
                    break
                log.info(
                    "vendor_analyst coverage refill turn={} unread={} project_id={} bid_id={}",
                    turn + 1,
                    len(unread),
                    project_id,
                    bid_id,
                )
                state = {
                    "messages": list(research.get("messages") or [])
                    + [coverage_refill_message(unread)],
                    "files": payload.get("files") or {},
                }
    research_messages = list(research.get("messages") or payload["messages"])
    research_elapsed = time.monotonic() - research_t0
    total_turns, total_tool_calls = _tool_call_stats(research_messages)
    log.info(
        "PERF vendor_analyst TOTAL elapsed_s={:.1f} llm_turns={} tool_calls={} chunks={} project_id={} bid_id={}",
        research_elapsed,
        total_turns,
        total_tool_calls,
        len(required),
        project_id,
        bid_id,
    )
    unread = coverage.unread()
    emit_messages = _databricks_safe_messages(research_messages)
    # Pricing and BAFO facts do not need 40 requirements' worth of quoted
    # evidence. Sending the full transcript to all three extractors tripled the
    # bid's input tokens and tripped the workspace per-minute cap.
    side_messages = _databricks_safe_messages(
        research_messages, limit=SIDE_TRANSCRIPT_CHARS
    )
    if total_turns == 0:
        # Research never got a turn in. Hand emit the packed corpus directly so
        # the bid still yields cited evidence instead of nothing.
        emit_messages = emit_messages + _packed_corpus_messages(project_id, bid_id)
        log.warning(
            "vendor_analyst produced no turns, emitting from packed chunks project_id={} bid_id={}",
            project_id,
            bid_id,
        )
    emit = build_vendor_emit()
    pricing_agent = build_pricing_extractor()
    profile_agent = build_profile_extractor()

    async def _ainvoke_emit() -> Any:
        try:
            return await emit.ainvoke(
                {"messages": emit_messages + [emit_user_message(bid_id)]},
                config=nested,
            )
        except Exception as exc:  # noqa: BLE001
            if is_checkpoint_sync_error(exc):
                raise
            log.warning(
                "vendor_emit failed project_id={} bid_id={}: {}",
                project_id,
                bid_id,
                exc,
            )
            return {"messages": emit_messages}

    async def _ainvoke_pricing() -> Any:
        try:
            return await pricing_agent.ainvoke(
                {
                    "messages": side_messages
                    + [
                        {
                            "role": "user",
                            "content": (
                                f"Extract commercial terms for bid `{bid_id}`. "
                                "Cite pages or chunk_id. Return PricingExtraction."
                            ),
                        }
                    ]
                },
                config=nested,
            )
        except Exception as exc:  # noqa: BLE001
            if is_checkpoint_sync_error(exc):
                raise
            log.exception(
                "pricing_extractor failed project_id={} bid_id={}",
                project_id,
                bid_id,
            )
            return None

    async def _ainvoke_profile() -> Any:
        try:
            return await profile_agent.ainvoke(
                {
                    "messages": side_messages
                    + [
                        {
                            "role": "user",
                            "content": (
                                f"Extract BidProfile BAFO facts for bid `{bid_id}`. "
                                "Omit fields the source does not state."
                            ),
                        }
                    ]
                },
                config=nested,
            )
        except Exception as exc:  # noqa: BLE001
            if is_checkpoint_sync_error(exc):
                raise
            log.exception(
                "profile_extractor failed project_id={} bid_id={}",
                project_id,
                bid_id,
            )
            return None

    extract_t0 = time.monotonic()
    bid_deadline = bid_t0 + ANALYZE_BID_SOFT_TIMEOUT_S - BID_RETURN_MARGIN_S
    # Leave the fallback its own room inside the deadline instead of starting it
    # after the budget is already spent (330 + 150 + 60 overran a 480s cap).
    emit_budget = min(
        max(
            EMIT_MIN_BUDGET_S,
            bid_deadline - extract_t0 - STRUCTURED_FALLBACK_TIMEOUT_S,
        ),
        max(0.0, bid_deadline - extract_t0),
    )
    try:
        result, pricing_result, profile_result = await asyncio.wait_for(
            asyncio.gather(
                _ainvoke_emit(),
                _ainvoke_pricing(),
                _ainvoke_profile(),
            ),
            emit_budget,
        )
    except asyncio.TimeoutError:
        log.warning(
            "extractors exceeded {:.0f}s project_id={} bid_id={}; one structured call instead",
            emit_budget,
            project_id,
            bid_id,
        )
        result = pricing_result = profile_result = None
    log.info(
        "PERF extractors elapsed_s={:.1f} project_id={} bid_id={}",
        time.monotonic() - extract_t0,
        project_id,
        bid_id,
    )
    try:
        bundle = bundle_from_result(result, bid_id)
    except ValueError:
        log.warning(
            "vendor_analyst missing structured_response project_id={} bid_id={}",
            project_id,
            bid_id,
        )
        try:
            bundle = await _structured_fallback(
                VendorEvidenceBundle,
                emit_messages,
                bid_id,
                budget=max(0.0, bid_deadline - time.monotonic()),
            )
        except (TimeoutError, asyncio.TimeoutError):
            # Return empty rather than raise so the other bids still run;
            # analyze_bid turns an empty bundle into this bid's failure.
            log.error(
                "structured fallback timed out project_id={} bid_id={}",
                project_id,
                bid_id,
            )
            bundle = VendorEvidenceBundle(bid_id=bid_id, items=[])
    if unread:
        notes = list(bundle.notes or [])
        notes.append("unread chunks: " + ", ".join(unread[:40]))
        bundle = bundle.model_copy(update={"notes": notes})
    if research_cut or total_turns == 0 or unread:
        # Downstream turns every not_stated in this bundle into "we could not
        # determine" rather than "the bidder is silent".
        bundle = bundle.model_copy(
            update={"notes": list(bundle.notes or []) + [INCOMPLETE_RESEARCH_NOTE]}
        )
    pricing = (
        pricing_from_result(pricing_result, bid_id)
        or pricing_from_result(result, bid_id)
        or pricing_from_result(research, bid_id)
        or await _optional_structured(PricingExtraction, side_messages, bid_id, bid_t0)
    )
    profile = (
        profile_from_result(profile_result, bid_id)
        or profile_from_result(result, bid_id)
        or profile_from_result(research, bid_id)
        or await _optional_structured(BidProfile, side_messages, bid_id, bid_t0)
    )
    return bundle, pricing, file_count, profile


# deepagents evicts a single user message over NUM_CHARS_PER_TOKEN(4) *
# human_message_token_limit_before_evict(50_000) = 200_000 chars, replacing it
# with a preview. Stay under that with headroom; 60_000 was throwing away 84%
# of a large bid's transcript before emit ever saw it.
EMIT_TRANSCRIPT_CHARS = 150_000
# Pricing/profile extractors read the same transcript; at full size the three
# calls together are what exhausts the workspace input-token-per-minute tier.
SIDE_TRANSCRIPT_CHARS = 50_000
_TRANSCRIPT_MIN_SLICE = 2_000
_TRUNC_MARK = "\n...[truncated]"
# Emit must quote chunk text literally to pass the grounding gate, so the
# analyst's own words get at most half the budget and the source keeps the rest.
_TRANSCRIPT_SAID_SHARE = 0.5


def _packed_corpus_messages(project_id: str, bid_id: str) -> list[dict[str, str]]:
    """The bid's chunks as plain text, for when research stalls before any turn."""
    from ai_brain.core.kb.api.mcp_tools import prefetch_bid_chunks

    try:
        packed, _ = prefetch_bid_chunks(project_id, bid_id)
    except Exception:
        log.exception("packed corpus fallback failed project_id={} bid_id={}", project_id, bid_id)
        return []
    parts: list[str] = []
    total = 0
    for path in sorted(packed):
        text = packed[path] or ""
        if not text:
            continue
        parts.append(text)
        total += len(text)
        if total > EMIT_TRANSCRIPT_CHARS:
            break
    if not parts:
        return []
    body = "\n\n".join(parts)[:EMIT_TRANSCRIPT_CHARS]
    return [{"role": "user", "content": f"Bid corpus for `{bid_id}`:\n\n{body}"}]


def _message_role(msg: Any) -> str:
    if isinstance(msg, dict):
        return str(msg.get("role") or msg.get("type") or "").lower()
    return str(getattr(msg, "type", "") or getattr(msg, "role", "") or "").lower()


def _message_name(msg: Any) -> str:
    if isinstance(msg, dict):
        return str(msg.get("name") or "")
    return str(getattr(msg, "name", "") or "")


def _databricks_safe_messages(
    messages: list[Any], *, limit: int = EMIT_TRANSCRIPT_CHARS
) -> list[dict[str, str]]:
    """Collapse research tool round-trips into plain user text.

    ChatDatabricks rejects Anthropic ``tool_result`` blocks that include
    ``id`` on nested text (``messages.N.content.0.tool_result.content.0.text.id``).
    Passing the raw deep-agent transcript also makes ``ModelCallLimitMiddleware``
    treat prior AIMessages as already spent, so emit dies at 15/15.
    """
    from ai_brain.core.utils.content import content_text

    # "said" is the analyst's own output; everything else (tool results and the
    # research prompt, which carries a one-line-per-chunk index) is source the
    # emit step only needs in order to quote it.
    parts: list[tuple[bool, str]] = []
    for msg in messages or []:
        role = _message_role(msg)
        if role in {"system", "developer"}:
            continue
        raw = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", None)
        text = (content_text(raw) or "").strip()
        if not text:
            continue
        if role in {"tool", "function"}:
            name = _message_name(msg) or "tool"
            parts.append((False, f"[{name}]\n{text}"))
        else:
            parts.append((role not in {"user", "human"}, text))

    # A flat head-cut dropped the tail, which is where the conclusions are.
    said_cap = int(limit * _TRANSCRIPT_SAID_SHARE)
    said_keep: dict[int, str] = {}
    said_used = 0
    for idx in range(len(parts) - 1, -1, -1):
        is_said, text = parts[idx]
        if not is_said:
            continue
        free = said_cap - said_used
        if free <= 0:
            break
        if len(text) <= free:
            said_keep[idx] = text
            said_used += len(text)
        elif free > _TRANSCRIPT_MIN_SLICE:
            # Never drop an oversized analyst message whole; its findings are at
            # the end of it.
            head = _TRUNC_MARK.strip() + "\n"
            said_keep[idx] = head + text[-(free - len(head)) :]
            said_used = said_cap
            break
    room = max(0, limit - said_used - 2 * len(parts))
    out: list[str] = []
    used = 0
    for idx, (is_said, text) in enumerate(parts):
        if is_said:
            kept = said_keep.get(idx)
            if kept:
                out.append(kept)
        elif used + len(text) <= room:
            out.append(text)
            used += len(text)
        elif room - used > _TRANSCRIPT_MIN_SLICE:
            out.append(text[: room - used - len(_TRUNC_MARK)] + _TRUNC_MARK)
            used = room
    body = "\n\n".join(out).strip() or "(no research notes)"
    if len(body) > limit:
        head = _TRUNC_MARK.strip() + "\n"
        body = head + body[-(limit - len(head)) :]
    return [{"role": "user", "content": body}]


def bundle_from_result(result: Any, bid_id: str) -> VendorEvidenceBundle:
    data = _structured(result)
    if isinstance(data, VendorEvidenceBundle):
        return data
    if isinstance(data, dict) and ("items" in data or "bid_id" in data):
        payload = dict(data)
        payload.setdefault("bid_id", bid_id)
        payload.setdefault("items", [])
        return VendorEvidenceBundle.model_validate(payload)
    raise ValueError("vendor_analyst returned no VendorEvidenceBundle")


def pricing_from_result(result: Any, bid_id: str) -> PricingExtraction | None:
    data = _structured(result)
    if isinstance(data, PricingExtraction):
        return data
    if isinstance(data, dict) and "lines" in data:
        payload = dict(data)
        payload.setdefault("bid_id", bid_id)
        return PricingExtraction.model_validate(payload)
    nested = result.get("pricing") if isinstance(result, dict) else None
    if isinstance(nested, dict):
        nested.setdefault("bid_id", bid_id)
        return PricingExtraction.model_validate(nested)
    return None


def profile_from_result(result: Any, bid_id: str) -> BidProfile | None:
    data = _structured(result)
    if isinstance(data, BidProfile):
        return data
    if isinstance(data, dict) and (
        data.get("timeline")
        or data.get("ecovadis")
        or data.get("delivery_model")
        or data.get("y2_tco")
        or data.get("y1_tco")
        or data.get("assumptions")
        or "citations" in data
    ):
        payload = dict(data)
        payload.setdefault("bid_id", bid_id)
        try:
            return BidProfile.model_validate(payload)
        except Exception:  # noqa: BLE001
            return None
    nested = result.get("profile") if isinstance(result, dict) else None
    if isinstance(nested, dict):
        nested.setdefault("bid_id", bid_id)
        try:
            return BidProfile.model_validate(nested)
        except Exception:  # noqa: BLE001
            return None
    return None


# Recovering pricing/BAFO facts must never cost the evidence bundle its own
# deadline, so the fallback only runs when the bid still has budget to spare.
OPTIONAL_STRUCTURED_TIMEOUT_S = 45.0
OPTIONAL_STRUCTURED_MIN_REMAINING_S = 75.0


async def _optional_structured(
    schema: type, messages: list[Any], bid_id: str, bid_t0: float
) -> Any:
    """Last-resort structured call. The emit agents raise at their model-call
    limit, which used to drop pricing and BAFO facts silently."""
    remaining = ANALYZE_BID_SOFT_TIMEOUT_S - (time.monotonic() - bid_t0)
    if remaining < OPTIONAL_STRUCTURED_MIN_REMAINING_S:
        log.info(
            "{} fallback skipped bid_id={} remaining_s={:.0f}",
            schema.__name__,
            bid_id,
            remaining,
        )
        return None
    budget = min(OPTIONAL_STRUCTURED_TIMEOUT_S, remaining - 30.0)
    try:
        return await asyncio.wait_for(
            _structured_fallback(schema, messages, bid_id), timeout=budget
        )
    except Exception as exc:  # noqa: BLE001
        if is_checkpoint_sync_error(exc):
            raise
        log.warning(
            "{} fallback failed bid_id={}: {}", schema.__name__, bid_id, exc
        )
        return None


async def _structured_fallback(
    schema: type, messages: list[Any], bid_id: str, *, budget: float | None = None
) -> Any:
    """ChatDatabricks.with_structured_output when the agent skipped ToolStrategy."""
    from ai_brain.core.config.llm import get_extract_model_kind, get_llm
    from ai_brain.core.procurement_ai.packs.matrix_layout import EXTRACT_MAX_TOKENS

    llm = get_llm(get_extract_model_kind(), max_tokens=EXTRACT_MAX_TOKENS)
    out = await asyncio.wait_for(
        llm.with_structured_output(schema).ainvoke(_databricks_safe_messages(messages)),
        STRUCTURED_FALLBACK_TIMEOUT_S if budget is None else budget,
    )
    if isinstance(out, schema):
        return out
    if isinstance(out, dict):
        payload = dict(out)
        payload.setdefault("bid_id", bid_id)
        if schema is VendorEvidenceBundle:
            payload.setdefault("items", [])
        if schema is BidProfile:
            payload.setdefault("bid_id", bid_id)
        return schema.model_validate(payload)
    raise ValueError(f"{schema.__name__} fallback returned {type(out).__name__}")


def _structured(result: Any) -> Any:
    if not isinstance(result, dict):
        return result
    data = result.get("structured_response")
    if data is not None:
        return data
    if result.get("output") is not None:
        return result["output"]
    for msg in reversed(list(result.get("messages") or [])):
        parsed = _from_ai_message(msg)
        if parsed is not None:
            return parsed
    return result


def _from_ai_message(msg: Any) -> Any:
    calls = getattr(msg, "tool_calls", None)
    if calls is None and isinstance(msg, dict):
        calls = msg.get("tool_calls")
    for call in calls or []:
        args = call.get("args") if isinstance(call, dict) else getattr(call, "args", None)
        if isinstance(args, dict) and (
            "items" in args or "bid_id" in args or "lines" in args or "timeline" in args
        ):
            return args
    content = getattr(msg, "content", None)
    if content is None and isinstance(msg, dict):
        content = msg.get("content")
    texts: list[str] = []
    if isinstance(content, str):
        texts.append(content)
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                texts.append(str(block.get("text") or ""))
            elif isinstance(block, str):
                texts.append(block)
    for text in texts:
        stripped = text.strip()
        if not stripped.startswith("{"):
            continue
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None
