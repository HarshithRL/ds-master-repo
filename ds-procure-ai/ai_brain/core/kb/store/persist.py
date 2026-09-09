"""SQL upserts for requirement / evidence / pricing_line. Idempotent on model_version."""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import select

from ai_brain.core.kb.api.schemas import (
    BidProfile,
    EvidenceItem,
    PricingExtraction,
    VendorEvidenceBundle,
    apply_grounding_gate,
)
from ai_brain.core.kb.skills import SKILLS_PACK_VERSION
from ai_brain.core.procurement_ai.packs.matrix_layout import SWIFT_REQUIREMENTS
from shared.db.connection import session_scope
from shared.db.models import BidProfileRow, Evidence, PricingLine, Requirement, utc_now_iso

MODEL_VERSION = "vendor-analyst-1"
PROMPT_VERSION = SKILLS_PACK_VERSION

_TIMELINE_OPTIONAL = frozenset(
    {f"R{i:02d}" for i in range(10, 18)}
)


def seed_swift_requirements(project_id: str) -> int:
    """Upsert R01–R40 for this project. Stable IDs match the SWIFT overlay."""
    if not project_id:
        return 0
    now = utc_now_iso()
    written = 0
    with session_scope() as session:
        for ordinal, (rid, text, category, target) in enumerate(SWIFT_REQUIREMENTS, start=1):
            row = session.get(Requirement, rid)
            if row is None:
                session.add(
                    Requirement(
                        id=rid,
                        project_id=project_id,
                        ordinal=ordinal,
                        section=target,
                        text=text,
                        category=category,
                        mandatory=0 if rid in _TIMELINE_OPTIONAL else 1,
                        created_at=now,
                    )
                )
                written += 1
            elif row.project_id == project_id:
                row.ordinal = ordinal
                row.section = target
                row.text = text
                row.category = category
            else:
                # Another project owns this R-id in this sqlite file; skip clash.
                continue
        session.flush()
    return written


def requirement_ids(project_id: str) -> list[str]:
    with session_scope() as session:
        rows = session.scalars(
            select(Requirement)
            .where(Requirement.project_id == project_id)
            .order_by(Requirement.ordinal, Requirement.id)
        ).all()
        return [row.id for row in rows]


def upsert_evidence_bundle(
    project_id: str,
    bundle: VendorEvidenceBundle,
    *,
    model_version: str = MODEL_VERSION,
    prompt_version: str = PROMPT_VERSION,
) -> dict[str, int]:
    """Ground then upsert. Reviewed cells are not overwritten."""
    gated: list[EvidenceItem] = []
    for item in bundle.items:
        gated.append(apply_grounding_gate(item, project_id=project_id))
    now = utc_now_iso()
    inserted = 0
    updated = 0
    skipped_reviewed = 0
    with session_scope() as session:
        for item in gated:
            existing = session.scalars(
                select(Evidence).where(
                    Evidence.requirement_id == item.requirement_id,
                    Evidence.vendor_id == bundle.bid_id,
                    Evidence.model_version == model_version,
                )
            ).first()
            if existing is not None and (existing.reviewed_by or "").strip():
                skipped_reviewed += 1
                continue
            if existing is None:
                session.add(
                    Evidence(
                        id=str(uuid.uuid4()),
                        project_id=project_id,
                        requirement_id=item.requirement_id,
                        vendor_id=bundle.bid_id,
                        status=item.status,
                        claim_text=item.claim_text,
                        artifact_id=item.artifact_id,
                        chunk_id=item.chunk_id,
                        page=item.page,
                        confidence=item.confidence,
                        model_version=model_version,
                        prompt_version=prompt_version,
                        extracted_at=now,
                    )
                )
                inserted += 1
            else:
                existing.status = item.status
                existing.claim_text = item.claim_text
                existing.artifact_id = item.artifact_id
                existing.chunk_id = item.chunk_id
                existing.page = item.page
                existing.confidence = item.confidence
                existing.prompt_version = prompt_version
                existing.extracted_at = now
                updated += 1
        session.flush()
    return {
        "inserted": inserted,
        "updated": updated,
        "skipped_reviewed": skipped_reviewed,
        "gated": len(gated),
    }


def upsert_pricing(
    project_id: str,
    extraction: PricingExtraction,
    *,
    model_version: str = MODEL_VERSION,
) -> int:
    written = 0
    with session_scope() as session:
        for line in extraction.lines:
            session.add(
                PricingLine(
                    id=str(uuid.uuid4()),
                    project_id=project_id,
                    vendor_id=extraction.bid_id,
                    offer_type=line.offer_type,
                    role=line.role,
                    seniority=line.seniority,
                    rate=line.rate,
                    rate_unit=line.rate_unit,
                    currency=line.currency,
                    quantity=line.quantity,
                    line_total=line.line_total,
                    artifact_id=line.artifact_id,
                    page=line.page,
                    chunk_id=line.chunk_id,
                    verified=0,
                    model_version=model_version,
                )
            )
            written += 1
        session.flush()
    return written


def upsert_bid_profile(
    project_id: str,
    profile: BidProfile,
    *,
    model_version: str = MODEL_VERSION,
) -> int:
    if not project_id or not profile or not (profile.bid_id or "").strip():
        return 0
    now = utc_now_iso()
    payload = profile.model_dump(exclude_none=True)
    with session_scope() as session:
        existing = session.scalars(
            select(BidProfileRow).where(
                BidProfileRow.project_id == project_id,
                BidProfileRow.vendor_id == profile.bid_id,
                BidProfileRow.model_version == model_version,
            )
        ).first()
        if existing is None:
            session.add(
                BidProfileRow(
                    id=str(uuid.uuid4()),
                    project_id=project_id,
                    vendor_id=profile.bid_id,
                    facts_json=json.dumps(payload, ensure_ascii=False),
                    model_version=model_version,
                    extracted_at=now,
                )
            )
        else:
            existing.facts_json = json.dumps(payload, ensure_ascii=False)
            existing.extracted_at = now
        session.flush()
    return 1


def fill_extraction_failed(
    project_id: str,
    bid_id: str,
    *,
    detail: str = "",
    model_version: str = MODEL_VERSION,
    prompt_version: str = PROMPT_VERSION,
) -> int:
    """Mark every requirement for this bid as extraction_failed (not not_stated)."""
    ids = requirement_ids(project_id)
    if not ids:
        seed_swift_requirements(project_id)
        ids = requirement_ids(project_id)
    now = utc_now_iso()
    written = 0
    note = (detail or "vendor analyst did not return a grounded bundle")[:500]
    with session_scope() as session:
        for rid in ids:
            existing = session.scalars(
                select(Evidence).where(
                    Evidence.requirement_id == rid,
                    Evidence.vendor_id == bid_id,
                    Evidence.model_version == model_version,
                )
            ).first()
            if existing is not None and (existing.reviewed_by or "").strip():
                continue
            if existing is None:
                session.add(
                    Evidence(
                        id=str(uuid.uuid4()),
                        project_id=project_id,
                        requirement_id=rid,
                        vendor_id=bid_id,
                        status="extraction_failed",
                        claim_text=note,
                        model_version=model_version,
                        prompt_version=prompt_version,
                        extracted_at=now,
                        confidence=0.0,
                    )
                )
                written += 1
            elif existing.status != "extraction_failed":
                existing.status = "extraction_failed"
                existing.claim_text = note
                existing.extracted_at = now
                written += 1
        session.flush()
    return written


def kb_counts(project_id: str) -> dict[str, Any]:
    from sqlalchemy import func

    from shared.db.models import Artifact, BidProfileRow, PricingLine, Vendor

    with session_scope() as session:
        def _count(model, extra=None):
            q = select(func.count()).select_from(model).where(model.project_id == project_id)
            if extra is not None:
                q = q.where(extra)
            return int(session.scalar(q) or 0)

        artifacts_ok = _count(Artifact, Artifact.parse_status == "ok")
        classified = int(
            session.scalar(
                select(func.count())
                .select_from(Artifact)
                .where(
                    Artifact.project_id == project_id,
                    Artifact.vendor_id.is_not(None),
                )
            )
            or 0
        )
        return {
            "project_id": project_id,
            "artifacts_ok": artifacts_ok,
            "classified": classified,
            "vendors": _count(Vendor),
            "requirements": _count(Requirement),
            "evidence": _count(Evidence),
            "pricing_line": _count(PricingLine),
            "bid_profile": _count(BidProfileRow),
        }
