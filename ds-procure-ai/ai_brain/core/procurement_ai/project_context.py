"""Load project files for pack/insight nodes. Tools wrap shared/db — graph nodes do not open sqlite themselves beyond repos."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.db.connection import session_scope
from shared.db.models import Artifact, Chunk, Project


def _project_in_session(session: Session, project_id: str) -> Project | None:
    project = session.get(Project, project_id)
    if project is None:
        project = session.scalar(select(Project).where(Project.code == project_id))
    return project


def load_project(project_id: str) -> Project | None:
    if not project_id:
        return None
    with session_scope() as session:
        project = _project_in_session(session, project_id)
        if project is None:
            return None
        session.expunge(project)
        return project


def load_artifacts(project_id: str) -> list[Artifact]:
    with session_scope() as session:
        rows = session.scalars(
            select(Artifact)
            .where(Artifact.project_id == project_id)
            .order_by(Artifact.created_at.desc())
        ).all()
        for row in rows:
            session.expunge(row)
        return list(rows)


def load_context(project_id: str) -> tuple[Any, list[Any], list[Any]]:
    """Load project, artifacts, and chunks in one warehouse session."""
    if not project_id:
        return None, [], []
    with session_scope() as session:
        project = _project_in_session(session, project_id)
        if project is None:
            return None, [], []
        pid = project.id
        artifacts = list(
            session.scalars(
                select(Artifact)
                .where(Artifact.project_id == pid)
                .order_by(Artifact.created_at.desc())
            ).all()
        )
        chunks = list(
            session.scalars(
                select(Chunk)
                .where(Chunk.project_id == pid)
                .order_by(Chunk.artifact_id, Chunk.ordinal)
            ).all()
        )
        session.expunge(project)
        for row in artifacts:
            session.expunge(row)
        for row in chunks:
            session.expunge(row)
        return project, artifacts, chunks
