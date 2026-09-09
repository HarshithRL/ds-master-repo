"""Overview / Requirements / Vendors view builders from SQL MatrixSource."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from ai_brain.core.kb.api.schemas import BidProfile, EvidenceItem, VendorEvidenceBundle
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


def _seed_project():
    from shared.db.connection import session_scope
    from shared.db.models import AppUser, Artifact, Project, Vendor

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
                id="art-ok",
                project_id="p1",
                uploaded_by="u1",
                kind="upload",
                original_name="Acme_Offer.pdf",
                storage_relpath="rel/ok",
                created_at=now,
                parse_status="ok",
                vendor_id="acme-offer",
                doc_role="proposal",
                parsed_json=json.dumps(
                    {"markdown": "## Page 1\nAcme covers both BIC codes.\n"}
                ),
            )
        )
        session.add(
            Vendor(
                id="p1:acme",
                project_id="p1",
                name="Acme",
                legal_entity="Acme NV",
                status="bidder",
                created_at=now,
            )
        )


def _seed_extracted():
    from ai_brain.core.kb.store.persist import seed_swift_requirements, upsert_bid_profile, upsert_evidence_bundle

    seed_swift_requirements("p1")
    upsert_evidence_bundle(
        "p1",
        VendorEvidenceBundle(
            bid_id="acme-offer",
            items=[
                EvidenceItem(
                    requirement_id="R01",
                    status="met",
                    claim_text="Acme covers both BIC codes.",
                    artifact_id="art-ok",
                    page=1,
                    confidence=0.9,
                )
            ],
        ),
    )
    upsert_bid_profile(
        "p1",
        BidProfile(
            bid_id="acme-offer",
            timeline="12 weeks",
            y1_tco="EUR 48000",
            ecovadis="Gold",
            delivery_model="On-site Belgium",
        ),
    )


def test_views_from_sql_evidence_and_profile(db_env, tmp_path, monkeypatch):
    import sys

    from ai_brain.core.kb.api.views import (
        build_overview_view,
        build_requirements_view,
        build_vendors_view,
        write_view,
    )
    from ai_brain.core.procurement_ai.packs.store import read_view
    from sqlalchemy import select
    from shared.db.connection import session_scope
    from shared.db.models import Artifact, Project

    backend = Path(__file__).resolve().parents[2] / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    from services.procurement_serializers import overview_payload

    monkeypatch.setenv("MATE_PROJECTS_DATA_ROOT", str(tmp_path))
    _seed_project()
    _seed_extracted()

    overview = build_overview_view("p1")
    assert overview["requirements"]["total"] >= 40
    assert overview["vendors"]["invited"] >= 1
    assert overview["vendors"]["responded"] >= 1
    assert overview["project"]["progress"] > 0
    assert any(metric["value"] == "EUR 48000" for metric in overview["metrics"])
    assert any("12 weeks" in item["date"] for item in overview["milestones"])

    requirements = build_requirements_view("p1")
    r01 = next(item for item in requirements["items"] if item["id"] == "R01")
    assert r01["coverage"] == "met"
    assert r01["mandatory"] is True

    vendors = build_vendors_view("p1")
    card = vendors["vendors"][0]
    assert card["tco"] == "EUR 48000"
    assert card["timeline"] == "12 weeks"
    assert card["responded"] is True

    write_view("p1", "overview", overview)
    write_view("p1", "requirements", requirements)
    write_view("p1", "vendors", vendors)

    saved = read_view("p1", "vendors")
    assert saved["vendors"][0]["tco"] == "EUR 48000"

    with session_scope() as session:
        project = session.get(Project, "p1")
        project.requirements_json = json.dumps([{"ref": "X", "text": "intake only"}])
        artifacts = list(
            session.scalars(select(Artifact).where(Artifact.project_id == "p1")).all()
        )
        session.expunge(project)
        for row in artifacts:
            session.expunge(row)
    payload = overview_payload(project, artifacts)
    assert payload["requirements"]["total"] >= 40
    assert payload["requirements"]["total"] != 1


def test_fill_nodes_write_view_files(db_env, tmp_path, monkeypatch):
    from ai_brain.core.kb.build.pipeline import fill_overview, fill_requirements, fill_vendors, plan_publish
    from ai_brain.core.procurement_ai.packs.store import read_view
    from langgraph.types import Send

    monkeypatch.setenv("MATE_PROJECTS_DATA_ROOT", str(tmp_path))
    _seed_project()
    _seed_extracted()

    sends = plan_publish({"project_id": "p1", "procurement": {"kb_audit": {"bundle_count": 1, "failed": 0}}})
    assert all(isinstance(item, Send) for item in sends)

    fill_overview({"project_id": "p1", "kb_audit": {"bundle_count": 1, "failed": 0}})
    fill_requirements({"project_id": "p1"})
    fill_vendors({"project_id": "p1"})
    assert read_view("p1", "overview")["vendors"]["invited"] >= 1
    assert read_view("p1", "requirements")["total"] >= 40
    assert read_view("p1", "vendors")["vendors"][0]["timeline"] == "12 weeks"
