"""Parse uploaded artifacts and persist ArtifactDocument JSON."""

from __future__ import annotations

import json
from typing import Any

from shared.artifacts import ArtifactHandler
from shared.artifacts.exceptions import ArtifactError, UnsupportedArtifact
from shared.db.models import Artifact
from shared.db.paths import artifact_absolute_path, parsed_storage_relpath
from shared.db.repos import artifacts as artifact_repo
from shared.db.repos import chunks as chunk_repo
from shared.logger_global import get_logger

log = get_logger(__name__)

PARSE_OK = "ok"
PARSE_ERROR = "error"
PARSE_SKIPPED = "skipped"


def parse_and_store(artifact: Artifact, *, force: bool = False) -> Artifact:
    # Two independent callers reach this for the same artifact (the upload
    # route's ingest pipeline and ai_brain's ingest fanout). Re-running Azure
    # Document Intelligence produces an identical result at full cost/latency.
    if not force and (getattr(artifact, "parse_status", "") or "") == PARSE_OK:
        log.info(
            "artifact parse skipped (already parsed) artifact_id={} name={}",
            artifact.id,
            artifact.original_name,
        )
        return artifact

    source_path = artifact_absolute_path(artifact.storage_relpath)
    try:
        from shared.db.volume_fs import read_bytes as vol_read_bytes
        source_bytes = vol_read_bytes(source_path)
        document = ArtifactHandler().parse(source_bytes, filename=artifact.original_name)
    except UnsupportedArtifact as exc:
        log.info(
            "artifact parse skipped artifact_id={} name={} detail={}",
            artifact.id,
            artifact.original_name,
            str(exc),
        )
        return _store_parse_failure(artifact, PARSE_SKIPPED, str(exc))
    except ArtifactError as exc:
        log.warning(
            "artifact parse failed artifact_id={} name={} detail={}",
            artifact.id,
            artifact.original_name,
            str(exc),
        )
        return _store_parse_failure(artifact, PARSE_ERROR, str(exc))
    except Exception as exc:
        log.exception(
            "artifact parse crashed artifact_id={} name={}",
            artifact.id,
            artifact.original_name,
        )
        return _store_parse_failure(artifact, PARSE_ERROR, str(exc))

    log.info(
        "artifact stored parser={} artifact_id={} name={} blocks={}",
        document.parser or "unknown",
        artifact.id,
        artifact.original_name,
        len(document.blocks),
    )
    payload: dict[str, Any] = document.to_dict()
    markdown = str(payload.get("markdown") or "").strip()
    chunks = list(getattr(document, "chunks", None) or [])
    if not markdown or not chunks:
        detail = (
            "parse produced empty markdown"
            if not markdown
            else "parse produced no chunks"
        )
        log.warning(
            "artifact parse empty content artifact_id={} name={} detail={}",
            artifact.id,
            artifact.original_name,
            detail,
        )
        return _store_parse_failure(artifact, PARSE_ERROR, detail)
    
    relpath = parsed_storage_relpath(artifact.project_id, artifact.id)
    absolute = artifact_absolute_path(relpath)
    
    from shared.db.volume_fs import ensure_dir, write_text as vol_write_text

    serialized = json.dumps(payload, ensure_ascii=False)
    ensure_dir(absolute.parent)
    vol_write_text(absolute, serialized)
    vol_write_text(absolute.with_suffix(".md"), markdown)
    saved = artifact_repo.save_parse_result(
        artifact.id,
        parse_status=PARSE_OK,
        parsed_json=_inline_parsed_json(serialized, markdown),
        parsed_relpath=relpath,
        parse_error=None,
    )
    _replace_chunks(saved, chunks)
    return saved


# DBSQL rejects oversized statement parameters, which failed the whole parse of
# large files even though the volume copy had already been written.
INLINE_PARSED_JSON_LIMIT = 900_000


def _inline_parsed_json(serialized: str, markdown: str) -> str:
    """Full payload when it fits, else enough markdown to keep readers working.

    parsed_relpath still points at the complete document on the volume, and an
    empty column here would make the reparse check treat the file as unparsed.
    """
    if len(serialized) <= INLINE_PARSED_JSON_LIMIT:
        return serialized
    budget = max(0, INLINE_PARSED_JSON_LIMIT - 512)
    trimmed = json.dumps(
        {"markdown": markdown[:budget], "truncated": True}, ensure_ascii=False
    )
    log.warning(
        "parsed_json too large for inline storage bytes={} kept={} relpath_has_full=1",
        len(serialized),
        len(trimmed),
    )
    return trimmed


def _store_parse_failure(artifact: Artifact, parse_status: str, parse_error: str) -> Artifact:
    _replace_chunks(artifact, [])
    return artifact_repo.save_parse_result(
        artifact.id,
        parse_status=parse_status,
        parse_error=parse_error,
    )


def _replace_chunks(artifact: Artifact, chunks: list[Any]) -> None:
    chunk_repo.replace_for_artifact(artifact.id, artifact.project_id, chunks)
