"""SQL upserts for requirement / evidence / pricing_line. Idempotent on model_version."""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import delete, insert, select, update

from ai_brain.core.kb.api.schemas import (
    ABSENCE_UNVERIFIED_TEXT,
    BidProfile,
    EvidenceItem,
    PricingExtraction,
    VendorEvidenceBundle,
    apply_grounding_gate,
    load_artifact_markdown,
    load_chunk_texts,
)
from ai_brain.core.kb.skills import SKILLS_PACK_VERSION
from ai_brain.core.procurement_ai.packs.matrix_layout import SWIFT_REQUIREMENTS
from shared.db.connection import session_scope
from shared.db.models import (
    BidProfileRow,
    Evidence,
    PricingLine,
    QualityFlag,
    Requirement,
    utc_now_iso,
)

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
    with session_scope() as session:
        existing = {
            row.id: row
            for row in session.scalars(
                select(Requirement).where(Requirement.project_id == project_id)
            ).all()
        }
        new_rows: list[dict[str, Any]] = []
        updates: list[dict[str, Any]] = []
        for ordinal, (rid, text, category, target) in enumerate(SWIFT_REQUIREMENTS, start=1):
            fields = {
                "ordinal": ordinal,
                "section": target,
                "text": text,
                "category": category,
            }
            row = existing.get(rid)
            if row is None:
                new_rows.append(
                    {
                        "id": rid,
                        "project_id": project_id,
                        "mandatory": 0 if rid in _TIMELINE_OPTIONAL else 1,
                        "created_at": now,
                        **fields,
                    }
                )
            elif (
                row.ordinal != ordinal
                or row.section != target
                or row.text != text
                or row.category != category
            ):
                updates.append({"id": rid, "project_id": project_id, **fields})
        # Was a get() plus a write per requirement: 80 statements on every
        # build, even when the static overlay had not changed at all.
        if new_rows:
            session.execute(insert(Requirement), new_rows)
        if updates:
            session.execute(
                update(Requirement).execution_options(synchronize_session=False),
                updates,
            )
        session.flush()
    return len(new_rows)


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
    bid_id: str | None = None,
    unverified_absence: bool = False,
    model_version: str = MODEL_VERSION,
    prompt_version: str = PROMPT_VERSION,
) -> dict[str, int]:
    """Ground then upsert. Reviewed cells are not overwritten."""
    # Caller-supplied bid_id wins: dedup below DELETEs rows, so a bundle that
    # echoed the wrong bid would destroy another vendor's evidence.
    vendor = (bid_id or bundle.bid_id or "").strip()
    gated: list[EvidenceItem] = []
    # Grounding one item at a time costs a DBSQL round trip per chunk and a full
    # re-parse of the artifact JSON per fallback, which stalls the whole build on
    # large vendors. Read every chunk once, and read each artifact at most once.
    chunk_texts = load_chunk_texts(
        item.chunk_id for item in bundle.items if item.chunk_id
    )
    artifact_cache: dict[str, str | None] = {}
    ungrounded: list[Any] = []

    def _artifact_markdown(artifact_id: str) -> str | None:
        if artifact_id not in artifact_cache:
            artifact_cache[artifact_id] = load_artifact_markdown(artifact_id)
        return artifact_cache[artifact_id]

    for item in bundle.items:
        gated.append(
            apply_grounding_gate(
                item,
                project_id=project_id,
                chunk_lookup=chunk_texts.get,
                artifact_lookup=_artifact_markdown,
                flag_sink=ungrounded,
            )
        )
    now = utc_now_iso()
    skipped_reviewed = 0
    unverified = 0
    with session_scope() as session:
        existing_rows = session.scalars(
            select(Evidence).where(
                Evidence.project_id == project_id,
                Evidence.vendor_id == vendor,
                Evidence.model_version == model_version,
            )
        ).all()
        by_requirement: dict[str, Evidence] = {}
        duplicate_ids: list[str] = []
        for row in existing_rows:
            kept = by_requirement.get(row.requirement_id)
            if kept is None:
                by_requirement[row.requirement_id] = row
                continue
            kept_reviewed = bool((kept.reviewed_by or "").strip())
            row_reviewed = bool((row.reviewed_by or "").strip())
            if row_reviewed and not kept_reviewed:
                duplicate_ids.append(kept.id)
                by_requirement[row.requirement_id] = row
            elif not row_reviewed:
                duplicate_ids.append(row.id)
            # Both reviewed: leave the duplicate rather than delete human work.

        new_rows: list[dict[str, Any]] = []
        updates: list[dict[str, Any]] = []
        # The model can emit the same requirement twice. The old per-item SELECT
        # absorbed that through autoflush; a batched write would insert both.
        for item in {item.requirement_id: item for item in gated}.values():
            existing = by_requirement.get(item.requirement_id)
            if existing is not None and (existing.reviewed_by or "").strip():
                skipped_reviewed += 1
                continue
            fields = {
                "status": item.status,
                "claim_text": item.claim_text,
                "artifact_id": item.artifact_id,
                "chunk_id": item.chunk_id,
                "page": item.page,
                "confidence": item.confidence,
                "prompt_version": prompt_version,
                "extracted_at": now,
            }
            if unverified_absence and item.status == "not_stated":
                # Absence is only a finding if the whole bid was read.
                fields["status"] = "extraction_failed"
                fields["claim_text"] = ABSENCE_UNVERIFIED_TEXT
                fields["confidence"] = 0.0
                unverified += 1
            if existing is None:
                new_rows.append(
                    {
                        "id": str(uuid.uuid4()),
                        "project_id": project_id,
                        "requirement_id": item.requirement_id,
                        "vendor_id": vendor,
                        "model_version": model_version,
                        **fields,
                    }
                )
            else:
                updates.append({"id": existing.id, **fields})

        # Statement count must not scale with the bundle. Row-at-a-time writes
        # ran past the node deadline on Delta, and the per-item SELECT made it
        # 80 statements for 40 requirements.
        if duplicate_ids:
            # Concurrent builds once inserted the same requirement twice; a
            # plain dict would hide the extra row instead of healing it.
            session.execute(
                delete(Evidence)
                .where(Evidence.id.in_(duplicate_ids))
                .execution_options(synchronize_session=False)
            )
        if new_rows:
            session.execute(insert(Evidence), new_rows)
        if updates:
            session.execute(
                update(Evidence).execution_options(synchronize_session=False),
                updates,
            )
        if ungrounded:
            session.execute(
                insert(QualityFlag),
                [
                    {c.name: getattr(flag, c.name) for c in QualityFlag.__table__.columns}
                    for flag in ungrounded
                ],
            )
        inserted = len(new_rows)
        updated = len(updates)
        session.flush()
    return {
        "inserted": inserted,
        "updated": updated,
        "skipped_reviewed": skipped_reviewed,
        "gated": len(gated),
        "deduped": len(duplicate_ids),
        "unverified_absence": unverified,
    }


def upsert_pricing(
    project_id: str,
    extraction: PricingExtraction,
    *,
    bid_id: str | None = None,
    model_version: str = MODEL_VERSION,
) -> int:
    # Caller-supplied bid_id wins: this function now DELETES the bid's existing
    # rows, so a hallucinated bid_id would wipe another vendor's rate card.
    vendor = (bid_id or extraction.bid_id or "").strip()
    if not project_id or not vendor:
        return 0
    rows = [
        {
            "id": str(uuid.uuid4()),
            "project_id": project_id,
            "vendor_id": vendor,
            "offer_type": line.offer_type,
            "role": line.role,
            "seniority": line.seniority,
            "rate": line.rate,
            "rate_unit": line.rate_unit,
            "currency": line.currency,
            "quantity": line.quantity,
            "line_total": line.line_total,
            "artifact_id": line.artifact_id,
            "page": line.page,
            "chunk_id": line.chunk_id,
            "verified": 0,
            "model_version": model_version,
        }
        for line in extraction.lines
    ]
    with session_scope() as session:
        # Replace, don't append. This table was insert-only, so every rebuild
        # stacked another copy of the bid's rate card into the comparison
        # matrix (observed: 6 -> 10 -> 25 lines across three runs).
        session.execute(
            delete(PricingLine)
            .where(
                PricingLine.project_id == project_id,
                PricingLine.vendor_id == vendor,
                PricingLine.model_version == model_version,
            )
            .execution_options(synchronize_session=False)
        )
        if rows:
            session.execute(insert(PricingLine), rows)
        session.flush()
    return len(rows)


def upsert_bid_profile(
    project_id: str,
    profile: BidProfile,
    *,
    bid_id: str | None = None,
    model_version: str = MODEL_VERSION,
) -> int:
    vendor = (bid_id or (profile.bid_id if profile else "") or "").strip()
    if not project_id or not profile or not vendor:
        return 0
    now = utc_now_iso()
    payload = profile.model_dump(exclude_none=True)
    with session_scope() as session:
        existing = session.scalars(
            select(BidProfileRow).where(
                BidProfileRow.project_id == project_id,
                BidProfileRow.vendor_id == vendor,
                BidProfileRow.model_version == model_version,
            )
        ).first()
        if existing is None:
            session.add(
                BidProfileRow(
                    id=str(uuid.uuid4()),
                    project_id=project_id,
                    vendor_id=vendor,
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
    note = (detail or "vendor analyst did not return a grounded bundle")[:500]
    with session_scope() as session:
        # One round trip: this runs inside the timeout cleanup window, where 40
        # separate DBSQL lookups did not finish before the node was killed.
        existing_rows = session.scalars(
            select(Evidence).where(
                Evidence.project_id == project_id,
                Evidence.vendor_id == bid_id,
                Evidence.model_version == model_version,
            )
        ).all()
        by_requirement = {row.requirement_id: row for row in existing_rows}
        new_rows: list[dict[str, Any]] = []
        stale_ids: list[str] = []
        for rid in ids:
            existing = by_requirement.get(rid)
            if existing is not None and (existing.reviewed_by or "").strip():
                continue
            if existing is None:
                new_rows.append(
                    {
                        "id": str(uuid.uuid4()),
                        "project_id": project_id,
                        "requirement_id": rid,
                        "vendor_id": bid_id,
                        "status": "extraction_failed",
                        "claim_text": note,
                        "model_version": model_version,
                        "prompt_version": prompt_version,
                        "extracted_at": now,
                        "confidence": 0.0,
                    }
                )
            elif existing.status != "extraction_failed":
                stale_ids.append(existing.id)
        # Two statements, not one per requirement. Row-at-a-time here cost ~120s
        # for 40 rows on Delta and ate a fifth of the node budget.
        if new_rows:
            session.execute(insert(Evidence), new_rows)
        if stale_ids:
            session.execute(
                update(Evidence)
                .where(Evidence.id.in_(stale_ids))
                .values(status="extraction_failed", claim_text=note, extracted_at=now)
            )
        written = len(new_rows) + len(stale_ids)
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
