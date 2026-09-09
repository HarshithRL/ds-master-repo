"""Structured comparison payloads. LLM fills these; Excel writers never invent."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ai_brain.core.procurement_ai.packs.matrix_layout import MISSING, SCORED


class IndirectVendorFacts(BaseModel):
    """Defaults omitted on quote fields so the LLM must emit them (missing if unknown)."""

    name: str
    legal_name: str = ""
    y1_solution: str
    y1_service: str
    y1_etex_mandays: str
    y1_tco: str
    y2_solution: str
    y2_service: str
    y2_etex_mandays: str
    y2_tco: str
    y3_solution: str
    y3_service: str
    y3_etex_mandays: str
    y3_tco: str
    tco_3_5: str
    score_card: str = SCORED
    indexation: str
    blended_rate: str
    vendor_mandays: str
    etex_mandays: str
    timeline: str
    ecovadis: str
    creditscore: str
    architecture: str = SCORED
    security: str = SCORED
    delivery_model: str
    assumptions: str
    legal: str
    obligations: str
    risk_plan: str
    scope_completeness: str
    missing_requirements: str
    source_files: str = ""
    requirement_marks: dict[str, str] = Field(default_factory=dict)
    cell_comments: dict[str, str] = Field(default_factory=dict)


def blank_indirect_vendor(name: str) -> IndirectVendorFacts:
    from ai_brain.core.procurement_ai.packs.matrix_layout import BAFO_ATTRS, MISSING

    fields = {attr: MISSING for attr in BAFO_ATTRS if attr}
    return IndirectVendorFacts(name=name, **fields)


class RequirementCell(BaseModel):
    requirement_id: str
    label: str = ""
    category: str = ""
    target: str = ""
    mandatory: bool = False
    vendor_marks: dict[str, str] = Field(default_factory=dict)
    vendor_states: dict[str, str] = Field(default_factory=dict)
    vendor_citations: dict[str, str] = Field(default_factory=dict)
    vendor_comments: dict[str, str] = Field(default_factory=dict)
    vendor_pinned: dict[str, bool] = Field(default_factory=dict)


class IndirectMatrix(BaseModel):
    """Layout of SWIFT CSP Vendor Comparison.xlsx."""

    vendors: list[IndirectVendorFacts] = Field(default_factory=list)
    requirements: list[RequirementCell] = Field(default_factory=list)
    method_notes: str = ""
    flags: list[str] = Field(default_factory=list)
    summary: str = ""
    rfp_sources: str = ""
    from_evidence: bool = False


class DirectLine(BaseModel):
    sku: str = ""
    description: str = ""
    qty_2023: str = MISSING
    qty_2024: str = MISSING
    qty_2025: str = MISSING
    unit_prices: dict[str, str] = Field(default_factory=dict)


class DirectVendorTerms(BaseModel):
    name: str
    agreement: str = MISSING
    incoterm: str = MISSING
    lead_time: str = MISSING
    payment_terms: str = MISSING
    rebate: str = MISSING
    samples: str = MISSING
    qualified: str = MISSING
    rfi_offer: str = MISSING
    rfp_offer: str = MISSING
    note: str = ""
    follow_up: str = MISSING
    source_files: str = ""


class DirectMatrix(BaseModel):
    """Layout of France overview P×Q / ranking / samples / terms."""

    vendors: list[DirectVendorTerms] = Field(default_factory=list)
    basket_lines: list[DirectLine] = Field(default_factory=list)
    ranking_notes: list[str] = Field(default_factory=list)
    summary: str = ""
    flags: list[str] = Field(default_factory=list)
