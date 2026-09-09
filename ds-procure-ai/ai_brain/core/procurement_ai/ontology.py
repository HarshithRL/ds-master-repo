"""Procurement ontology contract. Writers and extractors share this shape.

No commercial number is invented here. Missing evidence stays null or "?".
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

ONTOLOGY_VERSION = "1.0.0"
PROCESS_TYPES = ("direct_tg", "indirect_it_software", "indirect_it_services")

Status = Literal["\u2713", "~", "\u2717", "?", "\u2014"]
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
    vendor_id: str
    vendor_legal_name: str
    requirement_id: str
    value_text: str = ""
    numeric_value: float | None = None
    unit: str | None = None
    status: Status = "?"
    locator: str
    quote: str
    confidence: float = Field(default=0.0, ge=0, le=1)
    chunk_id: str | None = None


class TCOLine(BaseModel):
    vendor_id: str
    year: int
    line_type: LineType
    amount_eur: float | None = None
    mandays: float | None = None
    rate_eur_per_day: float | None = 800.0
    derived: bool = False
    note: str | None = None
    locator: str


class VendorProfile(BaseModel):
    vendor_id: str
    legal_name: str
    blended_rate: str | None = None
    vendor_mandays: str | None = None
    etex_mandays: str | None = None
    timeline: str | None = None
    ecovadis: str | None = None
    creditsafe: str | None = None
    delivery_model: str | None = None
    assumptions: str | None = None
    legal_terms: str | None = None
    etex_obligations: str | None = None
    risk_plan: str | None = None
    scope_completeness: str | None = None
    missing_requirements: str | None = None
    locators: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def ecovadis_is_not_creditsafe(self) -> "VendorProfile":
        eco = (self.ecovadis or "").strip()
        credit = (self.creditsafe or "").strip()
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
    weights_locked: bool = False
    scorecard_owner: str = "Etex evaluation team"

    @model_validator(mode="after")
    def fail_closed(self) -> "ComparisonMatrix":
        if self.process_type not in PROCESS_TYPES:
            raise ValueError("unknown process_type")
        ids = [row.id for row in self.requirements]
        if len(ids) != len(set(ids)):
            raise ValueError("requirement ids must be unique")
        return self
