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

- The bid list comes from SQL, never from the model.
- Mandatory requirements (`mandatory=1`) fail closed: no citation →
  `not_stated`, never a guessed ✓.
- A high-severity `quality_flag` on the cited artifact is a source-quality
  warning on the cell, not a reason to mark `not_stated`.
- `reviewed_by` cells are pinned; do not "improve" them on re-extraction.

## Scoring

Do not invent weights. Copy `requirement.weight` / `section` from the
requirement row. Narrative commentary belongs in notes, not in `status`.
