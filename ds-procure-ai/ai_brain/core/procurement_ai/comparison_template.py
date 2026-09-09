"""Shared Final BAFO Comparison rows. One template, N/A when a row does not apply."""

from __future__ import annotations

from typing import Any

from ai_brain.core.procurement_ai.process_type import DIRECT_TG, IT_SERVICES, IT_SOFTWARE

ALL = (DIRECT_TG, IT_SOFTWARE, IT_SERVICES)
INDIRECT = (IT_SOFTWARE, IT_SERVICES)
SOFTWARE_OR_DIRECT = (DIRECT_TG, IT_SOFTWARE)
DIRECT = (DIRECT_TG,)

NA = "N/A"
MISSING = "?"
SCORECARD = "To be scored by Etex evaluation team"

# field_id is the named Excel field. applies_to is the process types that may hold a value.
TEMPLATE_ROWS: tuple[dict[str, Any], ...] = (
    {"field_id": "y1_solution_cost", "label": "Solution costs (Software, Materials)", "cadence": "Recurring", "year": 1, "kind": "money", "applies_to": SOFTWARE_OR_DIRECT},
    {"field_id": "y1_service_cost", "label": "Service/Implementation Costs", "cadence": "One off", "kind": "money", "applies_to": INDIRECT},
    {"field_id": "y1_etex_mandays", "label": "Etex Mandays ( standard rate 800 EUR/day)", "cadence": "One off / Recurring", "kind": "mandays", "applies_to": INDIRECT},
    {"field_id": "tco_year_1", "label": "Total TCO year 1", "cadence": "", "kind": "total", "components": ("y1_solution_cost", "y1_service_cost", "y1_etex_mandays"), "applies_to": ALL},
    {"field_id": "y2_solution_cost", "label": "Solution costs (Software, Materials)", "cadence": "Recurring", "year": 2, "kind": "money", "applies_to": SOFTWARE_OR_DIRECT},
    {"field_id": "y2_service_cost", "label": "Service/Implementation Costs (if applicable)", "cadence": "One off", "kind": "money", "applies_to": INDIRECT},
    {"field_id": "y2_etex_mandays", "label": "Etex Mandays (Standard rate) 800 EUR/day) (if applicable)", "cadence": "One off / Recurring", "kind": "mandays", "applies_to": INDIRECT},
    {"field_id": "tco_year_2", "label": "Total TCO year 2", "cadence": "", "kind": "total", "components": ("y2_solution_cost", "y2_service_cost", "y2_etex_mandays"), "applies_to": ALL},
    {"field_id": "y3_solution_cost", "label": "Solution costs (Software, Materials)", "cadence": "Recurring", "year": 3, "kind": "money", "applies_to": SOFTWARE_OR_DIRECT},
    {"field_id": "y3_service_cost", "label": "Service/Implementation Costs (if applicable)", "cadence": "One off", "kind": "money", "applies_to": INDIRECT},
    {"field_id": "y3_etex_mandays", "label": "Etex Mandays (Standard rate) 800 EUR/day) (if applicable)", "cadence": "One off / Recurring", "kind": "mandays", "applies_to": INDIRECT},
    {"field_id": "tco_year_3", "label": "Total TCO year 3", "cadence": "", "kind": "total", "components": ("y3_solution_cost", "y3_service_cost", "y3_etex_mandays"), "applies_to": ALL},
    {"field_id": "tco_3_5_yrs", "label": "Total TCO (3/5 yrs)", "cadence": "", "kind": "total", "components": ("tco_year_1", "tco_year_2", "tco_year_3"), "applies_to": ALL},
    {"field_id": "scorecard", "label": "Score Card score", "cadence": "", "kind": "scorecard", "applies_to": ALL},
    {"field_id": "indexation", "label": "Indexation: (applies only to recurring components unless explicitly stated otherwise)", "cadence": "", "kind": "text", "applies_to": INDIRECT},
    {"field_id": "blended_rate", "label": "Indicative Blended rate", "cadence": "", "kind": "money", "applies_to": INDIRECT},
    {"field_id": "vendor_mandays", "label": "Vendor Mandays (implementation effort)", "cadence": "", "kind": "mandays", "applies_to": INDIRECT},
    {"field_id": "etex_effort", "label": "Etex Mandays (Internal business / IT effort)", "cadence": "", "kind": "mandays", "applies_to": INDIRECT},
    {"field_id": "timeline", "label": "Planning and timeline (weeks) / Delivery time", "cadence": "", "kind": "text", "applies_to": ALL},
    {"field_id": "renewal_type", "label": "Renewal type", "cadence": "", "kind": "text", "applies_to": INDIRECT},
    {"field_id": "ecovadis", "label": "EcoVadis", "cadence": "", "kind": "text", "applies_to": ALL},
    {"field_id": "creditscore", "label": "CreditScore", "cadence": "", "kind": "text", "applies_to": ALL},
    {"field_id": "architecture", "label": "Architecture Assessment", "cadence": "", "kind": "text", "applies_to": INDIRECT},
    {"field_id": "security", "label": "Security Assessment", "cadence": "", "kind": "text", "applies_to": INDIRECT},
    {"field_id": "supply_location", "label": "Supply type location", "cadence": "", "kind": "text", "applies_to": DIRECT},
    {"field_id": "delivery_model", "label": "Delivery Model", "cadence": "", "kind": "text", "applies_to": ALL},
    {"field_id": "assumptions", "label": "Assumptions", "cadence": "", "kind": "text", "applies_to": ALL},
    {"field_id": "legal", "label": "Legal terms & compliance", "cadence": "", "kind": "text", "applies_to": ALL},
    {"field_id": "etex_obligations", "label": "Obligations for Etex (excluding Etex Mandays, already captured above)", "cadence": "", "kind": "text", "applies_to": ALL},
    {"field_id": "risk_plan", "label": "Risk plan", "cadence": "", "kind": "text", "applies_to": ALL},
    {"field_id": "ref_names", "label": "Reference: Customer Names", "cadence": "", "kind": "text", "applies_to": ALL},
    {"field_id": "ref_feedback", "label": "Reference: Customer Feedback", "cadence": "", "kind": "text", "applies_to": ALL},
    {"field_id": "scope_completeness", "label": "Scope completeness against requirements", "cadence": "", "kind": "text", "applies_to": ALL},
    {"field_id": "missing_requirements", "label": "Missing requirement list", "cadence": "", "kind": "text", "applies_to": ALL},
)


def row_applies(row: dict[str, Any], process_type: str) -> bool:
    allowed = row.get("applies_to") or ALL
    return bool(process_type) and process_type in allowed
