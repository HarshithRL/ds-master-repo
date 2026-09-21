"""Analyst notes as extraction corpus.

Notes carry judgement the uploaded documents cannot supply — a reference call,
why a cheaper bid was rejected. They live in `mate_note`, which the extraction
pipeline never reads, so each note is mirrored into a per-bid artifact plus one
chunk. Every chunk states its provenance, so an analyst note can never be read
back as something the vendor itself claimed.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import delete as sa_delete
from sqlalchemy import select

from shared.db.connection import session_scope
from shared.db.models import Artifact, Chunk, Project, utc_now_iso
from shared.db.repos.notes import VENDOR_STATEMENT
from shared.logger_global import get_logger

log = get_logger(__name__, service="ai_brain")

NOTE_DOC_ROLE = "note"
NOTE_ARTIFACT_KIND = "note"


def _artifact_id(project_id: str, bid_id: str | None) -> str:
    return f"{project_id}:notes:{bid_id or 'project'}"


def _artifact_name(bid_id: str | None) -> str:
    return f"Analyst notes — {bid_id}.md" if bid_id else "Analyst notes — project.md"


def _chunk_text(note: dict[str, Any]) -> str:
    who = (note.get("author") or "").strip() or "an analyst"
    when = (note.get("created_at") or "")[:10]
    scope = note.get("bid_id") or "the project"
    stamp = f" on {when}" if when else ""
    body = (note.get("body") or "").strip()
    # Relayed vendor correspondence must not be read back as our own judgement,
    # and our judgement must never be read back as a vendor commitment.
    if (note.get("kind") or "") == VENDOR_STATEMENT and note.get("bid_id"):
        return (
            f"VENDOR STATEMENT from {scope}, relayed by {who}{stamp}.\n"
            "Correspondence the buying team received from this vendor, such as an "
            "email or call minutes. Treat it as the vendor's own words.\n\n"
            f"{body}"
        )
    return (
        f"ANALYST NOTE ({note.get('kind') or 'note'}) about {scope}, "
        f"recorded by {who}{stamp}.\n"
        "This is the buying team's own judgement, not a statement made by the vendor.\n\n"
        f"{body}"
    )


def materialize_notes(project_id: str) -> int:
    """Mirror notes into artifacts + chunks. Returns the chunk count written."""
    if not project_id:
        return 0
    from shared.db.repos import notes as note_repo

    try:
        notes = note_repo.list_for_project(project_id)
    except Exception:
        log.exception("notes read failed project_id={}", project_id)
        return 0

    by_bid: dict[str | None, list[dict[str, Any]]] = {}
    for note in notes:
        by_bid.setdefault(note.get("bid_id") or None, []).append(note)

    written = 0
    now = utc_now_iso()
    with session_scope() as session:
        project = session.get(Project, project_id)
        if project is None:
            return 0
        keep = {_artifact_id(project_id, bid) for bid in by_bid}

        # Drop mirrors whose notes were all deleted.
        stale = [
            row
            for row in session.scalars(
                select(Artifact).where(
                    Artifact.project_id == project_id,
                    Artifact.kind == NOTE_ARTIFACT_KIND,
                )
            ).all()
            if row.id not in keep
        ]
        for row in stale:
            session.execute(sa_delete(Chunk).where(Chunk.artifact_id == row.id))
            session.delete(row)

        for bid_id, bid_notes in by_bid.items():
            aid = _artifact_id(project_id, bid_id)
            artifact = session.get(Artifact, aid)
            if artifact is None:
                artifact = Artifact(
                    id=aid,
                    project_id=project_id,
                    uploaded_by=project.owner_id,
                    kind=NOTE_ARTIFACT_KIND,
                    folder="vendor",
                    original_name=_artifact_name(bid_id),
                    storage_relpath=f"notes/{bid_id or 'project'}.md",
                    created_at=now,
                )
                session.add(artifact)
            artifact.vendor_id = bid_id
            artifact.doc_role = NOTE_DOC_ROLE
            artifact.parse_status = "ok"
            artifact.parse_error = None
            # This mirror is rewritten on every note edit, and staleness checks
            # compare input timestamps against the last build.
            artifact.created_at = now

            # Rewritten wholesale: notes are edited and deleted in place.
            session.execute(sa_delete(Chunk).where(Chunk.artifact_id == aid))
            texts: list[str] = []
            for ordinal, note in enumerate(sorted(bid_notes, key=lambda n: n.get("created_at") or "")):
                text = _chunk_text(note)
                texts.append(text)
                session.add(
                    Chunk(
                        id=str(uuid.uuid4()),
                        project_id=project_id,
                        artifact_id=aid,
                        ordinal=ordinal,
                        chunk_type="text",
                        text=text,
                        token_count=max(1, len(text) // 4),
                    )
                )
                written += 1
            # The extraction corpus is rendered from parsed_json. Without it the
            # note lands in _quality/ as "no usable markdown" and the vendor
            # analyst never reads it.
            artifact.parsed_json = json.dumps({"markdown": "\n\n---\n\n".join(texts)})
        session.flush()

    log.info("notes materialized project_id={} chunks={}", project_id, written)
    return written
