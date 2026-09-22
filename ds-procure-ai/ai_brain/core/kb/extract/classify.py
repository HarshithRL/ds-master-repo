"""Vendor/bid classifier: fast model, structured output, then human confirm.

Filenames can name the buyer rather than the bidder. The confirm endpoint pins
artifact.vendor_id (the *bid* id) and doc_role. Consortium bids keep one bid id
and multiple legal entities — graph membership is W7.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from shared.db.connection import session_scope
from shared.db.models import Artifact, Vendor, utc_now_iso

DOC_ROLES = ("rfp", "proposal", "pricing", "registry", "csr", "reference")
DocRole = Literal["rfp", "proposal", "pricing", "registry", "csr", "reference", "note"]


class LegalEntity(BaseModel):
    name: str
    registry_id: str | None = None


class BidClassification(BaseModel):
    bid_id: str
    bid_label: str
    doc_role: DocRole
    entities: list[LegalEntity] = Field(min_length=1)
    confidence: float = 0.0
    role_confidence: float = 0.0

    @field_validator("bid_id")
    @classmethod
    def _slug_bid(cls, value: str) -> str:
        slug = _slug(value)
        if not slug:
            raise ValueError("bid_id is required")
        return slug


InvokeFn = Callable[[str], BidClassification]

# Filename → bid slug. Heuristics first; LLM only when this returns None.
_FILENAME_BIDS: tuple[tuple[tuple[str, ...], str, str, str], ...] = (
    (("trifinance", "inetum", "tf inetum"), "trifinance-inetum", "TriFinance + Inetum", "proposal"),
    (("kpmg",), "kpmg", "KPMG", "proposal"),
    (("pwc",), "pwc", "PwC", "proposal"),
    (("ey",), "ey", "EY", "proposal"),
    (("bdo",), "bdo", "BDO", "proposal"),
)

# "<Vendor> Response to ... RFP.pdf" is a bid, not the buyer's tender document.
_RESPONSE_MARKERS = ("response", "reply", "submission", "proposal", "offer", "quote")


def classify_from_filename(filename: str) -> BidClassification | None:
    """High-confidence identity from the filename. None → call the fast model."""
    name = (filename or "").lower()
    if (
        "rfp" in name
        and not any(
            token in name
            for token in ("kpmg", "pwc", "ey", "bdo", "inetum", "trifinance")
        )
        and not any(marker in name for marker in _RESPONSE_MARKERS)
    ):
        return BidClassification(
            bid_id="rfp",
            bid_label="RFP",
            doc_role="rfp",
            entities=[LegalEntity(name="Buyer")],
            confidence=0.95,
            role_confidence=0.98,
        )
    role: DocRole = "proposal"
    if "csr" in name or "ecovadis" in name:
        role = "csr"
    elif "pric" in name or "rate card" in name or "commercial" in name:
        role = "pricing"
    elif "registry" in name or "kbo" in name or "be-x-" in name:
        role = "registry"
    for needles, bid_id, label, default_role in _FILENAME_BIDS:
        if any(needle in name for needle in needles):
            entity_name = label.split("+")[0].strip() if "+" in label else label
            entities = [LegalEntity(name=part.strip()) for part in label.split("+")]
            if not entities:
                entities = [LegalEntity(name=entity_name)]
            use_role: DocRole = role if role != "proposal" else default_role  # type: ignore[assignment]
            if "csr" in name:
                use_role = "csr"
            return BidClassification(
                bid_id=bid_id,
                bid_label=label,
                doc_role=use_role,
                entities=entities,
                confidence=0.92,
                role_confidence=0.9,
            )
    if "independent assessment" in name and "swift" in name:
        return BidClassification(
            bid_id="bdo",
            bid_label="BDO",
            doc_role="proposal",
            entities=[LegalEntity(name="BDO")],
            confidence=0.85,
            role_confidence=0.8,
        )
    return None


STEM_FALLBACK_CONFIDENCE = 0.4


def classify_from_stem(filename: str) -> BidClassification | None:
    """Last-resort bid id from the filename stem so kb_build always has a column."""
    stem = Path(filename or "").stem
    slug = _slug(stem)
    if not slug:
        return None
    label = " ".join(stem.replace("_", " ").replace("-", " ").split()) or slug
    return BidClassification(
        bid_id=slug,
        bid_label=label,
        doc_role="proposal",
        entities=[LegalEntity(name=label)],
        confidence=STEM_FALLBACK_CONFIDENCE,
        role_confidence=STEM_FALLBACK_CONFIDENCE,
    )


def classify_and_pin(
    project_id: str,
    artifact_id: str,
    filename: str,
    *,
    snippets: list[str] | None = None,
    known_bids: list[str] | None = None,
) -> dict[str, object] | None:
    """Filename heuristic, then optional LLM, then filename-stem bid. Always pin."""
    classification = classify_from_filename(filename)
    if classification is None:
        body = [s for s in (snippets or []) if s.strip()] or [filename]
        try:
            classification = classify_snippets(filename, body, known_bids=known_bids)
        except Exception:
            classification = None
    if classification is None:
        classification = classify_from_stem(filename)
    if classification is None:
        return None
    return confirm_classification(project_id, artifact_id, classification)


# Automated pins are clamped below this, so the value only ever means "a person
# chose this" and no later re-classification may overwrite it.
MANUAL_PIN_CONFIDENCE = 1.0
_MAX_AUTO_CONFIDENCE = 0.99


def set_vendor_manually(
    project_id: str,
    artifact_id: str,
    bid_id: str,
    *,
    bid_label: str | None = None,
    doc_role: str | None = None,
) -> dict[str, object]:
    """Pin a bidder chosen by a person and mark the knowledge base stale.

    created_at is refreshed because _staleness compares it against the last kb
    build; the file itself did not change but its meaning for the matrix did.
    """
    slug = _slug(bid_id)
    if not slug:
        raise ValueError("bid_id is required")
    role = (doc_role or "").strip().lower()
    if role and role not in DOC_ROLES:
        raise ValueError(f"unknown doc_role: {doc_role}")
    label = (bid_label or "").strip() or slug
    now = utc_now_iso()
    with session_scope() as session:
        artifact = session.get(Artifact, artifact_id)
        if artifact is None or artifact.project_id != project_id:
            raise LookupError(artifact_id)
        artifact.vendor_id = slug
        artifact.doc_role = role or artifact.doc_role or "proposal"
        artifact.role_confidence = MANUAL_PIN_CONFIDENCE
        artifact.created_at = now
        vendor_id = f"{project_id}:{slug}"
        if session.get(Vendor, vendor_id) is None:
            session.add(
                Vendor(
                    id=vendor_id,
                    project_id=project_id,
                    name=label,
                    legal_entity=label,
                    status="bidder",
                    created_at=now,
                )
            )
        session.flush()
        out = {
            "artifact_id": artifact_id,
            "vendor_id": slug,
            "doc_role": artifact.doc_role,
            "manual": True,
        }
    _clear_unresolved_flag(artifact_id)
    return out


def _clear_unresolved_flag(artifact_id: str) -> None:
    from sqlalchemy import delete

    from shared.db.models import QualityFlag

    try:
        with session_scope() as session:
            session.execute(
                delete(QualityFlag).where(
                    QualityFlag.artifact_id == artifact_id,
                    QualityFlag.kind == "vendor_unresolved",
                )
            )
    except Exception:
        pass


def artifact_snippets(artifact_id: str, limit: int = 6) -> list[str]:
    """Opening chunks of a parsed artifact — letterheads and signature blocks
    name the bidder far more reliably than the filename does."""
    from shared.db.models import Chunk

    with session_scope() as session:
        rows = session.execute(
            select(Chunk.text)
            .where(Chunk.artifact_id == artifact_id)
            .order_by(Chunk.ordinal)
            .limit(limit)
        ).all()
        out = [str(r[0] or "").strip() for r in rows if (r[0] or "").strip()]
        if out:
            return out
        # Chunk writes fail independently of parsing (row-level Delta conflicts,
        # oversized statements), so parsed_json is often still populated.
        artifact = session.get(Artifact, artifact_id)
        raw = getattr(artifact, "parsed_json", None) if artifact is not None else None
    return _parsed_json_snippets(raw, limit)


def _parsed_json_snippets(raw: object, limit: int) -> list[str]:
    if not raw:
        return []
    data = raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except ValueError:
            return []
    text = ""
    if isinstance(data, dict):
        text = str(data.get("markdown") or data.get("text") or "")
    elif isinstance(data, str):
        text = data
    text = text.strip()
    if not text:
        return []
    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
    return blocks[:limit] if blocks else [text[:1000]]


def classify_snippets(
    filename: str,
    snippets: list[str],
    *,
    known_bids: list[str] | None = None,
    invoke: InvokeFn | None = None,
) -> BidClassification:
    """Fast-model structured classification. Tests inject `invoke` (no live LLM)."""
    prompt = _classifier_prompt(filename, snippets, known_bids=known_bids)
    fn = invoke or _live_invoke
    return fn(prompt)


def confirm_classification(
    project_id: str,
    artifact_id: str,
    classification: BidClassification,
) -> dict[str, object]:
    """Pin vendor_id (bid) + doc_role; upsert legal-entity vendor rows."""
    now = utc_now_iso()
    with session_scope() as session:
        artifact = session.get(Artifact, artifact_id)
        if artifact is None or artifact.project_id != project_id:
            raise LookupError(artifact_id)
        # A person outranks every later automated pass, and the check lives here
        # so it shares the write's transaction instead of racing a second query.
        if float(artifact.role_confidence or 0.0) >= MANUAL_PIN_CONFIDENCE:
            return {
                "artifact_id": artifact_id,
                "vendor_id": artifact.vendor_id,
                "doc_role": artifact.doc_role,
                "manual": True,
                "vendors": [],
            }
        artifact.doc_role = classification.doc_role
        artifact.role_confidence = min(
            classification.role_confidence or classification.confidence,
            _MAX_AUTO_CONFIDENCE,
        )
        if classification.doc_role == "rfp":
            artifact.vendor_id = None
            session.flush()
            return {
                "artifact_id": artifact_id,
                "vendor_id": None,
                "doc_role": "rfp",
                "vendors": [],
            }
        artifact.vendor_id = classification.bid_id
        vendors_out: list[dict[str, str | None]] = []
        for entity in classification.entities:
            vendor_id = f"{project_id}:{_slug(entity.registry_id or entity.name)}"
            existing = session.get(Vendor, vendor_id)
            if existing is None:
                session.add(
                    Vendor(
                        id=vendor_id,
                        project_id=project_id,
                        name=entity.name,
                        legal_entity=entity.name,
                        registry_id=entity.registry_id,
                        status="bidder",
                        created_at=now,
                    )
                )
            else:
                existing.name = entity.name
                existing.legal_entity = entity.name
                existing.registry_id = entity.registry_id
            vendors_out.append(
                {"id": vendor_id, "name": entity.name, "registry_id": entity.registry_id}
            )
        session.flush()
        return {
            "artifact_id": artifact_id,
            "vendor_id": classification.bid_id,
            "doc_role": classification.doc_role,
            "vendors": vendors_out,
        }


def roster_names(project_id: str) -> list[str]:
    with session_scope() as session:
        rows = session.scalars(select(Vendor).where(Vendor.project_id == project_id)).all()
        return sorted({row.name for row in rows})


def _classifier_prompt(
    filename: str, snippets: list[str], known_bids: list[str] | None = None
) -> str:
    body = "\n".join(snippets[:8])[:4000]
    known = ""
    if known_bids:
        known = (
            "bid_id values already used in this project: "
            + ", ".join(sorted(set(known_bids)))
            + "\nReuse one of them verbatim when this file comes from the same "
            "bidder; only invent a new bid_id for a genuinely different one.\n"
        )
    return (
        "Classify this procurement artifact.\n"
        "Return bid_id (stable slug), bid_label, doc_role, and legal entities.\n"
        "Do not trust the filename alone; filenames may describe the buyer, not the bidder.\n"
        "Consortium bids: one bid_id, multiple entities.\n"
        + known
        + f"filename: {filename}\n"
        f"snippets:\n{body}\n"
    )


def _live_invoke(prompt: str) -> BidClassification:
    from ai_brain.core.config.llm import get_fast_llm

    llm = get_fast_llm().with_structured_output(BidClassification)
    return BidClassification.model_validate(llm.invoke(prompt))


def _slug(value: str) -> str:
    chars: list[str] = []
    prev_dash = False
    for char in (value or "").strip().lower():
        if char.isalnum():
            chars.append(char)
            prev_dash = False
        elif not prev_dash:
            chars.append("-")
            prev_dash = True
    return "".join(chars).strip("-")
