"""Load a frozen ComparisonMatrix catalog. Does not write the database.

Each process_type has its own richness catalog. SWIFT CSP BAFO is only the
Indirect IT services example. Requirements in a live project come from the RFP.
Do not mix Direct TG and Indirect IT on one matrix.
"""

from __future__ import annotations

import json
from pathlib import Path

from ai_brain.core.procurement_ai.ontology import PROCESS_TYPES, ComparisonMatrix

_FIXTURES = Path(__file__).resolve().parent / "fixtures"

CATALOG_FILES = {
    "direct_tg": _FIXTURES / "direct_tg.json",
    "indirect_it_software": _FIXTURES / "indirect_it_software.json",
    "indirect_it_services": _FIXTURES / "swift_csp_bafo.json",
}

SWIFT_CSP_BAFO = CATALOG_FILES["indirect_it_services"]


def load_matrix(path: Path) -> ComparisonMatrix:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return ComparisonMatrix.model_validate(payload)


def load_catalog(process_type: str) -> ComparisonMatrix:
    key = (process_type or "").strip()
    if key not in PROCESS_TYPES:
        raise ValueError(f"unknown process_type: {key}")
    matrix = load_matrix(CATALOG_FILES[key])
    if matrix.process_type != key:
        raise ValueError("catalog process_type does not match the requested type")
    return matrix


def load_swift_csp_bafo() -> ComparisonMatrix:
    return load_catalog("indirect_it_services")
