---
name: rfp-evaluation
description: Use when scoring a bid against RFP requirements, applying the
  evaluation rubric, weighting mandatory vs optional items, or deciding
  between not_stated, not_offered, and extraction_failed for a matrix cell.
---
# RFP evaluation

## Render states (closed vocabulary)

These three are **not** interchangeable. Using the wrong one is a product
failure, not a style choice.

| Status | Meaning | Matrix render |
|---|---|---|
| `not_stated` | The submission does not address the requirement. Absence of text. | "Not stated in submission" |
| `not_offered` | The vendor explicitly declines or excludes the item. | Distinct from not_stated |
| `extraction_failed` | We could not extract (parse/quality/model). Not an answer. | Retry affordance, never a verdict |

`unclear` is for grounded-but-ambiguous claims after the grounding gate.
`partial` is for a cited, incomplete match. `met` requires a cited claim.

## Rubric stance

- The bid list comes from classified `artifact.vendor_id` via MCP
  `list_bids`, never from guessed filenames.
- Mandatory requirements (`mandatory=1`) fail closed: no citation →
  `not_stated`, never a guessed ✓.
- A high-severity `quality_flag` on the cited artifact is a source-quality
  warning on the cell, not a reason to mark `not_stated`.
- `reviewed_by` cells are pinned; do not "improve" them on re-extraction.

## Matrix cell text

The Excel cell is `value_text`, not the raw status enum. SWIFT baseline:

- `✓` plus a short cited fact (`✓ 21 mandatory/BIC`, `✓ signed`)
- `~` plus the condition (`~ single F&R report for both`)
- `✗` plus the gap (`✗ T&M only`, `✗ reporting Nov`)
- `?` when the submission is silent (`Not stated in submission`)
- `—` for Etex-side process steps (shortlist, award calendar)

Do not collapse these into a single "missing" token.

## Scoring

Do not invent weights. Copy `requirement.weight` / `section` from the
requirement row. Narrative commentary belongs in notes, not in `status`.
The comparison matrix is filled at request time from parsed chunks, not
from SQL `evidence` rows.
