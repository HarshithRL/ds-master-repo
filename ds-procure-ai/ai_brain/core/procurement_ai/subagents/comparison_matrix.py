"""Request-time comparison Deep Agent. MCP research, then ToolStrategy emit.

Excel is the only persist. ChatDatabricks cannot mix MCP tools with structured
output on one agent — same split as vendor_analyst.

https://docs.langchain.com/oss/python/deepagents/tools#mcp-tools
https://docs.langchain.com/oss/python/langchain/mcp
https://docs.langchain.com/oss/python/deepagents/subagents
"""

from __future__ import annotations

from typing import Any

from ai_brain.core.kb.extract.agents import (
    CITATION_DOCTRINE,
    MAX_COVERAGE_REFILLS,
    coverage_refill_message,
    extraction_middleware,
    emit_middleware,
    files_for_invoke,
)
from ai_brain.core.procurement_ai.ontology import ComparisonMatrix, ONTOLOGY_VERSION
from ai_brain.core.procurement_ai.packs.matrix_layout import EXTRACT_MAX_TOKENS, SWIFT_REQUIREMENTS
from ai_brain.core.procurement_ai.process_type import IT_SERVICES
from shared.logger_global import get_logger

log = get_logger(__name__, service="ai_brain")

ORCHESTRATOR_PROMPT = (
    "You are the procurement comparison orchestrator. "
    "Identify process_type (direct_tg vs indirect_it_software vs indirect_it_services). "
    "Never mix Direct TG with Indirect IT. "
    "Call list_bids then list_project_paths. "
    "Delegate with the task tool: rfp_analyst first, then vendor_analyst once per bid, "
    "then bafo_compiler. "
    "Do not invent EUR. Empty is missing, never zero. Humans award. "
    "Do not write the Excel. Do not emit ComparisonMatrix in this step.\n"
    + CITATION_DOCTRINE
)

RFP_PROMPT = (
    "Read /project/*/rfp/ and RFP chunks. Emit a requirement spine: id, text, category, "
    "target, mandatory. "
    "If this is SWIFT CSP / CSCF / independent assessment, use R01–R40 exactly as the overlay. "
    "If Direct TG, do not use SWIFT BIC/CSCF overlay labels — extract from this RFP. "
    "Cite artifact + page. Return a compact list, not PDF dumps.\n"
)

VENDOR_PROMPT = (
    "Analyse one bid only. Corpus is under /project/*/vendors/<bid>/_chunks/. "
    "ls/grep/read_file those files and the RFP. "
    "Use MCP list_bid_chunks, read_chunk, read_chunks, read_chunk_window to iterate unread chunks. "
    "Extract requirement marks (value_text + status + quote + locator) and BAFO narrative strings "
    "(Y1–Y3 TCO, mandays, EcoVadis, CreditScore as a separate field, legal, assumptions, gaps). "
    "Prefer SWIFT phrasing: '€3,600 (4.5 days)', 'Not quantified', "
    "'N/A - advisory service, no software'. "
    "Scorecard / architecture / security stay for humans. "
    "Return a compact VendorProfile + offerings for this bid.\n"
    + CITATION_DOCTRINE
)

BAFO_PROMPT = (
    "Roll up all vendor summaries. Build missing_requirement list per bid, key flags "
    "(wrong legal entity, missed dates, dual-pricing gaps), method notes, and RFP source filenames. "
    "Do not invent totals. If a year is not quoted, say so. "
    "Etex mandays × 800 EUR/day only when the day-count is cited.\n"
)

EMIT_PROMPT = (
    "Call the ComparisonMatrix structured-output tool now. "
    "Use only facts already in this conversation. ontology_version is "
    f"{ONTOLOGY_VERSION}. Do not invent numbers. Unevidenced commercial fields stay null. "
    "Scorecard owner is Etex evaluation team. Do not call file tools.\n"
)


def _overlay_block(process_type: str) -> str:
    if process_type != IT_SERVICES:
        return "Requirement spine comes from the RFP. Do not paste SWIFT CSP R01–R40 overlay labels."
    lines = [f"- {rid}: {label} [{category}] {target}" for rid, label, category, target in SWIFT_REQUIREMENTS]
    return "SWIFT CSP overlay (use these ids):\n" + "\n".join(lines)


def comparison_user_message(project_id: str, process_type: str, bids: list[str]) -> str:
    bid_list = ", ".join(f"`{bid}`" for bid in bids) or "(none classified)"
    return (
        f"Build a rich vendor comparison matrix for project `{project_id}`.\n"
        f"process_type={process_type or 'unset'}. Bids: {bid_list}.\n"
        f"{_overlay_block(process_type)}\n"
        "Delegate rfp_analyst, then vendor_analyst per bid, then bafo_compiler. "
        "Iterate all chunks. Citation-or-abstain."
    )


def comparison_files(project_id: str) -> tuple[dict[str, dict[str, str]], list[str]]:
    """Materialize /project files + packed bid chunks + skills for StateBackend."""
    from deepagents.backends.utils import create_file_data

    from ai_brain.core.kb.api.mcp_tools import prefetch_bid_chunks
    from ai_brain.core.kb.store.materialize import list_bid_ids

    files = files_for_invoke(project_id)
    packed_ids: list[str] = []
    for bid in list_bid_ids(project_id):
        packed, ids = prefetch_bid_chunks(project_id, bid)
        packed_ids.extend(str(cid) for cid in ids if cid)
        for path, text in packed.items():
            files[path] = create_file_data(text)
    return files, packed_ids


async def _research_with_coverage(
    orchestrator: Any,
    project_id: str,
    process: str,
    bids: list[str],
    files: dict[str, dict[str, str]],
    packed_ids: list[str],
    nested: dict[str, Any] | None,
) -> dict[str, Any]:
    from ai_brain.core.kb.api.mcp_tools import list_bid_chunk_ids
    from ai_brain.core.kb.build.coverage import CoverageState, coverage_scope

    required: set[str] = set()
    for bid in bids:
        required.update(list_bid_chunk_ids(project_id, bid))
    coverage = CoverageState(required=required)
    coverage.read.update(packed_ids)
    state: dict[str, Any] = {
        "messages": [
            {"role": "user", "content": comparison_user_message(project_id, process, bids)}
        ],
        "files": files,
    }
    research: dict[str, Any] = {"messages": state["messages"]}
    with coverage_scope(coverage):
        for turn in range(1 + MAX_COVERAGE_REFILLS):
            research = await orchestrator.ainvoke(state, config=nested)
            unread = coverage.unread()
            if not unread:
                break
            log.info(
                "comparison coverage refill turn={} unread={} project_id={}",
                turn + 1,
                len(unread),
                project_id,
            )
            state = {
                "messages": list(research.get("messages") or [])
                + [coverage_refill_message(unread)],
                "files": files,
            }
    return research


def build_comparison_orchestrator(
    *,
    model: Any | None = None,
    fallback_model: Any | None = None,
    tools: list[Any] | None = None,
):
    from deepagents import create_deep_agent
    from deepagents.backends import StateBackend
    from deepagents.middleware.filesystem import FilesystemMiddleware

    from ai_brain.core.kb.api.mcp_tools import langchain_kb_tools
    from ai_brain.core.kb.build.coverage import CoverageMiddleware

    primary = model or _llm(get_extract_model_kind())
    fast = fallback_model if fallback_model is not None else _llm("fast")
    agent_tools = tools if tools is not None else langchain_kb_tools()
    backend = StateBackend()
    subagents = [
        {
            "name": "rfp_analyst",
            "description": "Extract the RFP requirement spine. SWIFT CSP uses R01–R40.",
            "system_prompt": RFP_PROMPT,
            "tools": agent_tools,
        },
        {
            "name": "vendor_analyst",
            "description": "Analyse one bid: iterate chunks, requirement marks, BAFO narrative.",
            "system_prompt": VENDOR_PROMPT,
            "tools": agent_tools,
        },
        {
            "name": "bafo_compiler",
            "description": "Cross-bid rollup: flags, missing requirements, method notes.",
            "system_prompt": BAFO_PROMPT,
            "tools": agent_tools,
        },
    ]
    return create_deep_agent(
        model=primary,
        tools=agent_tools,
        system_prompt=ORCHESTRATOR_PROMPT,
        backend=backend,
        subagents=subagents,
        skills=["/skills/procurement/"],
        middleware=[
            FilesystemMiddleware(
                backend=backend,
                tools=["read_file", "ls", "glob", "grep"],
            ),
            CoverageMiddleware(),
            *extraction_middleware(fast),
        ],
        checkpointer=None,
        name="comparison_orchestrator",
    )


def build_comparison_emit(
    *,
    model: Any | None = None,
    fallback_model: Any | None = None,
):
    from langchain.agents import create_agent
    from langchain.agents.structured_output import ToolStrategy

    primary = model or _llm(get_extract_model_kind())
    fast = fallback_model if fallback_model is not None else _llm("fast")
    return create_agent(
        model=primary,
        tools=[],
        system_prompt=EMIT_PROMPT,
        response_format=ToolStrategy(ComparisonMatrix, handle_errors=True),
        middleware=emit_middleware(fast),
        checkpointer=None,
        name="comparison_emit",
    )


async def extract_comparison_matrix(
    project_id: str,
    insights: dict[str, Any],
    *,
    config: dict[str, Any] | None = None,
) -> ComparisonMatrix | None:
    """Research with MCP + subagents, then emit ComparisonMatrix. None if the LLM fails."""
    from ai_brain.core.kb.api.mcp_tools import mcp_kb_tools_context
    from ai_brain.core.kb.store.materialize import list_bid_ids
    from ai_brain.core.kb.store.search import set_current_project_id
    from ai_brain.server.tracing import child_runnable_config, is_checkpoint_sync_error

    process = str(insights.get("process_type") or "").strip()
    bids = list(list_bid_ids(project_id))
    nested = child_runnable_config(dict(config or {}))
    set_current_project_id(project_id)
    files, packed_ids = comparison_files(project_id)
    try:
        async with mcp_kb_tools_context() as tools:
            orchestrator = build_comparison_orchestrator(tools=tools)
            research = await _research_with_coverage(
                orchestrator,
                project_id,
                process,
                bids,
                files,
                packed_ids,
                nested,
            )
        messages = list(research.get("messages") or [])
        emit = build_comparison_emit()
        result = await emit.ainvoke(
            {
                "messages": messages
                + [
                    {
                        "role": "user",
                        "content": (
                            f"Call ComparisonMatrix now for project `{project_id}` "
                            f"process_type={process or 'unset'}."
                        ),
                    }
                ]
            },
            config=nested,
        )
    except Exception as exc:  # noqa: BLE001
        if is_checkpoint_sync_error(exc):
            raise
        log.exception("comparison matrix agent failed project_id={}", project_id)
        raise
    finally:
        set_current_project_id(None)
    payload = result.get("structured_response") if isinstance(result, dict) else None
    if isinstance(payload, ComparisonMatrix):
        return payload
    if isinstance(payload, dict):
        try:
            return ComparisonMatrix.model_validate(payload)
        except Exception as exc:  # noqa: BLE001
            log.warning("comparison emit invalid ComparisonMatrix: {}", exc)
            return None
    log.warning("comparison emit missing structured_response project_id={}", project_id)
    return None


def empty_matrix_for_process(process_type: str) -> ComparisonMatrix | None:
    if not process_type:
        return None
    from ai_brain.core.procurement_ai.fixture_loader import load_catalog

    try:
        return load_catalog(process_type)
    except ValueError:
        return None


def get_extract_model_kind() -> str:
    from ai_brain.core.config.llm import get_extract_model_kind as _kind

    return _kind()


def _llm(kind: str):
    from ai_brain.core.config.llm import get_llm

    return get_llm(kind, max_tokens=EXTRACT_MAX_TOKENS)  # type: ignore[arg-type]
