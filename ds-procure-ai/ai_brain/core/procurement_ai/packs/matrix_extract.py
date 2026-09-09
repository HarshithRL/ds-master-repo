"""Fill comparison matrices via LangChain create_agent structured output."""

from __future__ import annotations

import os
from typing import Any

from shared.logger_global import get_logger

from ai_brain.core.procurement_ai.packs.matrix_layout import (
    BAFO_ATTRS,
    BAFO_ROWS,
    CORPUS_CHAR_LIMIT,
    EXTRACT_MAX_TOKENS,
    SWIFT_REQUIREMENTS,
)
from ai_brain.core.procurement_ai.packs.matrix_schema import (
    DirectMatrix,
    IndirectMatrix,
    IndirectVendorFacts,
    RequirementCell,
    blank_indirect_vendor,
)
from ai_brain.core.procurement_ai.process_type import DIRECT_TG

log = get_logger(__name__, service="ai_brain")


def llm_extract_enabled() -> bool:
    if os.getenv("PYTEST_CURRENT_TEST"):
        return False
    if os.getenv("MATE_MATRIX_LLM", "1").strip() == "0":
        return False
    return True


def corpus_from_chunks(chunks: list[Any], artifacts: list[Any] | None = None) -> str:
    names = {
        getattr(artifact, "id", ""): getattr(artifact, "original_name", "") or ""
        for artifact in artifacts or []
    }
    grouped: dict[str, list[Any]] = {}
    for chunk in chunks or []:
        grouped.setdefault(getattr(chunk, "artifact_id", "") or "_", []).append(chunk)
    queues = [list(group) for group in grouped.values() if group]
    parts: list[str] = []
    used = 0
    while queues and used < CORPUS_CHAR_LIMIT:
        next_queues: list[list[Any]] = []
        for queue in queues:
            chunk = queue.pop(0)
            text = (getattr(chunk, "text", "") or "").strip()
            if text:
                label = names.get(getattr(chunk, "artifact_id", ""), "") or "document"
                block = f"[{label}]\n{text}\n"
                if used + len(block) > CORPUS_CHAR_LIMIT:
                    remain = CORPUS_CHAR_LIMIT - used
                    if remain > 200:
                        parts.append(block[:remain])
                    return "\n".join(parts).strip()
                parts.append(block)
                used += len(block)
            if queue:
                next_queues.append(queue)
        queues = next_queues
    return "\n".join(parts).strip()


async def extract_matrix(
    insights: dict[str, Any],
    source_text: str,
    *,
    chunks: list[Any] | None = None,
    artifacts: list[Any] | None = None,
    config: dict[str, Any] | None = None,
) -> IndirectMatrix | DirectMatrix | None:
    """Run LangChain structured extract. Returns None if skipped or the LLM fails."""
    from ai_brain.server.tracing import is_checkpoint_sync_error

    if not llm_extract_enabled():
        log.info("matrix extract skipped (tests or MATE_MATRIX_LLM=0)")
        return None
    if not source_text.strip():
        log.info("matrix extract skipped (no parsed text)")
        return None
    process = insights.get("process_type") or ""
    try:
        if process == DIRECT_TG:
            payload = await _ainvoke_structured(
                DirectMatrix,
                _user_prompt(insights, source_text, process),
                config=config,
            )
        else:
            payload = await _extract_indirect(
                insights, source_text, chunks or [], artifacts or [], config=config
            )
    except Exception as exc:  # noqa: BLE001
        if is_checkpoint_sync_error(exc):
            raise
        log.warning("matrix extract llm failed: {}", exc)
        return None
    if payload is None:
        log.warning("matrix extract returned no structured_response")
        return None
    log.info("matrix extract llm ok schema={}", type(payload).__name__)
    return payload


async def _extract_indirect(
    insights: dict[str, Any],
    source_text: str,
    chunks: list[Any],
    artifacts: list[Any],
    *,
    config: dict[str, Any] | None = None,
) -> IndirectMatrix | None:
    names = [v.get("name") or "Unnamed vendor" for v in insights.get("vendors") or []]
    if not names:
        names = ["Unnamed vendor"]
    rfp_text = _rfp_corpus(chunks, artifacts)
    vendors: list[IndirectVendorFacts] = []
    for name in names:
        vendor_text = _vendor_corpus(name, chunks, artifacts) or source_text
        prompt = _user_prompt(
            insights,
            f"{rfp_text}\n\n{vendor_text}".strip(),
            insights.get("process_type") or "",
            vendor_name=name,
        )
        fact = await _ainvoke_structured(IndirectVendorFacts, prompt, config=config)
        if fact is None:
            vendors.append(blank_indirect_vendor(name))
            continue
        vendors.append(fact.model_copy(update={"name": name}))
        log.info("matrix extract vendor ok name={}", name)
    requirements = []
    for rid, label, _cat, _target in SWIFT_REQUIREMENTS:
        marks = {
            vendor.name: (vendor.requirement_marks or {}).get(rid) or "missing"
            for vendor in vendors
        }
        requirements.append(RequirementCell(requirement_id=rid, vendor_marks=marks))
    return IndirectMatrix(vendors=vendors, requirements=requirements)


def empty_indirect(insights: dict[str, Any]) -> IndirectMatrix:
    vendors = [
        blank_indirect_vendor(vendor.get("name") or "Unnamed vendor")
        for vendor in insights.get("vendors") or []
    ]
    if not vendors:
        vendors = [blank_indirect_vendor("Unnamed vendor")]
    return IndirectMatrix(vendors=vendors)


def empty_direct(insights: dict[str, Any]) -> DirectMatrix:
    from ai_brain.core.procurement_ai.packs.matrix_schema import DirectVendorTerms

    vendors = [
        DirectVendorTerms(name=vendor.get("name") or "Unnamed vendor")
        for vendor in insights.get("vendors") or []
    ]
    if not vendors:
        vendors = [DirectVendorTerms(name="Unnamed vendor")]
    return DirectMatrix(vendors=vendors)


async def _ainvoke_structured(schema: type, prompt: str, *, config: dict[str, Any] | None = None):
    from langchain.agents import create_agent

    from ai_brain.core.config import get_llm
    from ai_brain.core.utils import read_prompt
    from ai_brain.server.tracing import child_runnable_config, is_checkpoint_sync_error

    llm = get_llm(max_tokens=EXTRACT_MAX_TOKENS)
    nested = child_runnable_config(config if isinstance(config, dict) else None)
    try:
        agent = create_agent(
            model=llm,
            tools=[],
            system_prompt=read_prompt("matrix_extract.md"),
            response_format=schema,
            checkpointer=None,
        )
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": prompt}]},
            config=nested,
        )
        payload = result.get("structured_response") if isinstance(result, dict) else None
        if payload is not None:
            return payload
        log.warning("create_agent returned no structured_response; trying with_structured_output")
    except Exception as exc:  # noqa: BLE001
        if is_checkpoint_sync_error(exc):
            raise
        log.warning("create_agent response_format failed: {}", exc)
    return await llm.with_structured_output(schema).ainvoke(prompt)


_PRICE_HINTS = ("eur", "€", "fee", "day", "tco", "price", "rate", "manday", "man-day", "blended", "fixed")


def _vendor_corpus(vendor_name: str, chunks: list[Any], artifacts: list[Any], limit: int = 12_000) -> str:
    from ai_brain.core.procurement_ai.insights import _vendor_name

    ids = {
        getattr(artifact, "id", "")
        for artifact in artifacts
        if _vendor_name(getattr(artifact, "original_name", "") or "") == vendor_name
    }
    subset = [chunk for chunk in chunks if getattr(chunk, "artifact_id", "") in ids]
    priced = []
    rest = []
    for chunk in subset:
        blob = (getattr(chunk, "text", "") or "").lower()
        (priced if any(hint in blob for hint in _PRICE_HINTS) else rest).append(chunk)
    return corpus_from_chunks(priced + rest, artifacts)[:limit]


def _rfp_corpus(chunks: list[Any], artifacts: list[Any], limit: int = 4_000) -> str:
    ids = {
        getattr(artifact, "id", "")
        for artifact in artifacts
        if "rfp" in (getattr(artifact, "original_name", "") or "").lower()
    }
    subset = [chunk for chunk in chunks if getattr(chunk, "artifact_id", "") in ids]
    text = corpus_from_chunks(subset, artifacts)[:limit]
    return f"[RFP]\n{text}" if text else ""


def _user_prompt(
    insights: dict[str, Any],
    source_text: str,
    process: str,
    *,
    vendor_name: str | None = None,
) -> str:
    vendor_names = [v.get("name") or "Unnamed vendor" for v in insights.get("vendors") or []]
    files = []
    for vendor in insights.get("vendors") or []:
        files.append(f"- {vendor.get('name')}: {vendor.get('headline') or ''}")
    reqs = "\n".join(
        f"- {rid}: {label}" for rid, label, _cat, _target in SWIFT_REQUIREMENTS
    )
    kind = "Direct TG P×Q / samples / commercial terms / ranking" if process == DIRECT_TG else (
        "Indirect IT BAFO comparison (SWIFT CSP Vendor Comparison.xlsx layout)"
    )
    field_map = "\n".join(
        f"- {attr}: {label}"
        for (label, _typ), attr in zip(BAFO_ROWS, BAFO_ATTRS, strict=True)
        if label and attr
    )
    target = vendor_name or ", ".join(vendor_names) or "none listed"
    return (
        f"Process: {process or 'unset'} ({kind})\n"
        f"Project: {insights.get('project_code') or ''} {insights.get('project_name') or ''}\n"
        f"{'Fill this one vendor only: ' + vendor_name if vendor_name else 'Vendors (emit one object per name): ' + target}\n"
        f"Files:\n{chr(10).join(files) or '- none'}\n\n"
        "Map BAFO cells onto these vendor fields. Copy quoted EUR / days / scores. "
        "If the source does not state a figure, write missing.\n"
        f"{field_map}\n\n"
        "Put requirement marks in requirement_marks keyed by R01..R40 (✓ ~ ✗ ? or missing).\n"
        f"{reqs}\n\n"
        "Source text from parsed uploads:\n"
        f"{source_text}\n"
    )
