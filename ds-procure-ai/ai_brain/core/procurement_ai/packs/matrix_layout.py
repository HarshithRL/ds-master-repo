"""Sheet layouts copied from the Etex SWIFT and France comparison workbooks."""

from __future__ import annotations

# Final BAFO Comparison — exact labels from SWIFT CSP Vendor Comparison.xlsx
BAFO_ROWS: tuple[tuple[str, str], ...] = (
    ("Solution costs (Software, Materials)", "Recurring"),
    ("Service/Implementation Costs", "One off"),
    ("Etex Mandays ( standard rate 800 EUR/day)", "One off /\nRecurring"),
    ("Total TCO year 1", ""),
    ("Solution costs (Software, Materials)", "Recurring"),
    ("Service/Implementation Costs (if applicable)", "One off"),
    ("Etex Mandays (Standard rate) 800 EUR/day) (if applicable)", "One off /\nRecurring"),
    ("Total TCO year 2", ""),
    ("Solution costs (Software, Materials)", "Recurring"),
    ("Service/Implementation Costs (if applicable)", "One off"),
    ("Etex Mandays (Standard rate) 800 EUR/day) (if applicable)", "One off /\nRecurring"),
    ("Total TCO year 3", ""),
    ("Total TCO (3/5 yrs)", ""),
    ("", ""),
    ("Score Card score", ""),
    (
        "Indexation: (applies only to recurring components unless explicitly stated otherwise)",
        "",
    ),
    ("Indicative Blended rate", ""),
    ("Vendor Mandays (implementation effort)", ""),
    ("Etex Mandays (Internal business / IT effort)", ""),
    ("Planning and timeline (weeks) / Delivery time", ""),
    ("EcoVadis", ""),
    ("CreditScore", ""),
    ("Architecture Assessment", ""),
    ("Security Assessment", ""),
    ("Delivery Model", ""),
    ("Assumptions", ""),
    ("Legal terms & compliance", ""),
    ("Obligations for Etex", ""),
    ("Risk plan", ""),
    ("Scope completeness against requirements", ""),
    ("Missing requirement list", ""),
)

BAFO_ATTRS: tuple[str | None, ...] = (
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
    None,
    "score_card",
    "indexation",
    "blended_rate",
    "vendor_mandays",
    "etex_mandays",
    "timeline",
    "ecovadis",
    "creditscore",
    "architecture",
    "security",
    "delivery_model",
    "assumptions",
    "legal",
    "obligations",
    "risk_plan",
    "scope_completeness",
    "missing_requirements",
)

SCORED_BY_ETEX = frozenset(
    {
        "Score Card score",
        "Architecture Assessment",
        "Security Assessment",
        "Reference: Customer Feedback",
    }
)

# Procurement Requirements — R01–R40 from SWIFT CSP Vendor Comparison.xlsx
SWIFT_REQUIREMENTS: tuple[tuple[str, str, str, str], ...] = (
    ("R01", "Two BIC codes in scope", "scope", "ETEXBEBB (BE) + URSNESMMXXX (ES)"),
    ("R02", "Separate IT environments assessed", "scope", "Both environments covered"),
    ("R03", "CSCF 2026, Architecture A4 confirmed", "scope", "Supplier confirms mandatory control list"),
    ("R04", "Independent assessment + attestation support", "scope", "Support SWIFT attestation"),
    ("R05", "Maximise reliance on service bureaus (FIDES/BME)", "scope", "Reduce duplicate testing"),
    ("R06", "ETEXBEBB architecture understood", "scope", "Serrala/SFTP - FIDES flow"),
    ("R07", "Swift.com portal exclusion respected", "scope", "No payment creation via portal"),
    ("R08", "TMS replacement (FIS Integrity) accounted for", "scope", "2026 migration in planning"),
    ("R09", "URSNESMMXXX architecture understood", "scope", "SAP RISE - BME flow"),
    ("R10", "Q&A via template by 16/02/2026", "timeline", "A03 template used"),
    ("R11", "RFP response by 13/03/2026", "timeline", "Word/Excel/PowerPoint, electronic"),
    ("R12", "Shortlist & presentation 25/03 - 06/04", "timeline", "Etex process step"),
    ("R13", "BAFO 10/04, award 17/04", "timeline", "Etex process step"),
    ("R14", "Project start Aug/Sep 2026", "timeline", "Fieldwork Aug-Sep"),
    ("R15", "Initial reporting by 30 Sep 2026", "timeline", "Both BICs in Q3"),
    ("R16", "Certification published by 30 Nov 2026", "timeline", "Incl. Q4 remediation"),
    ("R17", "Offer irrevocable 120 days", "timeline", "Binding validity"),
    ("R18", "Dual pricing: T&M AND Fixed Price", "commercial", "Two offers required"),
    ("R19", "Rate card per profile + resource plan", "commercial", "Per-role rates"),
    ("R20", "Quotation in EUR", "commercial", "EUR"),
    ("R21", "Multi-year discount offered", "commercial", "If Etex commits multi-year"),
    ("R22", "NDA signed (A01)", "legal", "Confidentiality agreement"),
    ("R23", "Etex standard Master Services Template accepted", "legal", "A05 governs agreement"),
    ("R24", "Supplier Code of Conduct (A04)", "legal", "Meet/exceed Etex minimums"),
    ("R25", "Personal data protection compliance", "legal", "EU data protection, indemnity"),
    ("R26", "Belgian law, Brussels jurisdiction", "legal", "Governing law"),
    ("R27", "Etex IP ownership of deliverables", "legal", "Exclusive from creation"),
    ("R28", "Third-party IP / no viral OSS", "legal", "Disclosure + approval"),
    ("R29", "Subcontractor disclosure", "legal", "Subcontractor form"),
    ("R30", "SLAs, warranties, indemnities per Etex standards", "legal", "Contractual standards"),
    ("R31", "Liability caps per Etex rules (carve-outs)", "legal", "No fee-multiplier caps"),
    ("R32", "English language", "legal", "Proposals + delivery in English"),
    ("R33", "Assessment report(s) per BIC", "deliverable", "Report per assessment expected"),
    ("R34", "Credentials / references", "deliverable", "Comparable experience"),
    ("R35", "Risk management methodology", "deliverable", "Scope creep, delays, overruns"),
    ("R36", "Team CVs", "deliverable", "Key members, interviewable"),
    ("R37", "CSR / EcoVadis disclosure", "deliverable", "Score shared with Etex"),
    ("R38", "Response format (Word/Excel/PPT)", "deliverable", "Complete package"),
    ("R39", "Existing Etex relationship disclosed", "deliverable", "Incl. consolidation benefits"),
    ("R40", "A02 Etex obligations completed (man-days + RACI)", "deliverable", "Days per role, IT + business"),
)

RACI_ACTIVITIES: tuple[str, ...] = (
    "Supplier shortlist & recommendation",
    "Sample validation",
    "Commercial term alignment",
    "Logistics / lead-time validation",
    "Contract / frame agreement route",
    "TCO / business case validation",
    "Final supplier award decision",
)

RACI_ROLES: tuple[str, ...] = (
    "Procurement",
    "Quality / Technical",
    "Supply Chain",
    "Finance",
    "Legal",
    "Plant / Operations",
    "Steerco / Management",
    "Suppliers",
)

# Default RACI from France overview (humans still own award).
RACI_DEFAULT: tuple[tuple[str, ...], ...] = (
    ("R/A", "C", "C", "C", "I", "C", "A", "I"),
    ("C", "R/A", "C", "I", "I", "C", "I", "R"),
    ("R/A", "C", "C", "C", "C", "I", "I", "R"),
    ("C", "C", "R/A", "I", "I", "R", "I", "C"),
    ("R", "I", "I", "C", "R/A", "I", "I", "C"),
    ("C", "I", "C", "R/A", "I", "I", "I", "I"),
    ("R", "C", "C", "C", "C", "C", "A", "I"),
)

MISSING = "missing"
SCORED = "To be scored by Etex evaluation team"
EXTRACT_MAX_TOKENS = 16384
CORPUS_CHAR_LIMIT = 28_000

# CURSOR-GUIDE §3 — three distinct render states, never collapsed.
NOT_STATED = "Not stated in submission"
NOT_OFFERED = "Not offered"
EXTRACTION_FAILED = "Extraction failed — retry"
REVIEWED_MARK = "[reviewed]"
SOURCE_QUALITY_PREFIX = "⚠ source quality (high):"
UNCERTAIN_PREFIX = "uncertain — review: "
CONFIDENCE_FLOOR = 0.7
# An hourly rate shown against a daily one is an 8x error in a bid comparison.
MIXED_RATE_BASIS = "mixed rate basis — see pricing lines"

# Marks matching the richness-bar workbook legend; phrases stay distinct.
STATUS_MARK = {
    "met": "✓",
    "partial": "~",
    "not_offered": "✗",
    "not_stated": "?",
    "unclear": "?",
    "extraction_failed": "retry",
}
REQUIREMENTS_LEGEND = (
    f"Legend:  {NOT_STATED}  ≠  {NOT_OFFERED}  ≠  {EXTRACTION_FAILED}.  "
    "✓ = met / evidenced.  ~ = partial.  ✗ = not offered / gap.  "
    "? = not stated in submission.  retry = extraction failed (not an answer).  "
    "[reviewed] = pinned.  [p.N] = cited page.  ⚠ source quality (high) = cited artifact flag.  "
    "— = Etex-side process step."
)
