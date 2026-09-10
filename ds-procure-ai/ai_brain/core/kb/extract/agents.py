"""Vendor analyst harness: Deep Agent research + create_agent ToolStrategy emit.

Research uses ``create_deep_agent`` with StateBackend files + MCP tools.
Emit stays ``create_agent`` + ``ToolStrategy`` because ChatDatabricks cannot mix
MCP tools and structured output on the same agent.

https://docs.langchain.com/oss/python/deepagents/tools#mcp-tools
https://docs.langchain.com/oss/python/langchain/mcp
https://docs.langchain.com/oss/python/langchain/structured-output
https://docs.langchain.com/oss/python/deepagents/backends
"""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ModelFallbackMiddleware,
    ModelRetryMiddleware,
    ToolCallLimitMiddleware,
    ToolRetryMiddleware,
)

from ai_brain.core.kb.build.coverage import CoverageMiddleware
from ai_brain.core.kb.middleware.strip_tool_content_ids import StripToolContentIdsMiddleware
from ai_brain.core.kb.store.materialize import project_files, vendor_paths
from ai_brain.core.kb.api.schemas import BidProfile, PricingExtraction, VendorEvidenceBundle
from ai_brain.core.procurement_ai.packs.matrix_layout import EXTRACT_MAX_TOKENS

STABLE_RULES = (
    "You are a procurement vendor analyst. Read only files under /project/.\n"
    "Do not invent requirements or bids. The bid id is artifact.vendor_id; "
    "a consortium is one bid with multiple legal entities.\n"
    "Write nothing under /project/ or /skills/.\n"
    "not_stated, not_offered, and extraction_failed are distinct states.\n"
)

CITATION_DOCTRINE = (
    "Citation-or-abstain: every status other than not_stated requires "
    "claim_text and (chunk_id or artifact_id + page). The claim_text must be a "
    "literal substring of the cited chunk. If you cannot cite a chunk or page, "
    "status is not_stated. Never treat filename as evidence; filenames may name the buyer.\n"
)

VENDOR_ANALYST_PROMPT = STABLE_RULES + CITATION_DOCTRINE + (
    "The bid corpus is packed under /project/*/vendors/<bid>/_chunks/. "
    "Use ls/grep/read_file on those files and the RFP. "
    "Use MCP search_project_kb, read_chunk, read_chunks, or read_chunk_window only "
    "to re-open a cited chunk_id. If you call MCP reads, emit several in one turn. "
    "Do not emit a schema in this step.\n"
)

VENDOR_EMIT_PROMPT = STABLE_RULES + CITATION_DOCTRINE + (
    "Finish by calling the VendorEvidenceBundle structured-output tool: "
    "one item per requirement (R01â€“R40). Use only facts already in this "
    "conversation. Do not call file tools.\n"
)

PRICING_PROMPT = (
    "Extract commercial terms from this bid's pricing material: rate cards, "
    "fixed-price vs T&M, Etex-side effort days, discounts, Annexe A02. "
    "Cite pages or chunk_id. Do not infer missing numbers. "
    "Finish by calling the PricingExtraction structured-output tool."
)

PROFILE_PROMPT = (
    "Extract BAFO commercial facts for this bid from the conversation: "
    "Y1â€“Y3 TCO strings, blended rate, mandays, timeline, EcoVadis, credit score, "
    "delivery model, assumptions, legal, Etex obligations, risk plan, "
    "scope completeness, missing requirements. "
    "Copy quoted figures. If the source does not state a figure, omit the field. "
    "Finish by calling the BidProfile structured-output tool."
)

MAX_COVERAGE_REFILLS = 2


def files_for_invoke(project_id: str) -> dict[str, dict[str, str]]:
    """Wrap `project_files` with FileData via `create_file_data`."""
    from deepagents.backends.utils import create_file_data

    files = {path: create_file_data(text) for path, text in project_files(project_id).items()}
    files.update(_skill_file_data())
    return files


def files_for_bid(project_id: str, bid_id: str) -> tuple[dict[str, dict[str, str]], list[str]]:
    """Path-scope: README + RFP + this vendor folder + packed chunks + skills."""
    from deepagents.backends.utils import create_file_data

    from ai_brain.core.kb.api.mcp_tools import prefetch_bid_chunks

    files = files_for_invoke(project_id)
    keep: dict[str, dict[str, str]] = {}
    vendor_prefix = f"/vendors/{bid_id}/"
    for path, data in files.items():
        if (
            vendor_prefix in path
            or "/rfp/" in path
            or path.endswith("README.md")
            or path.startswith("/skills/")
            or "/_quality/" in path
        ):
            keep[path] = data
    extra = vendor_paths(project_id, bid_id)
    for path in extra:
        if path not in keep and path in files:
            keep[path] = files[path]
    packed, packed_ids = prefetch_bid_chunks(project_id, bid_id)
    for path, text in packed.items():
        keep[path] = create_file_data(text)
    return keep, packed_ids


def _skill_file_data() -> dict[str, dict[str, str]]:
    from deepagents.backends.utils import create_file_data

    from ai_brain.core.kb.skills import iter_skill_files

    out: dict[str, dict[str, str]] = {}
    for name, path in iter_skill_files():
        if path.is_file():
            out[f"/skills/procurement/{name}/SKILL.md"] = create_file_data(
                path.read_text(encoding="utf-8")
            )
    return out


def invoke_payload(project_id: str, user_content: str) -> dict[str, Any]:
    """Input dict for agent.ainvoke â€” messages plus optional file map."""
    return {
        "messages": [{"role": "user", "content": user_content}],
        "files": files_for_invoke(project_id),
    }


def bid_invoke_payload(project_id: str, bid_id: str) -> dict[str, Any]:
    from ai_brain.core.kb.api.mcp_tools import chunk_manifest_block

    files, packed_ids = files_for_bid(project_id, bid_id)
    index = chunk_manifest_block(project_id, bid_id)
    content = (
        f"Analyse bid `{bid_id}` only. Corpus is under "
        f"/project/*/vendors/{bid_id}/_chunks/ â€” ls/grep/read_file there and the RFP. "
        "Use MCP search_project_kb / read_chunk / read_chunks / read_chunk_window only "
        "to re-open a cited id. If you call MCP reads, emit several in one turn. "
        "Gather cited facts for VendorEvidenceBundle (R01â€“R40) and BidProfile. "
        "Citation-or-abstain. Dual pricing (T&M and fixed) when present.\n\n"
        f"{index}"
    )
    return {
        "messages": [{"role": "user", "content": content}],
        "files": files,
        "packed_chunk_ids": packed_ids,
    }


def emit_user_message(bid_id: str) -> dict[str, str]:
    return {
        "role": "user",
        "content": (
            f"Call the VendorEvidenceBundle structured-output tool now for bid "
            f"`{bid_id}`. One item per requirement (R01â€“R40). Citation-or-abstain."
        ),
    }


def coverage_refill_message(unread: list[str]) -> dict[str, str]:
    preview = ", ".join(unread[:40])
    extra = "" if len(unread) <= 40 else f" (+{len(unread) - 40} more)"
    return {
        "role": "user",
        "content": (
            f"Coverage incomplete. Read these unread chunk_ids with read_chunk or "
            f"read_chunks, then continue gathering facts: {preview}{extra}"
        ),
    }


def extraction_middleware(fallback_model: Any) -> list[Any]:
    """User middleware for MCP research agents. TodoListMiddleware is not included.

    Includes StripToolContentIdsMiddleware so MCP tool_result blocks from
    langchain-mcp-adapters do not send Anthropic/FM-rejected id fields
    (langchain-mcp-adapters#397). Shared by comparison orchestrator and KB extract.
    """
    return [
        StripToolContentIdsMiddleware(),
        ModelCallLimitMiddleware(run_limit=30),
        ToolCallLimitMiddleware(run_limit=80),
        ModelRetryMiddleware(),
        ModelFallbackMiddleware(fallback_model),
        ToolRetryMiddleware(),
    ]


def emit_middleware(fallback_model: Any) -> list[Any]:
    """Middleware for ToolStrategy emit agents (no MCP tools)."""
    return [
        ModelCallLimitMiddleware(run_limit=15, exit_behavior="error"),
        ModelRetryMiddleware(),
        ModelFallbackMiddleware(fallback_model),
    ]


def build_vendor_analyst(
    *,
    model: Any | None = None,
    fallback_model: Any | None = None,
    store: Any | None = None,
    tools: list[Any] | None = None,
):
    """Deep-agent researcher. MCP + virtual files. No response_format. checkpointer=None."""
    from deepagents import create_deep_agent
    from deepagents.backends import StateBackend
    from deepagents.middleware.filesystem import FilesystemMiddleware

    from ai_brain.core.kb.api.mcp_tools import langchain_kb_tools

    del store
    thinking = model or _llm("thinking")
    fast = fallback_model if fallback_model is not None else _llm("fast")
    agent_tools = tools if tools is not None else langchain_kb_tools()
    backend = StateBackend()
    return create_deep_agent(
        model=thinking,
        tools=agent_tools,
        system_prompt=VENDOR_ANALYST_PROMPT,
        backend=backend,
        middleware=[
            FilesystemMiddleware(
                backend=backend,
                tools=["read_file", "ls", "glob", "grep"],
            ),
            CoverageMiddleware(),
            *extraction_middleware(fast),
        ],
        checkpointer=None,
        name="vendor_analyst",
    )


def build_vendor_emit(
    *,
    model: Any | None = None,
    fallback_model: Any | None = None,
):
    """Structured-output emit agent. tools=[] + ToolStrategy(VendorEvidenceBundle)."""
    from langchain.agents import create_agent
    from langchain.agents.structured_output import ToolStrategy

    thinking = model or _llm("thinking")
    fast = fallback_model if fallback_model is not None else _llm("fast")
    return create_agent(
        model=thinking,
        tools=[],
        system_prompt=VENDOR_EMIT_PROMPT,
        response_format=ToolStrategy(VendorEvidenceBundle, handle_errors=True),
        middleware=emit_middleware(fast),
        checkpointer=None,
        name="vendor_emit",
    )


def build_pricing_extractor(
    *,
    model: Any | None = None,
    fallback_model: Any | None = None,
    tools: list[Any] | None = None,
):
    """Pricing emit agent. No MCP tools â€” ToolStrategy only."""
    from langchain.agents import create_agent
    from langchain.agents.structured_output import ToolStrategy

    del tools
    thinking = model or _llm("thinking")
    fast = fallback_model if fallback_model is not None else _llm("fast")
    return create_agent(
        model=thinking,
        tools=[],
        system_prompt=PRICING_PROMPT,
        response_format=ToolStrategy(PricingExtraction, handle_errors=True),
        middleware=emit_middleware(fast),
        checkpointer=None,
        name="pricing_extractor",
    )


def build_profile_extractor(
    *,
    model: Any | None = None,
    fallback_model: Any | None = None,
):
    """BAFO BidProfile emit. No MCP tools â€” ToolStrategy only."""
    from langchain.agents import create_agent
    from langchain.agents.structured_output import ToolStrategy

    thinking = model or _llm("thinking")
    fast = fallback_model if fallback_model is not None else _llm("fast")
    return create_agent(
        model=thinking,
        tools=[],
        system_prompt=PROFILE_PROMPT,
        response_format=ToolStrategy(BidProfile, handle_errors=True),
        middleware=emit_middleware(fast),
        checkpointer=None,
        name="profile_extractor",
    )


def build_requirement_extractor(
    *,
    model: Any | None = None,
    fallback_model: Any | None = None,
    store: Any | None = None,
    tools: list[Any] | None = None,
):
    """RFP-only extractor. Stateless. Align to R01â€“R40."""
    from langchain.agents import create_agent

    from ai_brain.core.kb.api.mcp_tools import langchain_kb_tools

    del store
    thinking = model or _llm("thinking")
    fast = fallback_model if fallback_model is not None else _llm("fast")
    return create_agent(
        model=thinking,
        tools=tools if tools is not None else langchain_kb_tools(),
        system_prompt=(
            "Extract procurement requirements from /project/*/rfp/ only. "
            "Align to R01â€“R40. Extra requirements use ids R-E-001+. "
            "Cite artifact_id + page. Do not invent."
        ),
        middleware=extraction_middleware(fast),
        checkpointer=None,
        name="requirement_extractor",
    )


def _llm(kind: str):
    from ai_brain.core.config.llm import get_llm

    return get_llm(kind, max_tokens=EXTRACT_MAX_TOKENS)  # type: ignore[arg-type]
