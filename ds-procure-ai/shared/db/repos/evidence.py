"""Human review of extracted evidence.

The read side of this already existed and is honoured everywhere — `persist.py`
refuses to overwrite a reviewed cell on re-extraction, and
`matrix_from_evidence.pick_evidence_row` pins reviewed rows so the workbook
shows them instead of the model's answer. Nothing could ever *set*
`reviewed_by`, so the override was unreachable. This is the writer.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from shared.db.connection import session_scope
from shared.db.models import Evidence, utc_now_iso
from shared.logger_global import get_logger

log = get_logger(__name__)

# `extraction_failed` is a machine outcome; a human states a real verdict.
REVIEWABLE_STATUSES = ("met", "partial", "not_offered", "not_stated", "unclear")

MODEL_VERSION = "vendor-analyst-1"
REVIEW_PROMPT_VERSION = "human-review"

# A review states what a human decided; overwriting claim_text with it erased
# what the model had found, leaving "why was this changed?" unanswerable. The
# note leads, the model's quote is kept under this marker. `evidence` has no
# column for a note, so the two share the field rather than one destroying the
# other.
MODEL_EVIDENCE_PREFIX = "— model evidence: "
_MODEL_EVIDENCE_SEPARATOR = f"\n\n{MODEL_EVIDENCE_PREFIX}"


def split_review_claim(claim_text: str | None) -> tuple[str, str]:
    """(analyst note, model evidence). An unreviewed claim is all model."""
    text = (claim_text or "").strip()
    if _MODEL_EVIDENCE_SEPARATOR in text:
        note, _, model = text.partition(_MODEL_EVIDENCE_SEPARATOR)
        return note.strip(), model.strip()
    return "", text


def _unpin(row: Evidence) -> None:
    """Drop the human verdict and put the model's own words back in the cell."""
    note, model_evidence = split_review_claim(row.claim_text)
    # No marker on a reviewed row means the review created it: the text is the
    # analyst's note, and keeping it would read back as something the model
    # found. An empty cell is honest and re-extraction refills it.
    row.claim_text = model_evidence if note else None
    row.reviewed_by = None
    row.reviewed_at = None


def clear_all_reviews(project_id: str) -> int:
    """Unpin every reviewed cell in a project. Used by a deliberate reset."""
    if not project_id:
        return 0
    with session_scope() as session:
        rows = session.scalars(
            select(Evidence).where(Evidence.project_id == project_id)
        ).all()
        cleared = 0
        for row in rows:
            if not (row.reviewed_by or "").strip():
                continue
            _unpin(row)
            cleared += 1
        session.flush()
    log.info("cleared reviews project_id={} rows={}", project_id, cleared)
    return cleared


class EvidenceNotFoundError(LookupError):
    pass


def _to_dict(row: Evidence) -> dict[str, Any]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "requirement_id": row.requirement_id,
        "vendor_id": row.vendor_id,
        "status": row.status,
        "claim_text": row.claim_text,
        "reviewed_by": row.reviewed_by,
        "reviewed_at": row.reviewed_at,
        "extracted_at": row.extracted_at,
    }


def set_review(
    project_id: str,
    requirement_id: str,
    vendor_id: str,
    *,
    status: str,
    note: str = "",
    reviewed_by: str,
) -> dict[str, Any]:
    """Pin an analyst verdict onto one requirement/vendor cell."""
    if status not in REVIEWABLE_STATUSES:
        raise ValueError(f"status must be one of {', '.join(REVIEWABLE_STATUSES)}")
    reviewer = (reviewed_by or "").strip()
    if not reviewer:
        raise ValueError("reviewed_by is required")
    now = utc_now_iso()
    detail = (note or "").strip()[:500]

    with session_scope() as session:
        rows = session.scalars(
            select(Evidence).where(
                Evidence.project_id == project_id,
                Evidence.requirement_id == requirement_id,
                Evidence.vendor_id == vendor_id,
            )
        ).all()
        # Update in place so `persist.py`'s reviewed-cell guard protects it.
        row = max(rows, key=lambda r: r.extracted_at or "") if rows else None
        if row is None:
            row = Evidence(
                id=str(uuid.uuid4()),
                project_id=project_id,
                requirement_id=requirement_id,
                vendor_id=vendor_id,
                model_version=MODEL_VERSION,
                prompt_version=REVIEW_PROMPT_VERSION,
                extracted_at=now,
            )
            session.add(row)
        row.status = status
        # Re-reviewing must not nest: the model's quote is carried across, never
        # re-wrapped around the previous note.
        _, model_evidence = split_review_claim(row.claim_text)
        note_line = detail or f"Set to {status} by {reviewer}."
        row.claim_text = (
            f"{note_line}{_MODEL_EVIDENCE_SEPARATOR}{model_evidence}"
            if model_evidence
            else note_line
        )
        row.confidence = 1.0
        row.reviewed_by = reviewer
        row.reviewed_at = now
        session.flush()
        log.info(
            "evidence reviewed project_id={} requirement={} vendor={} status={} by={}",
            project_id,
            requirement_id,
            vendor_id,
            status,
            reviewer,
        )
        return _to_dict(row)


def clear_review(project_id: str, requirement_id: str, vendor_id: str) -> None:
    """Hand the cell back to the model on the next extraction."""
    with session_scope() as session:
        rows = session.scalars(
            select(Evidence).where(
                Evidence.project_id == project_id,
                Evidence.requirement_id == requirement_id,
                Evidence.vendor_id == vendor_id,
            )
        ).all()
        reviewed = [r for r in rows if (r.reviewed_by or "").strip()]
        if not reviewed:
            raise EvidenceNotFoundError(f"{requirement_id}/{vendor_id}")
        for row in reviewed:
            _unpin(row)
        session.flush()
