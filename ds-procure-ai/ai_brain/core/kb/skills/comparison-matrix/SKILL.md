---
name: comparison-matrix
description: Use when the user asks to create or rebuild a vendor comparison
  matrix, BAFO workbook, or SWIFT-style requirements grid. Request-time
  extraction from parsed files — do not read SQL evidence tables.
---
# Comparison matrix (request-time)

Excel is the only persist. Iterate chunks via MCP (`list_bids`,
`list_bid_chunks`, `read_chunk` / `read_chunks`, `search_project_kb`) and
`/project/` files. Do not invent EUR. Humans award.

## Process types (never mix)

- `direct_tg` — P×Q / materials. No SWIFT R01–R40 overlay.
- `indirect_it_software` — licence + implementation TCO.
- `indirect_it_services` — professional services. SWIFT CSP uses R01–R40.

Mark rows that do not apply as `N/A` with a short reason when known
(e.g. `N/A - advisory service, no software`). `N/A` ≠ missing.

## Cell richness (SWIFT CSP Vendor Comparison.xlsx)

Prefer a cited narrative over a bare number:

- `€3,600 (4.5 days)` not `3600`
- `Not quantified` / `Not quoted (2-year view only)` when the source is silent
- Ranges stay ranges (`€78,400–109,600`)
- Scorecard, Architecture Assessment, Security Assessment, Customer Feedback
  stay `To be scored by Etex evaluation team` / `Added Manually`

## Requirement marks

`not_stated` ≠ `not_offered` ≠ `extraction_failed`. Cell `value_text` may
append a short justification (`✓ 21 mandatory/BIC`). Etex process steps
use `—`. Every `✓` `~` `✗` needs quote + locator or chunk_id.

## Delegation

1. `rfp_analyst` — requirement spine from the RFP (SWIFT overlay when CSP).
2. `vendor_analyst` per bid — walk **all** bid chunks, then BAFO strings.
3. `bafo_compiler` — missing-requirement lists, key flags, method notes.
4. Stop. A separate emit agent returns `ComparisonMatrix`.
