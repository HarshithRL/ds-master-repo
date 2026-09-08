"""W3 quality detectors and classifier fixtures (BDO, consortium, KPMG CSR)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from ai_brain.core.kb.classify import (
    BidClassification,
    LegalEntity,
    classify_snippets,
    confirm_classification,
    roster_names,
)
from ai_brain.core.kb.quality import run_quality_detectors, scan_project
from shared.artifacts.blocks import make_content_block
from shared.artifacts.models import ArtifactDocument, ArtifactMetadata, ArtifactType, BlockType, SourceLocation
from shared.db.models import Artifact, utc_now_iso

ROOT = Path(__file__).resolve().parents[2]
MATE_SQLITE = ROOT / "mate.sqlite"

# Sample corpus filenames — fixtures only, not product constants.
BDO_FILENAME = "Etex - SWIFT Support Independent Assessment_v20260312.pdf"
CONSORTIUM_FILENAME = "TF Inetum Proposal Etex CSP Assessment.pdf"
CSR_FILENAME = "KPMG_BELGIUM_BV_(GROUP)_CSR_Highlights_2026_02_23.pdf"


def _artifact(**kwargs) -> Artifact:
    now = utc_now_iso()
    payload = {
        "id": "a1",
        "project_id": "p1",
        "uploaded_by": "u1",
        "kind": "upload",
        "original_name": "file.pdf",
        "storage_relpath": "rel/a",
        "created_at": now,
        "parse_status": "ok",
        "size_bytes": 1000,
    }
    payload.update(kwargs)
    return Artifact(**payload)


def _doc(blocks, filename: str = "x.pdf") -> ArtifactDocument:
    return ArtifactDocument(
        source=filename,
        artifact_type=ArtifactType.PDF,
        metadata=ArtifactMetadata(filename=filename, artifact_type=ArtifactType.PDF),
        blocks=list(blocks),
    )


def test_orphan_parse_when_pending_without_json():
    artifact = _artifact(parse_status="pending", parsed_json=None)
    flags = run_quality_detectors(artifact, None)
    assert any(flag["kind"] == "orphan_parse" for flag in flags)


def test_image_dominant():
    blocks = [
        make_content_block(
            seq_id=f"img-{i}",
            block_type=BlockType.IMAGE,
            text=f"[image {i}]",
            location=SourceLocation(page=1),
        )
        for i in range(3)
    ] + [
        make_content_block(
            seq_id="txt",
            block_type=BlockType.TEXT,
            text="A short caption.",
            location=SourceLocation(page=1),
        )
    ]
    flags = run_quality_detectors(_artifact(), _doc(blocks))
    assert any(flag["kind"] == "image_dominant" for flag in flags)


def test_low_yield_csr_like_ratio():
    blocks = [
        make_content_block(
            seq_id="kpi",
            block_type=BlockType.TEXT,
            text="15",
            location=SourceLocation(page=1),
            extra={"page_kind": "dashboard"},
        )
    ]
    artifact = _artifact(
        original_name=CSR_FILENAME,
        size_bytes=418575,
        parse_status="ok",
    )
    flags = run_quality_detectors(artifact, _doc(blocks, CSR_FILENAME))
    assert any(flag["kind"] == "low_yield" for flag in flags)


def test_filename_heuristics_swift_dump():
    from ai_brain.core.kb.classify import classify_from_filename

    bdo = classify_from_filename(BDO_FILENAME)
    assert bdo is not None and bdo.bid_id == "bdo"
    csr = classify_from_filename(CSR_FILENAME)
    assert csr is not None and csr.bid_id == "kpmg" and csr.doc_role == "csr"
    consortium = classify_from_filename(CONSORTIUM_FILENAME)
    assert consortium is not None and consortium.bid_id == "trifinance-inetum"
    rfp = classify_from_filename("Etex_RFP_Swift CSP_06022026.pdf")
    assert rfp is not None and rfp.doc_role == "rfp"


def test_bdo_classifier_ignores_etex_filename():
    def invoke(_prompt: str) -> BidClassification:
        return BidClassification(
            bid_id="bdo",
            bid_label="BDO",
            doc_role="proposal",
            entities=[LegalEntity(name="BDO", registry_id=None)],
            confidence=0.91,
            role_confidence=0.88,
        )

    result = classify_snippets(
        BDO_FILENAME,
        ["Steven Cauwenberghs, Partner, Risk Advisory BDO"],
        invoke=invoke,
    )
    assert result.bid_id == "bdo"
    assert result.entities[0].name == "BDO"
    assert "Etex" not in result.bid_label


def test_consortium_classifier_two_entities_one_bid():
    def invoke(_prompt: str) -> BidClassification:
        return BidClassification(
            bid_id="trifinance-inetum",
            bid_label="TriFinance & Inetum",
            doc_role="proposal",
            entities=[
                LegalEntity(name="TriFinance", registry_id="BE-X-882734939"),
                LegalEntity(name="Inetum"),
            ],
            confidence=0.9,
        )

    result = classify_snippets(
        CONSORTIUM_FILENAME,
        ["Proposal TriFinance & Inetum", "Inetum will prepare the questionnaires"],
        invoke=invoke,
    )
    assert result.bid_id == "trifinance-inetum"
    assert len(result.entities) == 2
    assert {entity.name for entity in result.entities} == {"TriFinance", "Inetum"}


def test_confirm_rosters_bdo(monkeypatch, tmp_path):
    from shared.db import connection as db_connection
    from shared.db import init_db
    from shared.db.connection import session_scope
    from shared.db.models import AppUser, Project

    if db_connection._engine is not None:
        db_connection._engine.dispose()
    db_connection._engine = None
    db_connection._SessionLocal = None
    db_path = tmp_path / "test.sqlite"
    monkeypatch.setenv("MATE_SQLITE_PATH", str(db_path))
    init_db()
    now = utc_now_iso()
    with session_scope() as session:
        session.add(AppUser(workspace_id="u1", created_at=now, updated_at=now))
        session.add(
            Project(
                id="p1",
                code="PRJ-TEST",
                owner_id="u1",
                module_id="procurement-ai-assistant",
                name="t",
                status="Active",
                priority="Medium",
                progress=0,
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            Artifact(
                id="art-bdo",
                project_id="p1",
                uploaded_by="u1",
                kind="upload",
                original_name=BDO_FILENAME,
                storage_relpath="rel/bdo",
                created_at=now,
                parse_status="ok",
            )
        )
    confirm_classification(
        "p1",
        "art-bdo",
        BidClassification(
            bid_id="bdo",
            bid_label="BDO",
            doc_role="proposal",
            entities=[LegalEntity(name="BDO")],
            confidence=0.9,
        ),
    )
    names = roster_names("p1")
    assert "BDO" in names
    if db_connection._engine is not None:
        db_connection._engine.dispose()
    db_connection._engine = None
    db_connection._SessionLocal = None


def test_prj_2026_0001_flags_kpmg_csr(tmp_path, monkeypatch):
    from shared.db import connection as db_connection
    from shared.db.migrate import apply_kb_foundation
    from sqlalchemy import create_engine

    if not MATE_SQLITE.exists():
        pytest.skip("mate.sqlite not present")
    copy = tmp_path / "mate-copy.sqlite"
    shutil.copy2(MATE_SQLITE, copy)
    monkeypatch.setenv("MATE_SQLITE_PATH", str(copy))
    if db_connection._engine is not None:
        db_connection._engine.dispose()
    db_connection._engine = None
    db_connection._SessionLocal = None
    engine = create_engine(f"sqlite:///{copy.as_posix()}")
    apply_kb_foundation(engine)
    engine.dispose()

    from shared.db import init_db

    init_db()
    flags = scan_project("PRJ-2026-0001")
    csr = [flag for flag in flags if CSR_FILENAME in (flag.get("original_name") or "")]
    assert any(flag["kind"] == "low_yield" for flag in csr), flags[:8]
    if db_connection._engine is not None:
        db_connection._engine.dispose()
    db_connection._engine = None
    db_connection._SessionLocal = None


def test_kb_package_has_no_demo_machine_paths():
    kb = Path(__file__).resolve().parents[1] / "core" / "kb"
    for path in sorted(kb.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        assert "DEMO_CORPUS_DIR" not in text
        assert "BDO_FILENAME" not in text
        assert r"D:\Work" not in text
        assert "Simple example" not in text
