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

import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
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
from shared.logger_global import get_logger

log = get_logger(__name__, service="ai_brain")

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

ALIGNMENT_DOCTRINE = (
    "Answer the requirement that was asked. /project/*/REQUIREMENTS.md gives the "
    "wording and target of every R-id; read it before emitting. A quote is "
    "evidence only for the requirement it actually addresses — pricing text is "
    "not a relationship disclosure, a CV is not a certification date, and a "
    "disclaimer is not a CSR statement. If the bid never addresses a "
    "requirement, that requirement is not_stated: an unanswered requirement is "
    "a normal, expected outcome and is far more useful than a quote that does "
    "not fit. Never spread one quote across several requirements to fill the "
    "table.\n"
)

VENDOR_ANALYST_PROMPT = STABLE_RULES + CITATION_DOCTRINE + ALIGNMENT_DOCTRINE + (
    "The bid corpus is packed under /project/*/vendors/<bid>/_chunks/. "
    "Use ls/grep/read_file on those files and the RFP. "
    "Each _chunks/NNN.md file is sized to be read in ONE call: always pass "
    "limit=1200 to read_file so you get the whole file, never the 100-line "
    "default. Files are ordered by relevance, so 000.md is the most likely to "
    "answer requirements. "
    "Use MCP search_project_kb, read_chunk, read_chunks, or read_chunk_window only "
    "to re-open a cited chunk_id. If you call MCP reads, emit several in one turn. "
    "Do not emit a schema in this step.\n"
)

VENDOR_EMIT_PROMPT = STABLE_RULES + CITATION_DOCTRINE + ALIGNMENT_DOCTRINE + (
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
            or path.endswith("REQUIREMENTS.md")
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
    from ai_brain.core.kb.api.mcp_tools import CHUNK_FILE_LINES, chunk_manifest_block

    files, packed_ids = files_for_bid(project_id, bid_id)
    index = chunk_manifest_block(project_id, bid_id)
    pack_files = sorted(p for p in files if f"/vendors/{bid_id}/_chunks/" in p)
    content = (
        f"Analyse bid `{bid_id}` only. Corpus is under "
        f"/project/*/vendors/{bid_id}/_chunks/ — ls/grep/read_file there and the RFP. "        "Read /project/*/REQUIREMENTS.md FIRST: it gives the wording and target "
        "of every R-id, and a quote that does not address that wording is "
        "`not_stated`, never `met`. "        f"There are {len(pack_files)} pack files, ordered most-relevant first. "
        f"Read each with read_file(path, limit={CHUNK_FILE_LINES}) so one call "
        "returns the whole file; the default limit of 100 lines would give you "
        "only a fraction of it. "
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


def emit_middleware(fallback_model: Any, *, run_limit: int = 15) -> list[Any]:
    """Middleware for ToolStrategy emit agents (no MCP tools).

    `run_limit` is per emit agent: a schema covering every bid against every
    requirement needs more retries than a single-answer one before the cap
    turns a recoverable validation error into a dead run.
    """
    return [
        ModelCallLimitMiddleware(run_limit=run_limit, exit_behavior="error"),
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
    primary = model or _llm(get_extract_model_kind())
    fast = fallback_model if fallback_model is not None else _llm("fast")
    agent_tools = tools if tools is not None else langchain_kb_tools()
    backend = StateBackend()
    return create_deep_agent(
        model=primary,
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

    primary = model or _llm(get_extract_model_kind())
    fast = fallback_model if fallback_model is not None else _llm("fast")
    return create_agent(
        model=primary,
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
    primary = model or _llm(get_extract_model_kind())
    fast = fallback_model if fallback_model is not None else _llm("fast")
    return create_agent(
        model=primary,
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

    primary = model or _llm(get_extract_model_kind())
    fast = fallback_model if fallback_model is not None else _llm("fast")
    return create_agent(
        model=primary,
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
    primary = model or _llm(get_extract_model_kind())
    fast = fallback_model if fallback_model is not None else _llm("fast")
    return create_agent(
        model=primary,
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


def get_extract_model_kind() -> str:
    from ai_brain.core.config.llm import get_extract_model_kind as _kind

    return _kind()


def _llm(kind: str):
    from ai_brain.core.config.llm import get_llm

    return get_llm(kind, max_tokens=EXTRACT_MAX_TOKENS)  # type: ignore[arg-type]


ALIGNMENT_VERIFIER_PROMPT = (
    "You check whether a quote answers the requirement it was filed under. "
    "This is the only question you answer; you do not grade the bidder, and "
    "you do not judge whether the answer is good.\n"
    "addresses=true only when the quote speaks to what the requirement asks. "
    "Wording may differ completely from the requirement: a bidder writing "
    "'sustainability rating' does answer a requirement about EcoVadis, and a "
    "bidder naming a start month does answer a requirement about project "
    "start. Judge meaning, not shared words.\n"
    "addresses=false when the quote is about something else, even if it comes "
    "from the same document and sounds relevant: a day rate is not a signed "
    "NDA, a CV is not a certification date, a liability disclaimer is not a "
    "CSR statement, and a general statement of approach answers no specific "
    "requirement.\n"
    "false is the expected answer for many cases. Return one verdict per case, "
    "in the order given, reusing the requirement_id verbatim."
)


def build_alignment_verifier(*, model: Any | None = None, fallback_model: Any | None = None):
    """Structured-output judge for claim-to-requirement fit. No tools."""
    from langchain.agents import create_agent
    from langchain.agents.structured_output import ToolStrategy

    from ai_brain.core.kb.api.schemas import AlignmentReview

    primary = model or _llm("fast")
    fast = fallback_model if fallback_model is not None else _llm("fast")
    return create_agent(
        model=primary,
        tools=[],
        system_prompt=ALIGNMENT_VERIFIER_PROMPT,
        response_format=ToolStrategy(AlignmentReview, handle_errors=True),
        middleware=emit_middleware(fast),
        checkpointer=None,
        name="alignment_verifier",
    )


# Keeps one judgement call per bid at a size the fast model answers reliably.
ALIGNMENT_BATCH = 20
# The judge runs inside the evidence write, after the analyst may already have
# spent its soft budget, and the LLM client sets no request timeout. The node
# keeps ~180s of margin, so staying under that stops a slow judge from costing
# the bid the extraction it already paid for.
ALIGNMENT_BUDGET_S = 120.0
# One call's share of the budget. `llm.py` sets no request timeout and retries
# five times, so a stalled endpoint has nothing of its own to stop it.
ALIGNMENT_CALL_TIMEOUT_S = 60.0


def _invoke_bounded(agent: Any, payload: dict, timeout_s: float) -> Any:
    """Bound the wait, not the request.

    The worker thread cannot be killed, but it can be abandoned: returning
    control lets the caller fall back to term overlap, where blocking would
    have cost the bid the extraction it already paid for.
    """
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="alignment")
    try:
        return pool.submit(agent.invoke, payload).result(timeout=timeout_s)
    except FutureTimeout as exc:
        raise TimeoutError(
            f"alignment verifier call exceeded {timeout_s:.0f}s"
        ) from exc
    finally:
        pool.shutdown(wait=False)


REQUIREMENT_SOURCER_PROMPT = (
    "You locate the tender's own wording for a requirement. Each case gives a "
    "short requirement label and numbered candidate passages from the RFP.\n"
    "Return the passage that states this requirement, copied VERBATIM from one "
    "candidate. Copy the sentence or two that carry the ask, not a whole page.\n"
    "The label is a summary someone else wrote; the RFP may word it completely "
    "differently. Match on meaning, not shared words.\n"
    "If no candidate states this requirement, return passage=null. Abstaining "
    "is correct and expected: a label may summarise a grid the RFP never spells "
    "out. Never write a passage of your own.\n"
    "Reuse requirement_id verbatim and set artifact_id to the candidate's."
)


def build_requirement_sourcer(*, model: Any | None = None, fallback_model: Any | None = None):
    """Structured-output locator for a requirement's wording in the RFP."""
    from langchain.agents import create_agent
    from langchain.agents.structured_output import ToolStrategy

    from ai_brain.core.kb.api.schemas import RequirementSourceBundle

    primary = model or _llm("fast")
    fast = fallback_model if fallback_model is not None else _llm("fast")
    return create_agent(
        model=primary,
        tools=[],
        system_prompt=REQUIREMENT_SOURCER_PROMPT,
        response_format=ToolStrategy(RequirementSourceBundle, handle_errors=True),
        middleware=emit_middleware(fast),
        checkpointer=None,
        name="requirement_sourcer",
    )


# Passages run long, so fewer per call than the alignment judge.
SOURCING_BATCH = 8
SOURCING_BUDGET_S = 240.0


def _normalise(text: str | None) -> str:
    return " ".join((text or "").casefold().split())


def source_requirements(
    cases: list[dict[str, Any]],
    *,
    budget_s: float = SOURCING_BUDGET_S,
    call_timeout_s: float = ALIGNMENT_CALL_TIMEOUT_S,
) -> dict[str, dict[str, Any]]:
    """requirement_id -> {passage, artifact_id, page}. Unlocated ids are absent.

    Runs once per project rather than per bid, so a partial result is kept:
    a batch that fails leaves its requirements on the template wording.
    """
    if not cases:
        return {}
    agent = build_requirement_sourcer()
    deadline = time.monotonic() + budget_s
    found: dict[str, dict[str, Any]] = {}
    for start in range(0, len(cases), SOURCING_BATCH):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            log.warning("requirement sourcing hit its budget after {} ids", len(found))
            break
        batch = cases[start : start + SOURCING_BATCH]
        blocks = []
        for case in batch:
            candidates = "\n".join(
                f"   [{i + 1}] artifact_id={c['artifact_id']} page={c.get('page')}\n"
                f"       {c['text']}"
                for i, c in enumerate(case["candidates"])
            )
            blocks.append(
                f"requirement_id={case['requirement_id']}\n"
                f"label: {case['label']}\n"
                f"target: {case.get('target') or ''}\n"
                f"candidates:\n{candidates}"
            )
        try:
            result = _invoke_bounded(
                agent,
                {
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                f"Locate the wording for these {len(batch)} "
                                "requirements.\n\n" + "\n\n".join(blocks)
                            ),
                        }
                    ]
                },
                min(call_timeout_s, remaining),
            )
        except Exception as exc:  # noqa: BLE001 - keep what earlier batches found
            log.warning("requirement sourcing batch failed: {}", exc)
            continue
        bundle = result.get("structured_response") if isinstance(result, dict) else None
        by_id = {c["requirement_id"]: c for c in batch}
        for source in list(getattr(bundle, "sources", []) or []):
            case = by_id.get((source.requirement_id or "").strip())
            if case is None or not (source.passage or "").strip():
                continue
            # The passage must exist in a candidate we supplied, or the tender is
            # being quoted words it never contained.
            hit = next(
                (
                    c
                    for c in case["candidates"]
                    if _normalise(source.passage) in _normalise(c["text"])
                ),
                None,
            )
            if hit is None:
                log.warning(
                    "requirement {} passage absent from its candidates; dropped",
                    source.requirement_id,
                )
                continue
            found[case["requirement_id"]] = {
                "passage": source.passage.strip(),
                "artifact_id": hit["artifact_id"],
                "page": hit.get("page"),
            }
    return found


def verify_alignment(
    cases: list[dict[str, str]],
    *,
    budget_s: float = ALIGNMENT_BUDGET_S,
    call_timeout_s: float = ALIGNMENT_CALL_TIMEOUT_S,
) -> list[bool]:
    """One boolean per case, in order. Raises so the caller can fall back."""
    if not cases:
        return []
    agent = build_alignment_verifier()
    deadline = time.monotonic() + budget_s
    out: list[bool] = []
    for start in range(0, len(cases), ALIGNMENT_BATCH):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(
                f"alignment verifier exceeded {budget_s}s after {len(out)} cases"
            )
        batch = cases[start : start + ALIGNMENT_BATCH]
        lines = [
            f"{i + 1}. requirement_id={case['requirement_id']}\n"
            f"   requirement: {case['requirement']}\n"
            f"   target: {case['target']}\n"
            f"   quote: {case['claim']}"
            for i, case in enumerate(batch)
        ]
        result = _invoke_bounded(
            agent,
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"Judge these {len(batch)} cases and return "
                            f"{len(batch)} verdicts in order.\n\n"
                            + "\n\n".join(lines)
                        ),
                    }
                ]
            },
            min(call_timeout_s, remaining),
        )
        review = result.get("structured_response") if isinstance(result, dict) else None
        verdicts = list(getattr(review, "verdicts", []) or [])
        if len(verdicts) != len(batch):
            raise ValueError(
                f"alignment verifier returned {len(verdicts)} verdicts for {len(batch)} cases"
            )
        # Trusting position alone would re-create the bug this judge exists to
        # catch, one layer up: a reordered reply would retire the wrong claims.
        for case, verdict in zip(batch, verdicts):
            if (verdict.requirement_id or "").strip() != case["requirement_id"]:
                raise ValueError(
                    "alignment verifier replied out of order: expected "
                    f"{case['requirement_id']}, got {verdict.requirement_id}"
                )
        out.extend(bool(v.addresses) for v in verdicts)
    return out
