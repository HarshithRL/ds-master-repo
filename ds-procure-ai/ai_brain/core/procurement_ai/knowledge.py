"""Project knowledge base for workspace chat — parsed chunks, retrieved into create_agent."""

from __future__ import annotations

import json
import re
from typing import Any

from ai_brain.core.procurement_ai.insights import build_insight_payload
from ai_brain.core.procurement_ai.project_context import load_context

HIT_LIMIT = 8
HIT_CHAR_LIMIT = 900
BLOCK_CHAR_LIMIT = 12_000
EVIDENCE_REQ_LIMIT = 12
EVIDENCE_CELL_CHARS = 160
PRICING_LINE_LIMIT = 16
_TOKEN = re.compile(r"[a-z0-9]{3,}")
_STOP = frozenset(
    {
        "the",
        "and",
        "for",
        "this",
        "that",
        "what",
        "who",
        "how",
        "are",
        "was",
        "with",
        "from",
        "about",
        "project",
        "please",
        "tell",
        "give",
        "ask",
    }
)


def knowledge_prompt_block(project_id: str, query: str) -> str:
    """Return a system-prompt block of project facts + ranked excerpts, or empty."""
    pid = (project_id or "").strip()
    if not pid:
        return ""
    project, artifacts, chunks = load_context(pid)
    if project is None:
        return (
            "## Project knowledge base\n"
            "No project is attached to this thread. Do not invent files, prices, or scores."
        )
    insights = build_insight_payload(project, artifacts, chunks)
    source = _matrix_source(pid)
    if source is not None and source.warm:
        from ai_brain.core.procurement_ai.packs.matrix_from_evidence import insights_from_source

        insights = insights_from_source(insights, source)
    parts = ["## Project knowledge base", _header(insights)]
    evidence = _structured_evidence_block(source, query) if source is not None else ""
    if evidence:
        parts.append(evidence)
    excerpts = _retrieved_excerpts(pid, query, artifacts, chunks)
    if excerpts:
        parts.append(excerpts)
    elif not chunks and not evidence:
        parts.append(
            "No parsed excerpts yet. Answer from the header only; say missing for facts not in files."
        )
    elif not excerpts:
        parts.append("No excerpt matched this question. Use structured evidence or say missing.")
    return "\n".join(parts)


def _matrix_source(project_id: str):
    try:
        from ai_brain.core.procurement_ai.packs.matrix_from_evidence import load_matrix_source

        return load_matrix_source(project_id)
    except Exception:
        return None


def _retrieved_excerpts(
    project_id: str,
    query: str,
    artifacts: list[Any],
    chunks: list[Any],
) -> str:
    hybrid = _hybrid_excerpts(project_id, query)
    if hybrid:
        return (
            "### Retrieved excerpts\n"
            "Cite file + locator. No citation = opinion. Do not invent numbers.\n"
            f"{hybrid}"
        )
    hits = search_chunks(query, artifacts, chunks)
    if not hits:
        return ""
    parts = [
        "### Retrieved excerpts",
        "Cite file + locator. No citation = opinion. Do not invent numbers.",
    ]
    used = 0
    for hit in hits:
        block = _format_hit(hit)
        if used + len(block) > BLOCK_CHAR_LIMIT:
            break
        parts.append(block)
        used += len(block)
    return "\n".join(parts)


def _hybrid_excerpts(project_id: str, query: str) -> str:
    try:
        from ai_brain.core.kb.search import search_kb

        return (search_kb(query, k=HIT_LIMIT, project_id=project_id) or "").strip()
    except Exception:
        return ""


def _structured_evidence_block(source: Any, query: str) -> str:
    if source is None or not getattr(source, "warm", False):
        return ""
    parts = ["### Structured evidence (SQL after kb_build)", str(source.summary or "").strip()]
    flags = list(getattr(source, "flags", None) or [])
    if flags:
        parts.append("Quality flags: " + "; ".join(str(flag) for flag in flags[:8]))
    reqs = _rank_requirements(list(getattr(source, "requirements", None) or []), query)
    bids = list(getattr(source, "bids", None) or [])
    cells = getattr(source, "cells", None) or {}
    labels = getattr(source, "bid_labels", None) or {}
    used = 0
    if reqs and bids:
        parts.append("Requirement × bid (status + claim). not_stated ≠ not_offered ≠ extraction_failed.")
        for req in reqs:
            line = _requirement_evidence_line(req, bids, cells, labels)
            if used + len(line) > BLOCK_CHAR_LIMIT:
                break
            parts.append(line)
            used += len(line)
    pricing = _pricing_lines(source)
    if pricing:
        parts.append("### Pricing lines")
        parts.extend(pricing)
    return "\n".join(part for part in parts if part)


def _rank_requirements(requirements: list[Any], query: str) -> list[Any]:
    if not requirements:
        return []
    terms = _query_tokens(query)
    scored: list[tuple[int, int, Any]] = []
    for req in requirements:
        text = " ".join(
            str(part or "")
            for part in (
                getattr(req, "id", ""),
                getattr(req, "text", ""),
                getattr(req, "section", ""),
                getattr(req, "category", ""),
            )
        )
        score = _score(terms, text, "", "")
        scored.append((score, int(getattr(req, "ordinal", 0) or 0), req))
    scored.sort(key=lambda item: (-item[0], item[1]))
    selected = [item[2] for item in scored if item[0] > 0][:EVIDENCE_REQ_LIMIT]
    if selected:
        return selected
    return [item[2] for item in scored[: min(8, len(scored))]]


def _requirement_evidence_line(
    req: Any,
    bids: list[str],
    cells: dict,
    labels: dict[str, str],
) -> str:
    rid = str(getattr(req, "id", "") or "")
    label = (getattr(req, "text", "") or rid).strip().replace("\n", " ")
    if len(label) > 80:
        label = label[:77] + "..."
    cells_out: list[str] = []
    for bid in bids:
        cell = cells.get((rid, bid))
        name = labels.get(bid) or bid
        if cell is None:
            cells_out.append(f"{name}=missing")
            continue
        status = getattr(cell, "status", "") or "missing"
        body = (getattr(cell, "text", "") or status).strip().replace("\n", " ")
        if len(body) > EVIDENCE_CELL_CHARS:
            body = body[: EVIDENCE_CELL_CHARS - 3] + "..."
        page = getattr(cell, "page", None)
        cite = f" p.{page}" if page is not None else ""
        cells_out.append(f"{name}={status}{cite}: {body}" if body != status else f"{name}={status}{cite}")
    return f"- {rid} {label}: " + " | ".join(cells_out)


def _pricing_lines(source: Any) -> list[str]:
    lines: list[str] = []
    for row in list(getattr(source, "pricing_lines", None) or [])[:PRICING_LINE_LIMIT]:
        bid = (getattr(row, "vendor_id", "") or "").strip() or "unknown"
        role = (getattr(row, "role", "") or "").strip()
        seniority = (getattr(row, "seniority", "") or "").strip()
        offer = (getattr(row, "offer_type", "") or "").strip()
        rate = getattr(row, "rate", None)
        unit = (getattr(row, "rate_unit", "") or "").strip()
        currency = (getattr(row, "currency", "") or "").strip()
        total = getattr(row, "line_total", None)
        page = getattr(row, "page", None)
        bits = [bid, offer]
        if role:
            bits.append(role)
        if seniority:
            bits.append(seniority)
        amount = f"{rate} {currency}/{unit}".strip(" /") if rate is not None else ""
        if total is not None:
            amount = f"{amount} total={total} {currency}".strip()
        if page is not None:
            amount = f"{amount} [p.{page}]".strip()
        detail = " ".join(part for part in bits if part)
        lines.append(f"- {detail}: {amount or 'missing'}")
    return lines


def search_chunks(
    query: str,
    artifacts: list[Any],
    chunks: list[Any],
    *,
    limit: int = HIT_LIMIT,
) -> list[dict[str, Any]]:
    names = {
        getattr(artifact, "id", ""): getattr(artifact, "original_name", "") or "document"
        for artifact in artifacts or []
    }
    terms = _query_tokens(query)
    scored: list[tuple[int, int, Any]] = []
    for ordinal, chunk in enumerate(chunks or []):
        text = (getattr(chunk, "text", "") or "").strip()
        if not text:
            continue
        filename = names.get(getattr(chunk, "artifact_id", ""), "document")
        score = _score(terms, text, filename, _heading(chunk))
        scored.append((score, ordinal, chunk))
    scored.sort(key=lambda item: (-item[0], item[1]))
    selected = [item for item in scored if item[0] > 0][:limit]
    if not selected:
        selected = scored[: min(3, len(scored))]
    hits: list[dict[str, Any]] = []
    for score, _ordinal, chunk in selected:
        filename = names.get(getattr(chunk, "artifact_id", ""), "document")
        text = (getattr(chunk, "text", "") or "").strip()
        hits.append(
            {
                "file": filename,
                "locator": chunk_locator(chunk),
                "heading": _heading(chunk),
                "text": text[:HIT_CHAR_LIMIT],
                "score": score,
            }
        )
    return hits


def chunk_locator(chunk: Any) -> str:
    raw = getattr(chunk, "location_json", None)
    if not raw:
        raw = getattr(chunk, "location", None)
    if not raw:
        return f"chunk {getattr(chunk, 'ordinal', 0)}"
    try:
        loc = json.loads(raw) if isinstance(raw, str) else dict(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return f"chunk {getattr(chunk, 'ordinal', 0)}"
    if loc.get("page") is not None:
        return f"p.{loc['page']}"
    if loc.get("slide") is not None:
        return f"slide {loc['slide']}"
    if loc.get("sheet"):
        return str(loc["sheet"])
    return loc.get("locator") or f"chunk {getattr(chunk, 'ordinal', 0)}"


def _header(insights: dict[str, Any]) -> str:
    vendors = ", ".join(
        str(vendor.get("name") or "").strip()
        for vendor in insights.get("vendors") or []
        if vendor.get("name")
    )
    return (
        f"Project: {insights.get('project_code') or ''} {insights.get('project_name') or ''}\n"
        f"Process: {insights.get('process_type') or 'unset'} · KB {insights.get('kb_status') or 'empty'}\n"
        f"Files: {insights.get('file_count') or 0} uploaded, {insights.get('parsed_ok') or 0} parsed\n"
        f"Vendors: {vendors or 'none yet'}"
    )


def _format_hit(hit: dict[str, Any]) -> str:
    heading = hit.get("heading") or ""
    title = f"[{hit.get('file') or 'document'} · {hit.get('locator') or 'excerpt'}]"
    if heading:
        title = f"{title} {heading}"
    return f"{title}\n{hit.get('text') or ''}"


def _heading(chunk: Any) -> str:
    raw = getattr(chunk, "heading_path_json", None)
    if not raw:
        path = getattr(chunk, "heading_path", None)
        if isinstance(path, (list, tuple)):
            return " > ".join(str(part) for part in path if part)
        return ""
    try:
        path = json.loads(raw) if isinstance(raw, str) else list(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return ""
    return " > ".join(str(part) for part in path if part)


def _query_tokens(query: str) -> set[str]:
    return {token for token in _TOKEN.findall((query or "").lower()) if token not in _STOP}


def _score(terms: set[str], text: str, filename: str, heading: str) -> int:
    if not terms:
        return 1
    hay = f"{filename} {heading} {text}".lower()
    hay_tokens = set(_TOKEN.findall(hay))
    overlap = terms & hay_tokens
    if not overlap:
        return 0
    return len(overlap) * 10 + sum(hay.count(token) for token in overlap)
