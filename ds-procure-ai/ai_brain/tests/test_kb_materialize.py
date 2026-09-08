"""W4: virtual /project/{code}/ tree from parsed artifacts."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import pytest

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
    from shared.db.models import AppUser, Artifact, Project, QualityFlag, Vendor

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
                original_name="TF Inetum Proposal Etex CSP Assessment.pdf",
                storage_relpath="rel/ok",
                created_at=now,
                parse_status="ok",
                vendor_id="trifinance-inetum",
                doc_role="proposal",
                parsed_json=json.dumps(
                    {
                        "markdown": "## Page 1\nInetum will prepare the questionnaires.\n"
                    }
                ),
            )
        )
        session.add(
            Artifact(
                id="art-fail",
                project_id="p1",
                uploaded_by="u1",
                kind="upload",
                original_name="corrupt.pdf",
                storage_relpath="rel/fail",
                created_at=now,
                parse_status="error",
                parse_error="parser exploded",
                vendor_id="bdo",
                doc_role="proposal",
            )
        )
        session.add(
            Vendor(
                id="p1:trifinance",
                project_id="p1",
                name="TriFinance",
                legal_entity="TriFinance",
                registry_id="BE-X-882734939",
                status="bidder",
                created_at=now,
            )
        )
        session.add(
            Vendor(
                id="p1:inetum",
                project_id="p1",
                name="Inetum",
                legal_entity="Inetum",
                status="bidder",
                created_at=now,
            )
        )
        session.add(
            QualityFlag(
                id="qf1",
                project_id="p1",
                artifact_id="art-fail",
                kind="orphan_parse",
                detail="parse failed",
                severity="high",
                created_at=now,
            )
        )


def test_materialize_tree_includes_quality_for_failed_artifact(db_env):
    from ai_brain.core.kb.materialize import list_bid_ids, project_files

    _seed_project()
    files = project_files("p1")
    quality_path = "/project/PRJ-TEST/_quality/art-fail.md"
    assert quality_path in files
    assert "parser exploded" in files[quality_path]
    ok_paths = [path for path in files if path.startswith("/project/PRJ-TEST/vendors/trifinance-inetum/")]
    assert ok_paths
    assert "Inetum will prepare the questionnaires" in files[ok_paths[0]]
    readme = files["/project/PRJ-TEST/README.md"]
    assert "TriFinance" in readme
    assert "Inetum" in readme
    assert "trifinance-inetum" in readme
    assert "consortium" in readme.lower()
    assert "bdo" in list_bid_ids("p1")
    assert "trifinance-inetum" in list_bid_ids("p1")
