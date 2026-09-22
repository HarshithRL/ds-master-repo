"""Analyst notes / decision log."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from shared.db.connection import session_scope
from shared.db.models import Note, utc_now_iso
from shared.logger_global import get_logger

log = get_logger(__name__)

# Correspondence the analyst relays from a vendor (email, call minutes). Kept
# apart from the other kinds because it is the vendor's voice, not ours.
VENDOR_STATEMENT = "vendor_statement"
KINDS = ("note", "risk", "decision", "question", VENDOR_STATEMENT)
SOURCES = ("manual", "chat", "artifact")


class NoteNotFoundError(LookupError):
    pass


def _to_dict(note: Note) -> dict[str, Any]:
    return {
        "id": note.id,
        "project_id": note.project_id,
        "bid_id": note.bid_id,
        "body": note.body,
        "kind": note.kind,
        "source": note.source,
        "author": note.author,
        "created_at": note.created_at,
        "updated_at": note.updated_at,
    }


def list_for_project(project_id: str, *, bid_id: str | None = None) -> list[dict[str, Any]]:
    with session_scope() as session:
        stmt = select(Note).where(Note.project_id == project_id)
        if bid_id is not None:
            stmt = stmt.where(Note.bid_id == bid_id)
        rows = session.scalars(stmt.order_by(Note.created_at.desc())).all()
        return [_to_dict(row) for row in rows]


def create(
    project_id: str,
    body: str,
    *,
    bid_id: str | None = None,
    kind: str = "note",
    source: str = "manual",
    author: str | None = None,
) -> dict[str, Any]:
    text = (body or "").strip()
    if not text:
        raise ValueError("note body is required")
    now = utc_now_iso()
    note = Note(
        id=uuid.uuid4().hex,
        project_id=project_id,
        bid_id=(bid_id or None),
        body=text,
        kind=kind if kind in KINDS else "note",
        source=source if source in SOURCES else "manual",
        author=author,
        created_at=now,
        updated_at=now,
    )
    with session_scope() as session:
        session.add(note)
        session.flush()
        return _to_dict(note)


def update(project_id: str, note_id: str, body: str) -> dict[str, Any]:
    text = (body or "").strip()
    if not text:
        raise ValueError("note body is required")
    with session_scope() as session:
        note = session.get(Note, note_id)
        if note is None or note.project_id != project_id:
            raise NoteNotFoundError(note_id)
        note.body = text
        note.updated_at = utc_now_iso()
        session.flush()
        return _to_dict(note)


def delete(project_id: str, note_id: str) -> None:
    with session_scope() as session:
        note = session.get(Note, note_id)
        if note is None or note.project_id != project_id:
            raise NoteNotFoundError(note_id)
        session.delete(note)
