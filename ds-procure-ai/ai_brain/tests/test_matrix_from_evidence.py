"""W8 matrix richness: SQL evidence → xlsx structure matching the sample workbook."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from openpyxl import load_workbook

from ai_brain.core.procurement_ai.packs.matrix_from_evidence import (
    pick_evidence_row,
    render_evidence_cell,
)
from ai_brain.core.procurement_ai.packs.matrix_layout import (
    EXTRACTION_FAILED,
    NOT_OFFERED,
    NOT_STATED,
    SWIFT_REQUIREMENTS,
)
from shared.db.models import utc_now_iso


@pytest.fixture()
def db_env(monkeypatch):
    from shared.db import init_db
    from shared.db import connection as db_connection

    if db_connection._engine is not None:
        db_connection._engine.dispose()
    db_connection._engine = None
    db_connection._SessionLocal = None
    tmp = tempfile.mkdtemp()
    db_path = Path(tmp) / "test.sqlite"
    monkeypatch.setenv("MATE_SQLITE_PATH", str(db_path))
    init_db()
    yield db_path
    if db_connection._engine is not None:
        db_connection._engine.dispose()
    db_connection._engine = None
    db_connection._SessionLocal = None
    shutil.rmtree(tmp, ignore_errors=True)


def test_render_states_are_distinct_phrases():
    assert NOT_STATED != NOT_OFFERED
    assert NOT_STATED != EXTRACTION_FAILED
    assert NOT_OFFERED != EXTRACTION_FAILED
    assert "Not stated" in NOT_STATED
    assert "retry" in EXTRACTION_FAILED.lower() or "failed" in EXTRACTION_FAILED.lower()


def test_render_evidence_cell_keeps_three_states():
    stated = render_evidence_cell(_evidence(status="not_stated"))
    offered = render_evidence_cell(_evidence(status="not_offered", claim_text="No fixed price"))
    failed = render_evidence_cell(_evidence(status="extraction_failed"))
    met = render_evidence_cell(
        _evidence(status="met", claim_text="Two BICs in scope", artifact_id="art-bdo", page=4),
        artifact_names={"art-bdo": "bdo-proposal.pdf"},
    )
    assert NOT_STATED in stated.text
    assert offered.status == "not_offered"
    assert NOT_OFFERED in offered.text or "No fixed price" in offered.text
    assert EXTRACTION_FAILED in failed.text
    assert "Two BICs" in met.text
    assert "p.4" in (met.text + (met.citation or ""))
    assert stated.text != offered.text != failed.text


def test_reviewed_row_is_pinned():
    older = _evidence(status="met", claim_text="old", extracted_at="2026-01-01", id="e1")
    reviewed = _evidence(
        status="partial",
        claim_text="human",
        reviewed_by="buyer",
        reviewed_at="2026-02-01",
        extracted_at="2026-01-02",
        id="e2",
    )
    newer = _evidence(status="met", claim_text="new", extracted_at="2026-03-01", id="e3")
    chosen = pick_evidence_row([older, reviewed, newer])
    assert chosen.id == "e2"
    cell = render_evidence_cell(chosen)
    assert cell.pinned
    assert "[reviewed]" in cell.text


def test_workbook_matches_sample_richness(db_env, tmp_path, monkeypatch):
    monkeypatch.setenv("MATE_PROJECTS_DATA_ROOT", str(tmp_path))
    _seed_warm_project()
    from ai_brain.core.procurement_ai.insights import build_insight_payload
    from ai_brain.core.procurement_ai.packs.compare_xlsx import build_comparison_xlsx

    class _Project:
        id = "p1"
        code = "PRJ-TEST"
        name = "SWIFT CSP assessment"
        business_process = "Indirect"
        category = "SWIFT CSCF"
        description = "Professional services days"

    insights = build_insight_payload(_Project(), [], [])
    result = build_comparison_xlsx("p1", insights, thread_id="t-matrix")
    assert result["status"] == "ready"
    assert result["llm_used"] is False
    wb = load_workbook(result["path"])
    blob = _workbook_text(wb)
    assert r"D:\Work" not in blob
    assert "Simple example" not in blob

    for name in (
        "Final BAFO Comparison",
        "Procurement Requirements",
        "Sources & Notes",
        "Citations",
        "Pricing lines",
        "Cover",
    ):
        assert name in wb.sheetnames, wb.sheetnames

    bafo = wb["Final BAFO Comparison"]
    assert bafo["B1"].value == "Type "
    assert bafo["A3"].value == "Solution costs (Software, Materials)"
    assert bafo["A6"].value == "Total TCO year 1"
    assert bafo["A17"].value == "Score Card score"
    vendors = [bafo.cell(1, col).value for col in range(3, 8) if bafo.cell(1, col).value]
    assert "BDO" in vendors
    assert "EY" in vendors
    assert any(str(bafo.cell(2, col).value or "").startswith("Vendor ") for col in range(3, 5))

    reqs = wb["Procurement Requirements"]
    headers = [reqs.cell(4, col).value for col in range(1, 12) if reqs.cell(4, col).value]
    assert headers[:3] == ["ID", "Requirement", "Category"]
    assert "BDO" in headers and "EY" in headers
    ids = {reqs.cell(row, 1).value for row in range(5, reqs.max_row + 1)}
    assert "R01" in ids
    assert "R40" in ids
    assert len(SWIFT_REQUIREMENTS) == 40
    legend = str(reqs["A2"].value or "")
    assert NOT_STATED in legend
    assert NOT_OFFERED in legend
    assert EXTRACTION_FAILED in legend

    req_blob = "\n".join(
        str(reqs.cell(row, col).value or "")
        for row in range(5, reqs.max_row + 1)
        for col in range(6, 10)
    )
    assert NOT_STATED in req_blob
    assert NOT_OFFERED in req_blob or "✗" in req_blob
    assert EXTRACTION_FAILED in req_blob

    cites = wb["Citations"]
    cite_headers = [cites.cell(1, col).value for col in range(1, 10)]
    assert cite_headers[:4] == ["Requirement", "Requirement text", "Bid", "Status"]
    statuses = {cites.cell(row, 4).value for row in range(2, cites.max_row + 1)}
    assert {"not_stated", "not_offered", "extraction_failed", "met"} <= statuses
    assert any(cites.cell(row, 7).value == 4 for row in range(2, cites.max_row + 1))

    pricing = wb["Pricing lines"]
    assert pricing["A1"].value == "Bid"
    assert pricing["B1"].value == "Offer type"
    assert pricing["A2"].value == "BDO"
    assert pricing["I2"].value == 35251

    sources = wb["Sources & Notes"]
    assert "parsed project uploads" in str(sources["A1"].value or "").lower()
    assert "bdo-proposal.pdf" in blob
    assert "Etex_RFP_Swift CSP_06022026.pdf" in blob


def _evidence(**kwargs):
    now = utc_now_iso()
    payload = {
        "id": "e0",
        "project_id": "p1",
        "requirement_id": "R01",
        "vendor_id": "bdo",
        "status": "met",
        "claim_text": None,
        "artifact_id": None,
        "chunk_id": None,
        "page": None,
        "confidence": 0.9,
        "model_version": "test",
        "prompt_version": "v1",
        "extracted_at": now,
        "reviewed_by": None,
        "reviewed_at": None,
    }
    payload.update(kwargs)
    return SimpleNamespace(**payload)


def _workbook_text(wb) -> str:
    parts: list[str] = []
    for ws in wb.worksheets:
        for row in ws.iter_rows(values_only=True):
            for value in row:
                if value is not None:
                    parts.append(str(value))
    return "\n".join(parts)


def _seed_warm_project():
    from shared.db.connection import session_scope
    from shared.db.models import (
        AppUser,
        Artifact,
        Evidence,
        PricingLine,
        Project,
        Requirement,
        Vendor,
    )

    now = utc_now_iso()
    with session_scope() as session:
        session.add(AppUser(workspace_id="u1", created_at=now, updated_at=now))
        session.add(
            Project(
                id="p1",
                code="PRJ-TEST",
                owner_id="u1",
                module_id="procurement-ai-assistant",
                name="SWIFT CSP assessment",
                status="Active",
                priority="Medium",
                progress=0,
                created_at=now,
                updated_at=now,
                business_process="Indirect",
                category="SWIFT CSCF",
            )
        )
        session.add(
            Vendor(
                id="bdo",
                project_id="p1",
                name="BDO",
                legal_entity="BDO Advisory BV",
                status="bidder",
                created_at=now,
            )
        )
        session.add(
            Vendor(
                id="ey",
                project_id="p1",
                name="EY",
                legal_entity="EY Bedrijfsrevisoren BV",
                status="bidder",
                created_at=now,
            )
        )
        session.add(
            Artifact(
                id="art-bdo",
                project_id="p1",
                uploaded_by="u1",
                kind="upload",
                original_name="bdo-proposal.pdf",
                storage_relpath="rel/bdo",
                created_at=now,
                parse_status="ok",
                vendor_id="bdo",
                doc_role="proposal",
            )
        )
        session.add(
            Artifact(
                id="art-ey",
                project_id="p1",
                uploaded_by="u1",
                kind="upload",
                original_name="ey-proposal.pdf",
                storage_relpath="rel/ey",
                created_at=now,
                parse_status="ok",
                vendor_id="ey",
                doc_role="proposal",
            )
        )
        session.add(
            Artifact(
                id="art-rfp",
                project_id="p1",
                uploaded_by="u1",
                kind="upload",
                original_name="Etex_RFP_Swift CSP_06022026.pdf",
                storage_relpath="rel/rfp",
                created_at=now,
                parse_status="ok",
                doc_role="rfp",
            )
        )
        session.add(
            Requirement(
                id="R01",
                project_id="p1",
                ordinal=1,
                section="ETEXBEBB (BE) + URSNESMMXXX (ES)",
                text="Two BIC codes in scope",
                category="scope",
                mandatory=1,
                created_at=now,
            )
        )
        session.add(
            Requirement(
                id="R18",
                project_id="p1",
                ordinal=18,
                section="Two offers required",
                text="Dual pricing: T&M AND Fixed Price",
                category="commercial",
                mandatory=1,
                created_at=now,
            )
        )
        session.add(
            Requirement(
                id="R40",
                project_id="p1",
                ordinal=40,
                section="Days per role, IT + business",
                text="A02 Etex obligations completed (man-days + RACI)",
                category="deliverable",
                mandatory=1,
                created_at=now,
            )
        )
        session.add(
            Evidence(
                id="ev-met",
                project_id="p1",
                requirement_id="R01",
                vendor_id="bdo",
                status="met",
                claim_text="Both BIC codes covered",
                artifact_id="art-bdo",
                page=4,
                confidence=0.95,
                model_version="test",
                prompt_version="v1",
                extracted_at=now,
            )
        )
        session.add(
            Evidence(
                id="ev-ns",
                project_id="p1",
                requirement_id="R01",
                vendor_id="ey",
                status="not_stated",
                confidence=0.4,
                model_version="test",
                prompt_version="v1",
                extracted_at=now,
            )
        )
        session.add(
            Evidence(
                id="ev-no",
                project_id="p1",
                requirement_id="R18",
                vendor_id="bdo",
                status="not_offered",
                claim_text="T&M only; no fixed-price offer",
                artifact_id="art-bdo",
                page=11,
                confidence=0.88,
                model_version="test",
                prompt_version="v1",
                extracted_at=now,
            )
        )
        session.add(
            Evidence(
                id="ev-fail",
                project_id="p1",
                requirement_id="R18",
                vendor_id="ey",
                status="extraction_failed",
                artifact_id="art-ey",
                page=2,
                confidence=0.0,
                model_version="test",
                prompt_version="v1",
                extracted_at=now,
            )
        )
        session.add(
            PricingLine(
                id="pl-bdo",
                project_id="p1",
                vendor_id="bdo",
                offer_type="time_and_materials",
                role="Partner",
                seniority="partner",
                rate=1250,
                rate_unit="day",
                currency="EUR",
                quantity=28.2,
                line_total=35251,
                etex_effort_days=4.5,
                artifact_id="art-bdo",
                page=9,
                verified=1,
                model_version="test",
            )
        )
