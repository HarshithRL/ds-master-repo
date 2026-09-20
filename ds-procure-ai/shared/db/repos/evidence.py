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
        row.claim_text = detail or f"Set to {status} by {reviewer}."
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
            row.reviewed_by = None
            row.reviewed_at = None
        session.flush()
