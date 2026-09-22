"""Load project files for pack/insight nodes. Tools wrap shared/db — graph nodes do not open sqlite themselves beyond repos."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from shared.db.connection import session_scope
from shared.db.models import Artifact, Project
from shared.db.repos import chunks as chunk_repo


def load_project(project_id: str) -> Project | None:
    if not project_id:
        return None
    with session_scope() as session:
        project = session.get(Project, project_id)
        if project is None:
            project = session.scalar(select(Project).where(Project.code == project_id))
        if project is None:
            return None
        session.expunge(project)
        return project


def load_artifacts(project_id: str) -> list[Artifact]:
    with session_scope() as session:
        rows = session.scalars(
            select(Artifact)
            .where(
                Artifact.project_id == project_id,
                # A re-upload retires the old revision. Extraction must not see
                # last round's prices next to this round's.
                Artifact.superseded_by.is_(None),
            )
            .order_by(Artifact.created_at.desc())
        ).all()
        for row in rows:
            session.expunge(row)
        return list(rows)


def load_context(project_id: str) -> tuple[Any, list[Any], list[Any]]:
    project = load_project(project_id)
    if project is None:
        return None, [], []
    artifacts = load_artifacts(project_id)
    chunks = chunk_repo.list_for_project(project_id)
    return project, artifacts, chunks
