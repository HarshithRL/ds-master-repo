"""Map project fields onto the three Etex process types. Never mix Direct and IT."""

from __future__ import annotations

from typing import Any

DIRECT_TG = "direct_tg"
IT_SOFTWARE = "indirect_it_software"
IT_SERVICES = "indirect_it_services"

_SOFTWARE_HINTS = (
    "software",
    "saas",
    "tms",
    "esg",
    "csrd",
    "licence",
    "license",
    "platform",
    "tagetik",
    "sphera",
    "kyriba",
)
_SERVICES_HINTS = (
    "service",
    "cscf",
    "swift",
    "csp",
    "audit",
    "advisory",
    "days",
    "manday",
)


def classify_process_type(
    *,
    business_process: str | None = None,
    category: str | None = None,
    name: str | None = None,
    description: str | None = None,
) -> str:
    blob = " ".join(
        part.lower()
        for part in (business_process, category, name, description)
        if part
    )
    process = (business_process or "").strip().lower()
    if process.startswith("direct") or "direct tg" in blob:
        return DIRECT_TG
    if any(hint in blob for hint in _SOFTWARE_HINTS) and not any(
        hint in blob for hint in ("swift", "cscf")
    ):
        return IT_SOFTWARE
    if process.startswith("indirect") or any(hint in blob for hint in _SERVICES_HINTS):
        return IT_SERVICES
    if process.startswith("indirect"):
        return IT_SOFTWARE
    return ""


def owner_label(process_type: str) -> str:
    if process_type == DIRECT_TG:
        return "Etex Luxembourg SA/NV"
    if process_type in {IT_SOFTWARE, IT_SERVICES}:
        return "Etex Services NV"
    return ""


def process_chip(process_type: str) -> str:
    return {
        DIRECT_TG: "Direct TG",
        IT_SOFTWARE: "IT software",
        IT_SERVICES: "IT services",
    }.get(process_type, "Unset")


def checklist_for(process_type: str) -> list[dict[str, Any]]:
    if process_type == DIRECT_TG:
        return [
            {"checklist_key": "nda", "label": "NDA", "severity": "blocking"},
            {"checklist_key": "requirements", "label": "Requirements checklist", "severity": "blocking"},
            {"checklist_key": "pricing_pq", "label": "Pricing P×Q", "severity": "blocking"},
            {"checklist_key": "technical", "label": "Technical assessment", "severity": "blocking"},
            {"checklist_key": "safety", "label": "Safety assessment", "severity": "blocking"},
        ]
    if process_type == IT_SOFTWARE:
        return [
            {"checklist_key": "nda", "label": "NDA", "severity": "blocking"},
            {"checklist_key": "dpa", "label": "GDPR Part B / DPA", "severity": "blocking"},
            {"checklist_key": "architecture", "label": "Architecture pack", "severity": "blocking"},
            {"checklist_key": "evsat", "label": "EVSAT", "severity": "blocking"},
            {"checklist_key": "pricing_tco", "label": "Licence + implementation TCO", "severity": "blocking"},
        ]
    return [
        {"checklist_key": "nda", "label": "NDA", "severity": "blocking"},
        {"checklist_key": "dpa", "label": "GDPR Part B / DPA", "severity": "optional"},
        {"checklist_key": "proposal", "label": "Vendor proposal", "severity": "blocking"},
        {"checklist_key": "pricing_days", "label": "Professional-services days / rate", "severity": "blocking"},
        {"checklist_key": "references", "label": "References", "severity": "optional"},
    ]
