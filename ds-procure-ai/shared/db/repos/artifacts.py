"""Artifact CRUD and file storage."""

from __future__ import annotations

import hashlib
import mimetypes
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from shared.db.connection import session_scope
from shared.db.models import Artifact, utc_now_iso
from shared.db.paths import artifact_absolute_path, artifact_storage_relpath
from shared.db.volume_fs import write_bytes
from shared.db.repos.projects import ProjectNotFoundError, _get_for_owner
from shared.db.seed import PROCUREMENT_MODULE_ID
from shared.logger_global import get_logger

log = get_logger(__name__)

FOLDER_VENDOR = "vendor_documents"
FOLDER_REQUIREMENTS = "requirements"
FOLDER_AI_GENERATED = "ai_generated"

FOLDER_TITLES = {
    FOLDER_VENDOR: "Vendor Documents",
    FOLDER_REQUIREMENTS: "Requirements",
    FOLDER_AI_GENERATED: "AI Generated",
}


@dataclass(frozen=True)
class UploadFile:
    filename: str
    stream: BinaryIO
    content_type: str | None = None


class ArtifactNotFoundError(LookupError):
    pass


def create_upload(
    project_id: str,
    owner_id: str,
    upload: UploadFile,
    *,
    folder: str = FOLDER_VENDOR,
    module_id: str = PROCUREMENT_MODULE_ID,
) -> Artifact:
    original_name = Path(upload.filename or "file").name
    if not original_name:
        raise ValueError("filename is required")

    artifact_id = str(uuid.uuid4())
    relpath = artifact_storage_relpath(project_id, artifact_id, original_name)
    absolute = artifact_absolute_path(relpath)
    upload.stream.seek(0)
    data = upload.stream.read()
    write_bytes(absolute, data)
    size_bytes = len(data)
    content_hash = hashlib.sha256(data).hexdigest()
    content_type = upload.content_type or mimetypes.guess_type(original_name)[0]

    with session_scope() as session:
        project = _get_for_owner(session, project_id, owner_id, module_id=module_id)
        if project is None:
            raise ProjectNotFoundError(project_id)

        # A re-upload of the same document is a new revision: retire the old one
        # so extraction never sees last round's prices next to this round's.
        previous = session.scalars(
            select(Artifact).where(
                Artifact.project_id == project_id,
                Artifact.superseded_by.is_(None),
                or_(
                    Artifact.original_name == original_name,
                    Artifact.content_hash == content_hash,
                ),
            )
        ).all()

        artifact = Artifact(
            id=artifact_id,
            project_id=project_id,
            uploaded_by=owner_id,
            kind="upload",
            folder=folder,
            original_name=original_name,
            content_type=content_type,
            size_bytes=size_bytes,
            storage_relpath=relpath,
            content_hash=content_hash,
            parse_status="pending",
            created_at=utc_now_iso(),
        )
        session.add(artifact)
        for old in previous:
            old.superseded_by = artifact_id
            log.info(
                "artifact superseded project_id={} old={} by={} name={}",
                project_id,
                old.id,
                artifact_id,
                original_name,
            )
        session.flush()
        session.expunge(artifact)
        return artifact


# Sentinel: omit parsed_json / parsed_relpath so callers do not wipe existing blobs.
_UNSET = object()


def save_parse_result(
    artifact_id: str,
    *,
    parse_status: str,
    parse_error: str | None = None,
    parsed_json: str | None | object = _UNSET,
    parsed_relpath: str | None | object = _UNSET,
) -> Artifact:
    with session_scope() as session:
        artifact = session.get(Artifact, artifact_id)
        if artifact is None:
            raise ArtifactNotFoundError(artifact_id)
        artifact.parse_status = parse_status
        artifact.parse_error = parse_error
        if parsed_json is not _UNSET:
            artifact.parsed_json = parsed_json  # type: ignore[assignment]
        if parsed_relpath is not _UNSET:
            artifact.parsed_relpath = parsed_relpath  # type: ignore[assignment]
        session.flush()
        session.expunge(artifact)
        return artifact


def create_uploads(
    project_id: str,
    owner_id: str,
    uploads: list[UploadFile],
    *,
    folder: str = FOLDER_VENDOR,
    module_id: str = PROCUREMENT_MODULE_ID,
) -> list[Artifact]:
    return [
        create_upload(project_id, owner_id, upload, folder=folder, module_id=module_id)
        for upload in uploads
    ]


def list_for_project(
    project_id: str,
    owner_id: str,
    *,
    module_id: str = PROCUREMENT_MODULE_ID,
) -> list[Artifact]:
    with session_scope() as session:
        project = _get_for_owner(session, project_id, owner_id, module_id=module_id)
        if project is None:
            raise ProjectNotFoundError(project_id)
        rows = session.scalars(
            select(Artifact)
            .where(Artifact.project_id == project_id)
            .order_by(Artifact.created_at.desc())
        ).all()
        for row in rows:
            session.expunge(row)
        return list(rows)


def delete_for_owner(
    artifact_id: str,
    owner_id: str,
    *,
    module_id: str = PROCUREMENT_MODULE_ID,
) -> None:
    with session_scope() as session:
        artifact = session.scalar(
            select(Artifact)
            .options(joinedload(Artifact.project))
            .where(Artifact.id == artifact_id)
        )
        if artifact is None or artifact.project is None:
            raise ArtifactNotFoundError(artifact_id)
        if artifact.project.owner_id != owner_id or artifact.project.module_id != module_id:
            raise ArtifactNotFoundError(artifact_id)

        relpath = artifact.storage_relpath
        parsed_relpath = artifact.parsed_relpath
        session.delete(artifact)
        session.flush()

    absolute = artifact_absolute_path(relpath)
    if absolute.exists():
        absolute.unlink(missing_ok=True)
    if parsed_relpath:
        parsed_path = artifact_absolute_path(parsed_relpath)
        if parsed_path.exists():
            parsed_path.unlink(missing_ok=True)


def total_bytes_for_project(project_id: str) -> int:
    with session_scope() as session:
        rows = session.scalars(
            select(Artifact.size_bytes).where(Artifact.project_id == project_id)
        ).all()
        return sum(int(size or 0) for size in rows)


def artifact_file_type(name: str) -> str:
    suffix = Path(name).suffix.lower().lstrip(".")
    return suffix or "file"


def format_file_meta(size_bytes: int | None, created_at: str | None) -> str:
    size_label = _format_size(size_bytes or 0)
    date_label = _format_short_datetime(created_at)
    return f"{size_label} • {date_label}"


def _format_size(size_bytes: int) -> str:
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.0f} KB"
    return f"{size_bytes} B"


def _format_short_datetime(iso_value: str | None) -> str:
    if not iso_value:
        return "—"
    date_part = iso_value[:10]
    try:
        year, month, day = date_part.split("-")
        months = [
            "Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
        ]
        return f"{months[int(month) - 1]} {int(day)}, {year}"
    except (ValueError, IndexError):
        return date_part
