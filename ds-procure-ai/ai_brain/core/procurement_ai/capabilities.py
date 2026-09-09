"""Procura capability names. Flags stay for back-compat; new work routes by capability."""

from __future__ import annotations

from typing import Any

QA = "qa"
INGEST = "ingest"
KB_BUILD = "kb_build"
COMPARE_XLSX = "compare_xlsx"
STEERCO_PPT = "steerco_ppt"

PACK_CAPABILITIES = frozenset({COMPARE_XLSX, STEERCO_PPT, KB_BUILD})
KNOWN = frozenset({QA, INGEST, KB_BUILD, COMPARE_XLSX, STEERCO_PPT})


def normalize_capability(raw: object) -> str:
    value = str(raw or "").strip().lower()
    aliases = {
        "compare": COMPARE_XLSX,
        "xlsx": COMPARE_XLSX,
        "matrix": COMPARE_XLSX,
        "vendor_comparison": COMPARE_XLSX,
        "ppt": STEERCO_PPT,
        "steerco": STEERCO_PPT,
        "chat": QA,
        "main": QA,
    }
    value = aliases.get(value, value)
    return value if value in KNOWN else ""


def capability_from_state(state: dict[str, Any]) -> str:
    procurement = state.get("procurement") if isinstance(state.get("procurement"), dict) else {}
    return normalize_capability(
        state.get("capability") or procurement.get("capability")
    )


def project_id_from_state(state: dict[str, Any]) -> str:
    procurement = state.get("procurement") if isinstance(state.get("procurement"), dict) else {}
    return str(state.get("project_id") or procurement.get("project_id") or "").strip()


def capability_from_request(text: str) -> str:
    """Route only explicit pack asks. A normal question stays on file-search chat."""
    lowered = " ".join((text or "").lower().split())
    compare_phrases = (
        "create comparison",
        "comparison matrix",
        "comparison workbook",
        "bafo comparison",
        "build comparison",
        "build the matrix",
        "vendor comparison matrix",
    )
    if any(phrase in lowered for phrase in compare_phrases):
        return COMPARE_XLSX
    steerco_phrases = (
        "build steerco",
        "steerco deck",
        "steerco ppt",
        "steering committee",
    )
    if any(phrase in lowered for phrase in steerco_phrases):
        return STEERCO_PPT
    return ""
