"""Extraction schemas and the citation-or-abstain / grounding gate.

Accuracy is enforced here, not requested in the prompt. Closed status
vocabulary matches `evidence.status` CHECK (minus `extraction_failed`,
which is a post-processing persist state, not a model output).
"""

from __future__ import annotations

import os
import re
import uuid
from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select

from shared.db.connection import session_scope
from shared.db.models import Chunk, QualityFlag, utc_now_iso
from shared.logger_global import get_logger

log = get_logger(__name__, service="ai_brain")

EvidenceStatus = Literal["met", "partial", "not_offered", "not_stated", "unclear"]
UNGROUNDED_KIND = "ungrounded_claim"
# Grounding proves the quote is in the document, not that it answers the
# requirement: "€ 1.600" really was cited for "Certification published by
# 30 Nov". A fragment this short cannot carry a compliance verdict, so it goes
# to a human as unclear instead of crediting the vendor.
THIN_CLAIM_KIND = "thin_met_claim"
MIN_MET_CLAIM_CHARS = 25
# Grounding proves the quote came from the bid, never that it answers the
# question: "VAT will be charged separately" was cited as met for "Existing
# Etex relationship disclosed". A verdict that credits a bidder must share at
# least one distinguishing term with the requirement it claims to satisfy;
# otherwise the cell goes to a human as unclear.
MISALIGNED_KIND = "misaligned_claim"
ALIGNMENT_GATE_ENV = "MATE_ALIGNMENT_GATE"
_CREDITING_STATUSES = frozenset({"met", "partial"})
_MIN_KEY_TERM_DF = 3
# One shared word is coincidence: "code of conduct" was credited against "Two
# BIC codes in scope", and "Service Monitoring Assessment" against "Master
# Services Template". Corroboration means two distinct terms, or one term that
# binds a number to a label (A4, Q3, 16/02/2026) and so is hard to hit by
# accident. A bare number is not enough: every document in a 2026 tender says
# "2026", which would otherwise satisfy "Project start Aug/Sep 2026".
_MIN_ALIGNMENT_TERMS = 2
_TERM_STOPWORDS = frozenset(
    """
    a an the and or of for to in on at by with from as is are was were be been
    being this that these those it its we our you your they their he she his her
    will shall can could would should may might must per via not no any all each
    other others same such than then there here also more most both
    provide provided providing include including included ensure ensures
    use used using make makes made give given get gets
    etc eg ie vs re
    """.split()
)
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


class AlignmentVerdict(BaseModel):
    """Does one quote answer the requirement it was filed under."""

    requirement_id: str
    addresses: bool
    reason: str | None = None


class AlignmentReview(BaseModel):
    verdicts: list[AlignmentVerdict] = Field(default_factory=list)


class RequirementSource(BaseModel):
    """The tender's own wording for one requirement, or an abstention."""

    requirement_id: str
    passage: str | None = None
    artifact_id: str | None = None
    page: int | None = None

    @model_validator(mode="after")
    def passage_or_abstain(self) -> RequirementSource:
        if self.passage and not (self.artifact_id or "").strip():
            raise ValueError("a sourced passage must name the artifact it came from")
        return self


class RequirementSourceBundle(BaseModel):
    sources: list[RequirementSource] = Field(default_factory=list)


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


def _tokens(text: str | None) -> list[str]:
    return re.findall(r"[A-Za-z0-9][A-Za-z0-9/&.-]*", text or "")


def _stem(token: str) -> str:
    """Plural only. Under-stemming costs a review; over-stemming credits a bid."""
    t = token.casefold().strip(".-/&")
    if len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
        return t[:-1]
    return t


def _term_set(text: str | None) -> set[str]:
    """Hyphenated compounds contribute their parts too: `in-scope` reaches `scope`.

    Only hyphens are split. Breaking `/` or `.` apart would turn `16/02/2026`
    into a bare `2026` that matches any sentence mentioning the year.
    """
    out: set[str] = set()
    for token in _tokens(text):
        pieces = [token, *token.split("-")] if "-" in token else [token]
        out.update(_stem(piece) for piece in pieces)
    return {s for s in out if len(s) > 1 and s not in _TERM_STOPWORDS}


def requirement_key_terms(
    requirements: Mapping[str, tuple[str | None, str | None]],
) -> dict[str, frozenset[str]]:
    """Terms that identify one requirement rather than the tender as a whole.

    `etex`, `swift` and `2026` occur across most of the tender, so a claim
    containing them proves nothing about which requirement it answers.
    """
    per_requirement = {
        rid: _term_set(text) | _term_set(section)
        for rid, (text, section) in requirements.items()
    }
    df: Counter[str] = Counter()
    for terms in per_requirement.values():
        df.update(terms)
    ceiling = max(_MIN_KEY_TERM_DF, len(per_requirement) // 8)
    return {
        rid: frozenset(term for term in terms if df[term] <= ceiling)
        for rid, terms in per_requirement.items()
    }


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


# Cases are dicts so the caller can log them verbatim; the verifier returns one
# boolean per case, in order.
AlignmentVerifier = Callable[[list[dict[str, str]]], list[bool]]


def apply_alignment_pass(
    items: list[EvidenceItem],
    requirements: Mapping[str, tuple[str | None, str | None]],
    *,
    project_id: str | None = None,
    verifier: AlignmentVerifier | None = None,
    flag_sink: list[QualityFlag] | None = None,
) -> list[EvidenceItem]:
    """Drop verdicts whose quote does not answer the requirement it was filed under.

    Asking whether one quote answers one requirement is a far narrower job than
    finding evidence for forty of them, so a model can be trusted with it where
    it could not be trusted with the extraction. Word overlap cannot: a bidder
    writing "sustainability rating" instead of "EcoVadis" answers R37 and shares
    no term with it. Overlap stays as the fallback for when no verifier is
    reachable, because failing closed costs a review and failing open costs a
    procurement decision.
    """
    if not alignment_gate_enabled():
        return items
    key_terms = requirement_key_terms(requirements)
    targets = [
        idx for idx, item in enumerate(items) if item.status in _CREDITING_STATUSES
    ]
    if not targets:
        return items

    verdicts: list[bool] | None = None
    if verifier is not None:
        cases = [
            {
                "requirement_id": items[idx].requirement_id,
                "requirement": (requirements.get(items[idx].requirement_id) or ("", ""))[0] or "",
                "target": (requirements.get(items[idx].requirement_id) or ("", ""))[1] or "",
                "claim": items[idx].claim_text or "",
            }
            for idx in targets
        ]
        try:
            reviewed = list(verifier(cases))
        except Exception as exc:  # noqa: BLE001 - a dead verifier must not void a build
            log.warning("alignment verifier unavailable, using term overlap: {}", exc)
            reviewed = None
        if reviewed is None:
            verdicts = None
        elif len(reviewed) == len(targets):
            verdicts = reviewed
        else:
            log.warning(
                "alignment verifier reviewed {} of {} claims; using term overlap",
                len(reviewed),
                len(targets),
            )
            verdicts = None

    out = list(items)
    for position, idx in enumerate(targets):
        item = items[idx]
        if verdicts is not None:
            aligned = bool(verdicts[position])
        else:
            aligned = (
                _gate_alignment(item, key_terms, project_id=None, flag_sink=None).status
                == item.status
            )
        if aligned:
            continue
        if project_id:
            record_misaligned_claim(
                project_id,
                item,
                sorted(key_terms.get(item.requirement_id, frozenset()))[:8],
                sink=flag_sink,
            )
        out[idx] = item.model_copy(update={"status": "unclear", "confidence": 0.0})
    return out


def alignment_gate_enabled() -> bool:
    return os.getenv(ALIGNMENT_GATE_ENV, "1").strip().lower() not in {"0", "false", "no"}


def _binds_a_number(term: str) -> bool:
    """A digit tied to a label or separator, not a standalone figure."""
    return any(c.isdigit() for c in term) and not term.isdigit()


def _gate_alignment(
    item: EvidenceItem,
    key_terms: Mapping[str, frozenset[str]] | None,
    *,
    project_id: str | None,
    flag_sink: list[QualityFlag] | None,
) -> EvidenceItem:
    """Downgrade a crediting verdict whose quote never mentions the requirement."""
    if item.status not in _CREDITING_STATUSES or not key_terms:
        return item
    if not alignment_gate_enabled():
        return item
    terms = key_terms.get(item.requirement_id)
    # No distinguishing term exists for this requirement, so nothing to test
    # against; abstaining here keeps the gate from punishing generic wording.
    if not terms:
        return item
    hits = _term_set(item.claim_text) & terms
    if len(hits) >= _MIN_ALIGNMENT_TERMS or any(_binds_a_number(hit) for hit in hits):
        return item
    if project_id:
        record_misaligned_claim(project_id, item, sorted(terms)[:8], sink=flag_sink)
    return item.model_copy(update={"status": "unclear", "confidence": 0.0})


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


def record_misaligned_claim(
    project_id: str,
    item: EvidenceItem,
    expected_terms: list[str],
    *,
    sink: list[QualityFlag] | None = None,
) -> QualityFlag:
    """Flag a crediting verdict whose quote never mentions the requirement."""
    flag = QualityFlag(
        id=str(uuid.uuid4()),
        project_id=project_id,
        artifact_id=item.artifact_id,
        kind=MISALIGNED_KIND,
        detail=(
            f"requirement={item.requirement_id} chunk={item.chunk_id or ''} "
            f"expected={','.join(expected_terms)} "
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
