"""Parse-quality detectors. Pure functions over Artifact + ArtifactDocument."""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import delete, select

from shared.artifacts.chunking import estimate_tokens
from shared.artifacts.models import ArtifactDocument, BlockType
from shared.db.connection import session_scope
from shared.db.models import Artifact, QualityFlag, utc_now_iso

# Plan snippet used 2000, but the CSR example is ~559 bytes/token vs ~140 healthy.
# 2000 would not flag KPMG CSR (W3 gate). 400 flags CSR and other sparse visual decks.
LOW_YIELD_BYTES_PER_TOKEN = 400
IMAGE_DOMINANT_RATIO = 0.20
NO_STRUCTURE_MIN_BLOCKS = 50
DETECTOR_KINDS = ("low_yield", "image_dominant", "no_structure", "orphan_parse")


def run_quality_detectors(artifact: Artifact, doc: ArtifactDocument | None) -> list[dict[str, str]]:
    flags: list[dict[str, str]] = []
    parse_status = (artifact.parse_status or "").strip() or None
    if parse_status in (None, "pending") and not artifact.parsed_json:
        flags.append(
            {
                "kind": "orphan_parse",
                "detail": f"parse_status={parse_status or 'NULL'} with no parsed_json",
                "severity": "high",
            }
        )
        return flags
    if doc is None:
        return flags

    blocks = doc.blocks
    toks = sum(estimate_tokens(block.text or "") for block in blocks)
    size = int(artifact.size_bytes or 0)
    if size and toks and (size / toks) > LOW_YIELD_BYTES_PER_TOKEN:
        flags.append(
            {
                "kind": "low_yield",
                "detail": f"{size / toks:.0f} bytes/token",
                "severity": "high",
            }
        )
    imgs = sum(1 for block in blocks if block.type == BlockType.IMAGE)
    if blocks and imgs / len(blocks) > IMAGE_DOMINANT_RATIO:
        flags.append(
            {
                "kind": "image_dominant",
                "detail": f"{imgs}/{len(blocks)} blocks are images",
                "severity": "high",
            }
        )
    headings = any(block.type == BlockType.HEADING for block in blocks)
    if len(blocks) > NO_STRUCTURE_MIN_BLOCKS and not headings:
        flags.append(
            {
                "kind": "no_structure",
                "detail": "no headings in a large document",
                "severity": "medium",
            }
        )
    return flags


def persist_flags(project_id: str, artifact_id: str, flags: list[dict[str, str]]) -> list[QualityFlag]:
    now = utc_now_iso()
    saved: list[QualityFlag] = []
    with session_scope() as session:
        session.execute(
            delete(QualityFlag).where(
                QualityFlag.artifact_id == artifact_id,
                QualityFlag.kind.in_(DETECTOR_KINDS),
            )
        )
        for flag in flags:
            row = QualityFlag(
                id=str(uuid.uuid4()),
                project_id=project_id,
                artifact_id=artifact_id,
                kind=flag["kind"],
                detail=flag.get("detail"),
                severity=flag.get("severity"),
                created_at=now,
            )
            session.add(row)
            saved.append(row)
        session.flush()
        for row in saved:
            session.expunge(row)
    return saved


def document_from_artifact(artifact: Artifact) -> ArtifactDocument | None:
    if not artifact.parsed_json:
        return None
    return ArtifactDocument.from_dict(json.loads(artifact.parsed_json))


def scan_project(project_id: str) -> list[dict[str, Any]]:
    from ai_brain.core.procurement_ai.project_context import load_project

    project = load_project(project_id)
    if project is None:
        return []
    project_id = project.id
    results: list[dict[str, Any]] = []
    with session_scope() as session:
        artifacts = session.scalars(
            select(Artifact).where(Artifact.project_id == project_id)
        ).all()
        for row in artifacts:
            session.expunge(row)
        rows = list(artifacts)
    for artifact in rows:
        doc = document_from_artifact(artifact)
        flags = run_quality_detectors(artifact, doc)
        persist_flags(artifact.project_id, artifact.id, flags)
        for flag in flags:
            results.append(
                {
                    "artifact_id": artifact.id,
                    "original_name": artifact.original_name,
                    **flag,
                }
            )
    return results
