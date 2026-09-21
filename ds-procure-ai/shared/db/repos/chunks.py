"""Chunk persistence for parsed artifacts."""

from __future__ import annotations

import json
import uuid
from typing import Any, Sequence

from sqlalchemy import delete, select

from shared.db.connection import session_scope
from shared.db.models import Artifact, Chunk, utc_now_iso


def replace_for_artifact(
    artifact_id: str,
    project_id: str,
    chunks: Sequence[Any],
) -> None:
    with session_scope() as session:
        session.execute(delete(Chunk).where(Chunk.artifact_id == artifact_id))
        for chunk in chunks:
            session.add(
                Chunk(
                    id=str(uuid.uuid4()),
                    project_id=project_id,
                    artifact_id=artifact_id,
                    ordinal=int(chunk.ordinal),
                    chunk_type=str(chunk.chunk_type),
                    text=str(chunk.text),
                    token_count=int(chunk.token_count),
                    heading_path_json=json.dumps(list(chunk.heading_path), ensure_ascii=False),
                    block_ids_json=json.dumps(list(chunk.block_ids), ensure_ascii=False),
                    location_json=json.dumps(dict(chunk.location), ensure_ascii=False),
                    table_json=getattr(chunk, "table_json", None),
                    page_kind=getattr(chunk, "page_kind", None),
                    reconstructor=getattr(chunk, "reconstructor", None),
                    created_at=utc_now_iso(),
                )
            )


def list_for_project(project_id: str) -> list[Chunk]:
    with session_scope() as session:
        superseded = select(Artifact.id).where(
            Artifact.project_id == project_id,
            Artifact.superseded_by.is_not(None),
        )
        rows = session.scalars(
            select(Chunk)
            .where(
                Chunk.project_id == project_id,
                # Retired revisions stay on disk for audit; retrieval must not
                # quote them back as current.
                Chunk.artifact_id.not_in(superseded),
            )
            .order_by(Chunk.artifact_id, Chunk.ordinal)
        ).all()
        for row in rows:
            session.expunge(row)
        return list(rows)


def list_for_artifact(artifact_id: str) -> list[Chunk]:
    with session_scope() as session:
        rows = session.scalars(
            select(Chunk)
            .where(Chunk.artifact_id == artifact_id)
            .order_by(Chunk.ordinal)
        ).all()
        for row in rows:
            session.expunge(row)
        return list(rows)
