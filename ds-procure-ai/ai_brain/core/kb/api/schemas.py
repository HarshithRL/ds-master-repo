"""Extraction schemas and the citation-or-abstain / grounding gate.

Accuracy is enforced here, not requested in the prompt. Closed status
vocabulary matches `evidence.status` CHECK (minus `extraction_failed`,
which is a post-processing persist state, not a model output).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select

from shared.db.connection import session_scope
from shared.db.models import Chunk, QualityFlag, utc_now_iso

EvidenceStatus = Literal["met", "partial", "not_offered", "not_stated", "unclear"]
UNGROUNDED_KIND = "ungrounded_claim"
# Grounding proves the quote is in the document, not that it answers the
# requirement: "€ 1.600" really was cited for "Certification published by
# 30 Nov". A fragment this short cannot carry a compliance verdict, so it goes
# to a human as unclear instead of crediting the vendor.
THIN_CLAIM_KIND = "thin_met_claim"
MIN_MET_CLAIM_CHARS = 25
# not_stated asserts the document is silent, which only holds if the analyst read
# it all. When research is cut short the absence is ours, not the bidder's.
INCOMPLETE_RESEARCH_NOTE = "research incomplete: absence not verified"
ABSENCE_UNVERIFIED_TEXT = (
    "not determined: the analyst did not finish reading this bid, so no "
    "conclusion about the bidder was drawn"
)

ChunkLookup = Callable[[str], str | None]
ArtifactLookup = Callable[[str], str | None]
# One connection, several statements, rather than one huge IN list.
CHUNK_FETCH_BATCH = 500


class EvidenceItem(BaseModel):
    requirement_id: str
    status: EvidenceStatus
    claim_text: str | None = None
    artifact_id: str | None = None
    page: int | None = None
    chunk_id: str | None = None
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def citation_or_abstain(self) -> EvidenceItem:
        if self.status == "not_stated":
            return self
        if not self.claim_text:
            raise ValueError(
                "every non-not_stated claim requires claim_text and "
                "(chunk_id or artifact_id + page)"
            )
        if self.chunk_id:
            return self
        if self.artifact_id and self.page is not None:
            return self
        raise ValueError(
            "every non-not_stated claim requires claim_text and "
            "(chunk_id or artifact_id + page)"
        )


class EntityMention(BaseModel):
    name: str
    type: Literal["LegalEntity", "Person", "Bid"] = "LegalEntity"
    registry_id: str | None = None
    artifact_id: str | None = None
    page: int | None = None


class VendorEvidenceBundle(BaseModel):
    bid_id: str
    items: list[EvidenceItem]
    entities: list[EntityMention] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class PricingLineItem(BaseModel):
    offer_type: Literal["fixed_price", "time_and_materials"]
    role: str | None = None
    seniority: str | None = None
    rate: float | None = None
    rate_unit: str | None = None
    currency: str | None = None
    quantity: float | None = None
    line_total: float | None = None
    artifact_id: str | None = None
    page: int | None = None
    chunk_id: str | None = None
    claim_text: str | None = None


class PricingExtraction(BaseModel):
    bid_id: str
    lines: list[PricingLineItem] = Field(default_factory=list)


class BidProfile(BaseModel):
    """BAFO qualitative + multi-year TCO strings. Missing fields stay unset."""

    bid_id: str
    legal_name: str | None = None
    y1_solution: str | None = None
    y1_service: str | None = None
    y1_etex_mandays: str | None = None
    y1_tco: str | None = None
    y2_solution: str | None = None
    y2_service: str | None = None
    y2_etex_mandays: str | None = None
    y2_tco: str | None = None
    y3_solution: str | None = None
    y3_service: str | None = None
    y3_etex_mandays: str | None = None
    y3_tco: str | None = None
    tco_3_5: str | None = None
    indexation: str | None = None
    blended_rate: str | None = None
    vendor_mandays: str | None = None
    etex_mandays: str | None = None
    timeline: str | None = None
    ecovadis: str | None = None
    creditscore: str | None = None
    delivery_model: str | None = None
    assumptions: str | None = None
    legal: str | None = None
    obligations: str | None = None
    risk_plan: str | None = None
    scope_completeness: str | None = None
    missing_requirements: str | None = None
    citations: dict[str, dict[str, Any]] = Field(default_factory=dict)


def bid_profile_filled(profile: BidProfile | None) -> bool:
    if profile is None:
        return False
    skip = {"bid_id", "citations"}
    for name, value in profile.model_dump().items():
        if name in skip:
            continue
        if isinstance(value, str) and value.strip() and value.strip().lower() != "missing":
            return True
    return bool(profile.citations)


def normalize(text: str | None) -> str:
    return " ".join((text or "").casefold().split())


def verify_grounding(
    item: EvidenceItem,
    chunk_text: str | None = None,
    *,
    chunk_lookup: ChunkLookup | None = None,
    artifact_lookup: ArtifactLookup | None = None,
) -> bool:
    """Claim must literally appear in the cited chunk (normalized substring).

    Fail-closed: missing chunk text is not grounded. `not_stated` always passes.
    Callers grounding a whole bundle should pass batched/memoised lookups; the
    defaults hit DBSQL once per item, and `load_artifact_markdown` re-parses the
    artifact's entire JSON every time.
    """
    if item.status == "not_stated":
        return True
    if not item.claim_text:
        return False
    source = chunk_text
    if source is None:
        lookup = chunk_lookup or load_chunk_text
        if item.chunk_id:
            source = lookup(item.chunk_id)
    if source is None and item.artifact_id:
        artifacts = artifact_lookup or load_artifact_markdown
        source = artifacts(item.artifact_id)
    if source is None:
        return False
    return normalize(item.claim_text) in normalize(source)


def load_artifact_markdown(artifact_id: str) -> str | None:
    import json

    from shared.db.models import Artifact

    if not artifact_id:
        return None
    with session_scope() as session:
        row = session.get(Artifact, artifact_id)
        if row is None or not row.parsed_json:
            return None
        try:
            payload = json.loads(row.parsed_json) if isinstance(row.parsed_json, str) else row.parsed_json
        except json.JSONDecodeError:
            return None
        if isinstance(payload, dict):
            return payload.get("markdown") or payload.get("text")
        return None


def apply_grounding_gate(
    item: EvidenceItem,
    chunk_text: str | None = None,
    *,
    project_id: str | None = None,
    chunk_lookup: ChunkLookup | None = None,
    artifact_lookup: ArtifactLookup | None = None,
    flag_sink: list[QualityFlag] | None = None,
) -> EvidenceItem:
    """Downgrade ungrounded items to unclear/0 and raise `ungrounded_claim`."""
    if verify_grounding(
        item,
        chunk_text,
        chunk_lookup=chunk_lookup,
        artifact_lookup=artifact_lookup,
    ):
        return _gate_thin_met(item, project_id=project_id, flag_sink=flag_sink)
    flagged = item.model_copy(update={"status": "unclear", "confidence": 0.0})
    if project_id:
        record_ungrounded_claim(project_id, item, sink=flag_sink)
    return flagged


def _gate_thin_met(
    item: EvidenceItem,
    *,
    project_id: str | None,
    flag_sink: list[QualityFlag] | None,
) -> EvidenceItem:
    """Downgrade a `met` backed by too little text to carry the verdict."""
    if item.status != "met":
        return item
    if len((item.claim_text or "").strip()) >= MIN_MET_CLAIM_CHARS:
        return item
    if project_id:
        record_thin_claim(project_id, item, sink=flag_sink)
    return item.model_copy(update={"status": "unclear", "confidence": 0.0})


def load_chunk_text(chunk_id: str) -> str | None:
    if not chunk_id:
        return None
    with session_scope() as session:
        row = session.get(Chunk, chunk_id)
        if row is None:
            return None
        return row.text


def load_chunk_texts(chunk_ids: Iterable[str]) -> dict[str, str]:
    """Fetch many chunks in one round trip.

    Calling `load_chunk_text` in a loop opens one DBSQL connection per chunk
    (NullPool), which blocks the event loop long enough that asyncio timeouts
    never fire. Batched so a bid with thousands of chunks cannot build an
    `IN (...)` list big enough to hit the statement size limit.
    """
    ids = [cid for cid in dict.fromkeys(chunk_ids) if cid]
    if not ids:
        return {}
    out: dict[str, str] = {}
    with session_scope() as session:
        for start in range(0, len(ids), CHUNK_FETCH_BATCH):
            rows = session.execute(
                select(Chunk.id, Chunk.text).where(
                    Chunk.id.in_(ids[start : start + CHUNK_FETCH_BATCH])
                )
            ).all()
            out.update({str(cid): (text or "") for cid, text in rows})
    return out


def record_thin_claim(
    project_id: str, item: EvidenceItem, *, sink: list[QualityFlag] | None = None
) -> QualityFlag:
    """Flag a `met` whose quote is too short to evidence the requirement."""
    flag = QualityFlag(
        id=str(uuid.uuid4()),
        project_id=project_id,
        artifact_id=item.artifact_id,
        kind=THIN_CLAIM_KIND,
        detail=(
            f"requirement={item.requirement_id} chunk={item.chunk_id or ''} "
            f"claim={normalize(item.claim_text)[:240]}"
        ),
        severity="high",
        created_at=utc_now_iso(),
    )
    if sink is not None:
        sink.append(flag)
        return flag
    with session_scope() as session:
        session.add(flag)
        session.flush()
        session.expunge(flag)
    return flag


def record_ungrounded_claim(
    project_id: str, item: EvidenceItem, *, sink: list[QualityFlag] | None = None
) -> QualityFlag:
    """Write the flag, or hand it to `sink` so a bundle can persist them together."""
    now = utc_now_iso()
    flag = QualityFlag(
        id=str(uuid.uuid4()),
        project_id=project_id,
        artifact_id=item.artifact_id,
        kind=UNGROUNDED_KIND,
        detail=(
            f"requirement={item.requirement_id} chunk={item.chunk_id or ''} "
            f"claim={normalize(item.claim_text)[:240]}"
        ),
        severity="high",
        created_at=now,
    )
    if sink is not None:
        sink.append(flag)
        return flag
    with session_scope() as session:
        session.add(flag)
        session.flush()
        session.expunge(flag)
    return flag
