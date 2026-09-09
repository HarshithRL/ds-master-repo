"""Build comparison matrices from SQL `evidence` + `pricing_line`. No LLM.

CURSOR-GUIDE §3: `not_stated` ≠ `not_offered` ≠ `extraction_failed`. Bid list
comes from SQL (`list_bid_ids`). Reviewed cells (`reviewed_by` set) win over
newer unreviewed extraction rows. File writers consume this module only.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any
import json

from sqlalchemy import select

from ai_brain.core.procurement_ai.packs.matrix_layout import (
    CONFIDENCE_FLOOR,
    EXTRACTION_FAILED,
    NOT_OFFERED,
    NOT_STATED,
    REVIEWED_MARK,
    SOURCE_QUALITY_PREFIX,
    STATUS_MARK,
    UNCERTAIN_PREFIX,
)
from ai_brain.core.procurement_ai.packs.matrix_schema import (
    DirectMatrix,
    DirectVendorTerms,
    IndirectMatrix,
    RequirementCell,
    blank_indirect_vendor,
)
from shared.db.connection import session_scope
from shared.db.models import Artifact, BidProfileRow, Evidence, PricingLine, QualityFlag, Requirement, Vendor
from shared.logger_global import get_logger

log = get_logger(__name__, service="ai_brain")

EVIDENCE_METHOD_NOTES = (
    "Rendered from SQL evidence + pricing_line. No LLM in the file-writing path. "
    "Cost rows use quoted figures when present; empty is missing, never zero. "
    "Cells with comments carry citation / derivation detail. "
    "not_stated ≠ not_offered ≠ extraction_failed. Reviewed cells are pinned. Humans award."
)


@dataclass(frozen=True)
class RenderedCell:
    status: str
    text: str
    pinned: bool = False
    source_quality_warning: str | None = None
    citation: str | None = None
    comment: str | None = None
    page: int | None = None
    artifact_id: str | None = None


@dataclass
class MatrixSource:
    project_id: str
    bids: list[str]
    bid_labels: dict[str, str]
    legal_names: dict[str, str]
    requirements: list[Requirement]
    cells: dict[tuple[str, str], RenderedCell]
    pricing_lines: list[PricingLine]
    profiles: dict[str, dict[str, Any]] = field(default_factory=dict)
    artifact_names: dict[str, str] = field(default_factory=dict)
    sources_by_bid: dict[str, list[str]] = field(default_factory=dict)
    rfp_sources: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    summary: str = ""

    @property
    def warm(self) -> bool:
        return bool(self.cells or self.pricing_lines or self.profiles)


def empty_source(project_id: str = "") -> MatrixSource:
    return MatrixSource(
        project_id=project_id,
        bids=[],
        bid_labels={},
        legal_names={},
        requirements=[],
        cells={},
        pricing_lines=[],
        profiles={},
    )


def load_matrix_source(project_id: str) -> MatrixSource:
    """Read evidence, pricing_line, requirements, and the SQL bid list."""
    if not project_id:
        return empty_source()
    try:
        return _load_matrix_source(project_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("matrix SQL read failed project_id={}: {}", project_id, exc)
        return empty_source(project_id)


def _load_matrix_source(project_id: str) -> MatrixSource:
    from ai_brain.core.kb.store.materialize import list_bid_ids

    sql_bids = list(list_bid_ids(project_id))
    with session_scope() as session:
        vendors = list(
            session.scalars(select(Vendor).where(Vendor.project_id == project_id)).all()
        )
        artifacts = list(
            session.scalars(select(Artifact).where(Artifact.project_id == project_id)).all()
        )
        requirements = list(
            session.scalars(
                select(Requirement)
                .where(Requirement.project_id == project_id)
                .order_by(Requirement.ordinal, Requirement.id)
            ).all()
        )
        evidence_rows = list(
            session.scalars(select(Evidence).where(Evidence.project_id == project_id)).all()
        )
        pricing_rows = list(
            session.scalars(
                select(PricingLine).where(PricingLine.project_id == project_id)
            ).all()
        )
        profile_rows = list(
            session.scalars(
                select(BidProfileRow).where(BidProfileRow.project_id == project_id)
            ).all()
        )
        quality_flags = list(
            session.scalars(
                select(QualityFlag).where(QualityFlag.project_id == project_id)
            ).all()
        )
        for row in (
            *vendors,
            *artifacts,
            *requirements,
            *evidence_rows,
            *pricing_rows,
            *profile_rows,
            *quality_flags,
        ):
            session.expunge(row)

    extra_bids = sorted(
        {
            (row.vendor_id or "").strip()
            for row in (*evidence_rows, *pricing_rows, *profile_rows)
            if (row.vendor_id or "").strip()
        }
    )
    bids: list[str] = list(sql_bids)
    seen = set(bids)
    for bid in extra_bids:
        if bid not in seen:
            bids.append(bid)
            seen.add(bid)

    bid_labels = {bid: _bid_label(bid, vendors) for bid in bids}
    legal_names = {bid: _legal_name(bid, vendors) for bid in bids}
    artifact_names = {
        art.id: (art.original_name or art.id) for art in artifacts if art.id
    }
    sources_by_bid, rfp_sources = _sources_from_artifacts(artifacts)
    high_by_artifact = _high_severity_by_artifact(quality_flags)
    grouped: dict[tuple[str, str], list[Evidence]] = defaultdict(list)
    for row in evidence_rows:
        req_id = (row.requirement_id or "").strip()
        bid = (row.vendor_id or "").strip()
        if req_id and bid:
            grouped[(req_id, bid)].append(row)

    cells: dict[tuple[str, str], RenderedCell] = {}
    for key, rows in grouped.items():
        chosen = pick_evidence_row(rows)
        cells[key] = render_evidence_cell(
            chosen,
            high_by_artifact.get(chosen.artifact_id or "", []),
            artifact_names=artifact_names,
        )

    profiles = _profiles_by_bid(profile_rows)
    flags = sorted(
        {
            f"{flag.kind} ({flag.artifact_id or 'project'})"
            for flag in quality_flags
            if (flag.severity or "").strip().lower() == "high"
        }
    )
    source = MatrixSource(
        project_id=project_id,
        bids=bids,
        bid_labels=bid_labels,
        legal_names=legal_names,
        requirements=requirements,
        cells=cells,
        pricing_lines=pricing_rows,
        profiles=profiles,
        artifact_names=artifact_names,
        sources_by_bid=sources_by_bid,
        rfp_sources=rfp_sources,
        flags=flags,
    )
    source.summary = deterministic_summary(source)
    return source


def pick_evidence_row(rows: list[Evidence]) -> Evidence:
    """Reviewed rows are pinned: re-extraction must not replace them on read."""
    if not rows:
        raise ValueError("pick_evidence_row requires at least one evidence row")
    reviewed = [row for row in rows if (row.reviewed_by or "").strip()]
    pool = reviewed or rows
    return max(pool, key=lambda row: (row.reviewed_at or "", row.extracted_at or "", row.id))


def render_evidence_cell(
    row: Evidence,
    high_flags: list[QualityFlag] | None = None,
    artifact_names: dict[str, str] | None = None,
) -> RenderedCell:
    """Map a persisted evidence row onto a distinct render state."""
    status = (row.status or "").strip()
    pinned = bool((row.reviewed_by or "").strip())
    warning = _source_quality_warning(high_flags or [])
    citation = _citation_line(row, artifact_names or {})
    names = artifact_names or {}

    if status == "not_stated":
        text = NOT_STATED
    elif status == "not_offered":
        text = NOT_OFFERED
        claim = (row.claim_text or "").strip()
        if claim:
            text = f"{text}\n{STATUS_MARK['not_offered']} {claim}"
    elif status == "extraction_failed":
        text = EXTRACTION_FAILED
    elif status == "unclear":
        body = (row.claim_text or "").strip() or "unclear"
        text = f"{STATUS_MARK['unclear']} {body}"
    elif status in {"met", "partial"}:
        mark = STATUS_MARK.get(status, "")
        body = (row.claim_text or "").strip() or status
        if row.confidence is not None and row.confidence < CONFIDENCE_FLOOR:
            body = f"{UNCERTAIN_PREFIX}{body}"
        text = f"{mark} {body}".strip()
    else:
        text = EXTRACTION_FAILED
        status = "extraction_failed"

    if status not in {"not_stated", "extraction_failed"} and row.page is not None:
        text = f"{text}\n[p.{row.page}]"
    elif citation and status not in {"not_stated", "extraction_failed"}:
        text = f"{text}\n[{citation}]"
    if warning:
        text = f"{text}\n{warning}"
    if pinned:
        text = f"{text}\n{REVIEWED_MARK}"
    return RenderedCell(
        status=status,
        text=text,
        pinned=pinned,
        source_quality_warning=warning,
        citation=citation,
        comment=_cell_comment(row, names, citation, pinned),
        page=row.page,
        artifact_id=row.artifact_id,
    )


def deterministic_summary(source: MatrixSource) -> str:
    counts = Counter(cell.status for cell in source.cells.values())
    parts = [f"{counts[status]} {status}" for status in sorted(counts)]
    tally = "; ".join(parts) if parts else "no evidence cells"
    return (
        f"Matrix from SQL evidence ({len(source.bids)} bids, "
        f"{len(source.requirements)} requirements). {tally}. Humans award."
    )


def insights_from_source(insights: dict[str, Any], source: MatrixSource) -> dict[str, Any]:
    """Replace filename-inferred vendors with the SQL bid list."""
    out = dict(insights)
    vendors = []
    for bid in source.bids:
        files = source.sources_by_bid.get(bid) or []
        vendors.append(
            {
                "name": source.bid_labels.get(bid, bid),
                "bid_id": bid,
                "role": "bidder",
                "artifact_count": len(files),
                "coverage_pct": 0,
                "headline": "; ".join(files) if files else "",
                "evidence": [],
            }
        )
    out["vendors"] = vendors
    decision = dict(out.get("decision") or {})
    decision["summary"] = source.summary
    out["decision"] = decision
    return out


def matrix_from_source(source: MatrixSource, process: str) -> IndirectMatrix | DirectMatrix:
    from ai_brain.core.procurement_ai.process_type import DIRECT_TG

    if process == DIRECT_TG:
        return _direct_from_source(source)
    return _indirect_from_source(source)


def _indirect_from_source(source: MatrixSource) -> IndirectMatrix:
    vendors = []
    lines_by_bid: dict[str, list[PricingLine]] = defaultdict(list)
    for line in source.pricing_lines:
        bid = (line.vendor_id or "").strip()
        if bid:
            lines_by_bid[bid].append(line)
    for bid in source.bids:
        label = source.bid_labels.get(bid, bid)
        legal = source.legal_names.get(bid) or label
        files = "; ".join(source.sources_by_bid.get(bid) or [])
        vendors.append(
            _facts_from_pricing(
                label,
                lines_by_bid.get(bid, []),
                legal_name=legal,
                source_files=files,
                artifact_names=source.artifact_names,
                profile=source.profiles.get(bid) or {},
            )
        )
    requirements: list[RequirementCell] = []
    for req in source.requirements:
        marks: dict[str, str] = {}
        states: dict[str, str] = {}
        citations: dict[str, str] = {}
        comments: dict[str, str] = {}
        pinned: dict[str, bool] = {}
        for bid in source.bids:
            label = source.bid_labels.get(bid, bid)
            cell = source.cells.get((req.id, bid))
            if cell is None:
                marks[label] = f"{STATUS_MARK['not_stated']} {NOT_STATED}"
                states[label] = "not_stated"
                continue
            marks[label] = cell.text
            states[label] = cell.status
            if cell.citation:
                citations[label] = cell.citation
            if cell.comment:
                comments[label] = cell.comment
            if cell.pinned:
                pinned[label] = True
        requirements.append(
            RequirementCell(
                requirement_id=req.id,
                label=req.text,
                category=req.category or "",
                target=req.section or "",
                mandatory=bool(req.mandatory),
                vendor_marks=marks,
                vendor_states=states,
                vendor_citations=citations,
                vendor_comments=comments,
                vendor_pinned=pinned,
            )
        )
    return IndirectMatrix(
        vendors=vendors,
        requirements=requirements,
        method_notes=EVIDENCE_METHOD_NOTES,
        flags=list(source.flags),
        summary=source.summary,
        rfp_sources="; ".join(source.rfp_sources),
        from_evidence=True,
    )


def _direct_from_source(source: MatrixSource) -> DirectMatrix:
    vendors = [
        DirectVendorTerms(
            name=source.bid_labels.get(bid, bid),
            source_files="; ".join(source.sources_by_bid.get(bid) or []),
        )
        for bid in source.bids
    ]
    return DirectMatrix(
        vendors=vendors or [DirectVendorTerms(name="Unnamed vendor")],
        summary=source.summary,
        flags=list(source.flags),
        ranking_notes=[EVIDENCE_METHOD_NOTES],
    )


def _facts_from_pricing(
    name: str,
    lines: list[PricingLine],
    *,
    legal_name: str = "",
    source_files: str = "",
    artifact_names: dict[str, str] | None = None,
    profile: dict[str, Any] | None = None,
):
    vendor = blank_indirect_vendor(name)
    updates: dict[str, Any] = {
        "legal_name": legal_name or name,
        "source_files": source_files,
    }
    profile = dict(profile or {})
    for attr in (
        "legal_name",
        "y1_solution",
        "y1_service",
        "y1_etex_mandays",
        "y1_tco",
        "y2_solution",
        "y2_service",
        "y2_etex_mandays",
        "y2_tco",
        "y3_solution",
        "y3_service",
        "y3_etex_mandays",
        "y3_tco",
        "tco_3_5",
        "indexation",
        "blended_rate",
        "vendor_mandays",
        "etex_mandays",
        "timeline",
        "ecovadis",
        "creditscore",
        "delivery_model",
        "assumptions",
        "legal",
        "obligations",
        "risk_plan",
        "scope_completeness",
        "missing_requirements",
    ):
        value = profile.get(attr)
        if isinstance(value, str) and value.strip() and value.strip().lower() != "missing":
            updates[attr] = value.strip()
    if not lines:
        return vendor.model_copy(update=updates)
    names = artifact_names or {}
    currency = next((line.currency for line in lines if line.currency), "EUR")
    rates = [_as_float(line.rate) for line in lines if line.rate is not None]
    if rates:
        unit = next((line.rate_unit for line in lines if line.rate_unit), "day")
        updates["blended_rate"] = f"{currency} {rates[0]:g}/{unit}"
    qty = sum(_as_float(line.quantity) or 0 for line in lines if line.quantity is not None)
    if qty:
        updates["vendor_mandays"] = f"{qty:g}"
    etex_days = sum(
        _as_float(line.etex_effort_days) or 0
        for line in lines
        if line.etex_effort_days is not None
    )
    if etex_days:
        text = f"{etex_days:g}"
        updates["etex_mandays"] = text
        updates["y1_etex_mandays"] = text
    fp = sum(
        _as_float(line.line_total) or 0
        for line in lines
        if line.offer_type == "fixed_price" and line.line_total is not None
    )
    tm = sum(
        _as_float(line.line_total) or 0
        for line in lines
        if line.offer_type == "time_and_materials" and line.line_total is not None
    )
    if fp:
        updates["y1_solution"] = f"{currency} {fp:g}"
    if tm:
        updates["y1_service"] = f"{currency} {tm:g}"
    total = fp + tm
    if total:
        updates["y1_tco"] = f"{currency} {total:g}"
    discounts = [line.discount_terms for line in lines if line.discount_terms]
    if discounts:
        updates["indexation"] = discounts[0]
    comment = _pricing_comment(lines, names)
    if comment:
        filled = [key for key in ("y1_solution", "y1_service", "y1_tco", "blended_rate") if key in updates]
        updates["cell_comments"] = {key: comment for key in filled} or {
            "y1_service": comment
        }
    return vendor.model_copy(update=updates)


def _profiles_by_bid(rows: list[BidProfileRow]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        bid = (row.vendor_id or "").strip()
        if not bid:
            continue
        try:
            data = json.loads(row.facts_json) if isinstance(row.facts_json, str) else dict(row.facts_json or {})
        except (TypeError, json.JSONDecodeError, ValueError):
            continue
        if isinstance(data, dict):
            out[bid] = data
    return out


def _bid_label(bid: str, vendors: list[Vendor]) -> str:
    exact = [row for row in vendors if row.id == bid]
    if len(exact) == 1:
        return exact[0].name
    suffix = [row for row in vendors if row.id.endswith(f":{bid}")]
    if len(suffix) == 1:
        return suffix[0].name
    return bid


def _legal_name(bid: str, vendors: list[Vendor]) -> str:
    exact = [row for row in vendors if row.id == bid]
    if len(exact) == 1:
        return exact[0].legal_entity or exact[0].name
    suffix = [row for row in vendors if row.id.endswith(f":{bid}")]
    if len(suffix) == 1:
        return suffix[0].legal_entity or suffix[0].name
    return bid


def _sources_from_artifacts(artifacts: list[Artifact]) -> tuple[dict[str, list[str]], list[str]]:
    by_bid: dict[str, list[str]] = defaultdict(list)
    rfp: list[str] = []
    for art in artifacts:
        name = (art.original_name or art.id or "").strip()
        if not name:
            continue
        role = (art.doc_role or "").strip().lower()
        bid = (art.vendor_id or "").strip()
        if role == "rfp" or "rfp" in name.lower():
            rfp.append(name)
            if role == "rfp" or not bid:
                continue
        if bid:
            by_bid[bid].append(name)
    return dict(by_bid), rfp


def _citation_line(row: Evidence, names: dict[str, str]) -> str | None:
    if (row.status or "").strip() in {"not_stated", "extraction_failed"}:
        if not row.artifact_id and row.page is None:
            return None
    parts: list[str] = []
    if row.page is not None:
        parts.append(f"p.{row.page}")
    name = names.get(row.artifact_id or "") or ""
    if name:
        parts.append(name)
    elif row.artifact_id:
        parts.append(row.artifact_id)
    return " · ".join(parts) if parts else None


def _cell_comment(
    row: Evidence,
    names: dict[str, str],
    citation: str | None,
    pinned: bool,
) -> str | None:
    lines: list[str] = []
    if citation:
        lines.append(citation)
    if row.artifact_id:
        lines.append(f"artifact_id: {row.artifact_id}")
    if row.chunk_id:
        lines.append(f"chunk_id: {row.chunk_id}")
    if row.confidence is not None:
        lines.append(f"confidence: {row.confidence:g}")
    if pinned and row.reviewed_by:
        lines.append(f"reviewed_by: {row.reviewed_by}")
    if (row.claim_text or "").strip() and (row.status or "") not in {"not_stated"}:
        claim = (row.claim_text or "").strip()
        if len(claim) > 280:
            claim = claim[:277] + "..."
        lines.append(claim)
    return "\n".join(lines) if lines else None


def _pricing_comment(lines: list[PricingLine], names: dict[str, str]) -> str | None:
    notes: list[str] = []
    for line in lines:
        offer = (line.offer_type or "").replace("_", " ")
        if offer:
            notes.append(offer)
        if line.discount_terms:
            notes.append(str(line.discount_terms).strip())
        cite: list[str] = []
        if line.page is not None:
            cite.append(f"p.{line.page}")
        if line.artifact_id:
            cite.append(names.get(line.artifact_id, line.artifact_id))
        if cite:
            notes.append(" · ".join(cite))
    unique: list[str] = []
    seen: set[str] = set()
    for note in notes:
        if note and note not in seen:
            unique.append(note)
            seen.add(note)
    return "\n".join(unique) if unique else None


def _high_severity_by_artifact(flags: list[QualityFlag]) -> dict[str, list[QualityFlag]]:
    grouped: dict[str, list[QualityFlag]] = defaultdict(list)
    for flag in flags:
        if (flag.severity or "").strip().lower() != "high":
            continue
        artifact_id = (flag.artifact_id or "").strip()
        if artifact_id:
            grouped[artifact_id].append(flag)
    return grouped


def _source_quality_warning(flags: list[QualityFlag]) -> str | None:
    if not flags:
        return None
    kinds = ", ".join(sorted({flag.kind for flag in flags if flag.kind}))
    if not kinds:
        return None
    return f"{SOURCE_QUALITY_PREFIX} {kinds}"


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
