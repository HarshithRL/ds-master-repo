"""Map ComparisonMatrix ontology → IndirectMatrix / DirectMatrix. No LLM."""

from __future__ import annotations

from typing import Any

from ai_brain.core.procurement_ai.comparison_template import FIELD_TO_ATTR, SCORECARD
from ai_brain.core.procurement_ai.ontology import ComparisonMatrix, VendorOffering, VendorProfile
from ai_brain.core.procurement_ai.packs.matrix_layout import (
    MISSING,
    NOT_STATED,
    STATUS_MARK,
    SWIFT_REQUIREMENTS,
)
from ai_brain.core.procurement_ai.packs.matrix_schema import (
    DirectMatrix,
    DirectVendorTerms,
    IndirectMatrix,
    IndirectVendorFacts,
    RequirementCell,
    blank_indirect_vendor,
)
from ai_brain.core.procurement_ai.process_type import DIRECT_TG, IT_SERVICES

_MARK_TO_STATE = {
    "\u2713": "met",
    "~": "partial",
    "\u2717": "not_offered",
    "?": "not_stated",
    "\u2014": "not_stated",
}


def matrix_is_rich(matrix: ComparisonMatrix | None) -> bool:
    if matrix is None:
        return False
    if matrix.offerings:
        return True
    for vendor in matrix.vendors:
        if (vendor.legal_name or "").strip() and vendor.vendor_id:
            for attr in ("y1_service", "y1_tco", "y1_solution", "blended_rate", "timeline"):
                value = getattr(vendor, attr, None)
                if isinstance(value, str) and value.strip():
                    return True
    return False


def indirect_from_ontology(
    matrix: ComparisonMatrix,
    insights: dict[str, Any] | None = None,
) -> IndirectMatrix:
    del insights
    vendors = [_vendor_facts(row) for row in matrix.vendors]
    offerings_by_req: dict[str, list[VendorOffering]] = {}
    for item in matrix.offerings:
        offerings_by_req.setdefault(item.requirement_id, []).append(item)
    requirements: list[RequirementCell] = []
    spine = list(matrix.requirements)
    if matrix.process_type == IT_SERVICES and not spine:
        from ai_brain.core.procurement_ai.ontology import Requirement

        spine = [
            Requirement(id=rid, text=label, category=category, target=target)  # type: ignore[arg-type]
            for rid, label, category, target in SWIFT_REQUIREMENTS
        ]
    for req in spine:
        marks: dict[str, str] = {}
        states: dict[str, str] = {}
        citations: dict[str, str] = {}
        comments: dict[str, str] = {}
        for offering in offerings_by_req.get(req.id, []):
            label = _vendor_label(matrix, offering)
            marks[label] = offering.value_text or _mark_fallback(offering)
            states[label] = offering.state or _MARK_TO_STATE.get(offering.status, "not_stated")
            if offering.locator:
                citations[label] = offering.locator
            comment_parts = [part for part in (offering.locator, offering.quote) if part]
            if comment_parts:
                comments[label] = "\n".join(comment_parts)
        requirements.append(
            RequirementCell(
                requirement_id=req.id,
                label=req.text,
                category=req.category or "",
                target=req.target or "",
                mandatory=bool(req.mandatory),
                vendor_marks=marks,
                vendor_states=states,
                vendor_citations=citations,
                vendor_comments=comments,
            )
        )
    method = (matrix.method_notes or "").strip()
    if not method:
        notes = [src.method_note for src in matrix.sources if src.method_note]
        method = " ".join(str(n) for n in notes)
    flags = [f"{flag.severity}: {flag.text}" for flag in matrix.key_flags]
    rfp = matrix.rfp_sources or ""
    if not rfp:
        rfp_src = next((src for src in matrix.sources if src.vendor_id == "rfp"), None)
        if rfp_src:
            rfp = "; ".join(rfp_src.files)
    return IndirectMatrix(
        vendors=vendors or [blank_indirect_vendor("Vendor 1")],
        requirements=requirements,
        method_notes=method,
        flags=flags,
        summary=matrix.summary,
        rfp_sources=rfp,
        from_evidence=matrix_is_rich(matrix),
    )


def direct_from_ontology(
    matrix: ComparisonMatrix,
    insights: dict[str, Any] | None = None,
) -> DirectMatrix:
    del insights
    vendors = [
        DirectVendorTerms(
            name=row.legal_name or row.vendor_id,
            source_files=row.source_files or "",
            lead_time=row.timeline or MISSING,
            note=row.assumptions or "",
        )
        for row in matrix.vendors
    ]
    return DirectMatrix(
        vendors=vendors or [DirectVendorTerms(name="Unnamed vendor")],
        summary=matrix.summary,
        flags=[f"{flag.severity}: {flag.text}" for flag in matrix.key_flags],
        ranking_notes=[matrix.method_notes] if matrix.method_notes else [],
    )


def _vendor_facts(row: VendorProfile) -> IndirectVendorFacts:
    vendor = blank_indirect_vendor(row.legal_name or row.vendor_id)
    updates: dict[str, Any] = {
        "legal_name": row.legal_name or row.vendor_id,
        "source_files": row.source_files or "",
        "score_card": SCORECARD,
    }
    credit = (row.creditscore or row.creditsafe or "").strip()
    for attr in FIELD_TO_ATTR.values():
        if attr in {"score_card", "creditscore"}:
            continue
        source_attr = "legal_terms" if attr == "legal" else "etex_obligations" if attr == "obligations" else attr
        value = getattr(row, source_attr, None)
        if isinstance(value, str) and value.strip():
            updates[attr] = value.strip()
    if credit:
        updates["creditscore"] = credit
    comments = {key: locator for key, locator in (row.locators or {}).items() if locator}
    if comments:
        updates["cell_comments"] = comments
    return vendor.model_copy(update=updates)


def _vendor_label(matrix: ComparisonMatrix, offering: VendorOffering) -> str:
    if (offering.vendor_legal_name or "").strip():
        return offering.vendor_legal_name.strip()
    for row in matrix.vendors:
        if row.vendor_id == offering.vendor_id:
            return row.legal_name or row.vendor_id
    return offering.vendor_id


def _mark_fallback(offering: VendorOffering) -> str:
    state = offering.state or _MARK_TO_STATE.get(offering.status, "not_stated")
    mark = STATUS_MARK.get(state, offering.status)
    if state == "not_stated":
        return f"{mark} {NOT_STATED}"
    return f"{mark} {offering.status}".strip()
