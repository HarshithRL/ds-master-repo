"""Procurement ontology contract. Writers and extractors share this shape.

No commercial number is invented here. Missing evidence stays null or "?".
BAFO cells are rich strings (SWIFT baseline): cited narrative, never coerced floats.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

ONTOLOGY_VERSION = "1.0.0"
PROCESS_TYPES = ("direct_tg", "indirect_it_software", "indirect_it_services")
SWIFT_OVERLAY_LABELS = (
    "Two BIC codes in scope",
    "CSCF 2026, Architecture A4 confirmed",
    "Maximise reliance on service bureaus (FIDES/BME)",
)

Status = Literal["\u2713", "~", "\u2717", "?", "\u2014"]
OfferingState = Literal[
    "met",
    "partial",
    "not_offered",
    "not_stated",
    "unclear",
    "extraction_failed",
]
EVIDENCED_MARKS = frozenset({"\u2713", "~", "\u2717"})
Category = Literal[
    "scope",
    "timeline",
    "commercial",
    "legal",
    "deliverable",
    "commercial_tco",
    "risk",
]
ProcessType = Literal["direct_tg", "indirect_it_software", "indirect_it_services"]
LineType = Literal[
    "solution_recurring",
    "service_one_off",
    "etex_mandays",
    "total_year",
    "total_horizon",
]


class Requirement(BaseModel):
    id: str
    text: str
    category: Category
    target: str | None = None
    mandatory: bool = True
    weight: float | None = None


class VendorOffering(BaseModel):
    """One requirement × bid cell. value_text is the SWIFT-rich mark (e.g. '✓ 21 mandatory/BIC')."""

    vendor_id: str
    vendor_legal_name: str
    requirement_id: str
    value_text: str = ""
    numeric_value: float | None = None
    unit: str | None = None
    status: Status = "?"
    state: OfferingState | None = None
    locator: str = ""
    quote: str = ""
    confidence: float = Field(default=0.0, ge=0, le=1)
    chunk_id: str | None = None

    @model_validator(mode="after")
    def citation_or_abstain(self) -> "VendorOffering":
        mark = (self.status or "?").strip()
        if mark not in EVIDENCED_MARKS:
            return self
        if not (self.quote or "").strip():
            raise ValueError("evidenced offering requires quote")
        if not (self.locator or "").strip() and not (self.chunk_id or "").strip():
            raise ValueError("evidenced offering requires locator or chunk_id")
        return self


class TCOLine(BaseModel):
    vendor_id: str
    year: int
    line_type: LineType
    amount_eur: float | None = None
    mandays: float | None = None
    rate_eur_per_day: float | None = 800.0
    derived: bool = False
    note: str | None = None
    locator: str = ""


class VendorProfile(BaseModel):
    """BAFO column. Money/manday fields are narrative strings (ranges allowed). Omit if not stated."""

    vendor_id: str
    legal_name: str
    y1_solution: str | None = None
    y1_service: str | None = None
    y1_etex_mandays: str | None = None
    y1_tco: str | None = None
    y2_solution: str | None = None
    y2_service: str | None = None
    y2_etex_mandays: str | None = None
    y2_tco: str | None = None
    y3_solution: str | None = None
    y3_service: str | None = None
    y3_etex_mandays: str | None = None
    y3_tco: str | None = None
    tco_3_5: str | None = None
    indexation: str | None = None
    blended_rate: str | None = None
    vendor_mandays: str | None = None
    etex_mandays: str | None = None
    timeline: str | None = None
    renewal_type: str | None = None
    ecovadis: str | None = None
    creditsafe: str | None = None
    creditscore: str | None = None
    architecture: str | None = None
    security: str | None = None
    supply_location: str | None = None
    delivery_model: str | None = None
    assumptions: str | None = None
    legal_terms: str | None = None
    etex_obligations: str | None = None
    risk_plan: str | None = None
    ref_names: str | None = None
    ref_feedback: str | None = None
    scope_completeness: str | None = None
    missing_requirements: str | None = None
    source_files: str | None = None
    locators: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def ecovadis_is_not_creditsafe(self) -> "VendorProfile":
        eco = (self.ecovadis or "").strip()
        credit = (self.creditsafe or self.creditscore or "").strip()
        if eco and credit and eco == credit:
            raise ValueError("EcoVadis and CreditSafe must stay separate fields")
        return self


class KeyFlag(BaseModel):
    severity: Literal["high", "medium", "low"]
    text: str
    vendors: list[str]
    locator: str | None = None


class SourceNote(BaseModel):
    vendor_id: str
    files: list[str] = Field(default_factory=list)
    method_note: str | None = None


class ComparisonMatrix(BaseModel):
    process_type: ProcessType
    ontology_version: str
    currency: str = "EUR"
    internal_day_rate: float = 800.0
    requirements: list[Requirement]
    vendors: list[VendorProfile]
    offerings: list[VendorOffering] = Field(default_factory=list)
    tco: list[TCOLine] = Field(default_factory=list)
    key_flags: list[KeyFlag] = Field(default_factory=list)
    sources: list[SourceNote] = Field(default_factory=list)
    bafo_rows: list[str] = Field(default_factory=list)
    method_notes: str = ""
    rfp_sources: str = ""
    summary: str = ""
    weights_locked: bool = False
    scorecard_owner: str = "Etex evaluation team"

    @model_validator(mode="after")
    def fail_closed(self) -> "ComparisonMatrix":
        if self.process_type not in PROCESS_TYPES:
            raise ValueError("unknown process_type")
        ids = [row.id for row in self.requirements]
        if len(ids) != len(set(ids)):
            raise ValueError("requirement ids must be unique")
        if self.process_type == "direct_tg":
            labels = {row.text.strip() for row in self.requirements}
            overlap = labels.intersection(SWIFT_OVERLAY_LABELS)
            if overlap:
                raise ValueError("Direct TG must not use the SWIFT CSP requirement overlay")
        return self
