---
name: swift-csp
description: Use when the question or document mentions SWIFT CSP, CSCF,
  architecture types A1–A4, BIC codes (ETEXBEBB, URSNESMMXXX), mandatory vs
  advisory controls, independent assessment scope, service-bureau reliance,
  or attestation for a SWIFT Customer Security Programme engagement.
---
# SWIFT CSP / CSCF

## Architecture types

CSCF classifies SWIFT connectivity as architecture types **A1–A4**. The type
drives which controls are mandatory vs advisory. Do not infer an architecture
type from a filename or from a neighbouring BIC.

This corpus is dense with **A4** references. Etex's working assumption (to be
confirmed by the supplier, never by the extractor) is Architecture Type A4
for both in-scope BICs:

- `ETEXBEBB` — Etex Group
- `URSNESMMXXX` — URSA / Etex Insulation Division

Each BIC has its own environment, control set, and (often) a separate
assessment report. Do not collapse two BICs into one row.

## Assessment scope

Independent assessment + attestation support is in scope when the RFP or
proposal states it. Service-bureau reliance (e.g. FIDES, BME) is a fact
only when cited. Advisory controls and TMS replacement are out of scope
unless the cited chunk says otherwise.

## Extraction rules

- Quote the architecture type and CSCF version (e.g. CSCF 2026) from the
  cited page. If the page does not say A4, status is `not_stated`.
- Mandatory vs advisory is a closed distinction; do not promote advisory
  language into a "met" mandatory cell.
- Prior-year assessments (e.g. 2025) are not evidence that a 2026 control
  is met.
