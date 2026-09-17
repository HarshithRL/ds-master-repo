"""load_context should open one DB session for project + artifacts + chunks."""

from __future__ import annotations

import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

import pytest

from shared.db.models import utc_now_iso


@pytest.fixture()
def db_env(monkeypatch):
    from shared.db import init_db
    from shared.db import connection as db_connection

    db_connection.reset_engine_state()
    tmp = tempfile.mkdtemp()
    db_path = Path(tmp) / "test.sqlite"
    monkeypatch.setenv("MATE_SQLITE_PATH", str(db_path))
    monkeypatch.delenv("MATE_DB_BACKEND", raising=False)
    init_db()
    yield db_path
    db_connection.reset_engine_state()
    shutil.rmtree(tmp, ignore_errors=True)


def _seed():
    from shared.db.connection import session_scope
    from shared.db.models import AppUser, Artifact, Chunk, Project

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
                id="art-1",
                project_id="p1",
                uploaded_by="u1",
                kind="upload",
                original_name="BDO_proposal.pdf",
                storage_relpath="rel/bdo",
                created_at=now,
                parse_status="ok",
                vendor_id="bdo",
                doc_role="proposal",
            )
        )
        session.add(
            Chunk(
                id="chk-1",
                project_id="p1",
                artifact_id="art-1",
                ordinal=0,
                chunk_type="paragraph",
                text="BDO will staff the assessment.",
                token_count=6,
                created_at=now,
            )
        )


def test_load_context_uses_one_session(db_env, monkeypatch):
    from ai_brain.core.procurement_ai import project_context
    from shared.db.connection import session_scope

    _seed()
    count = {"n": 0}
    real_scope = session_scope

    @contextmanager
    def counting_scope():
        count["n"] += 1
        with real_scope() as session:
            yield session

    monkeypatch.setattr(project_context, "session_scope", counting_scope)
    project, artifacts, chunks = project_context.load_context("p1")
    assert project is not None
    assert project.id == "p1"
    assert [row.id for row in artifacts] == ["art-1"]
    assert [row.id for row in chunks] == ["chk-1"]
    assert count["n"] == 1


def test_list_bid_ids_uses_supplied_artifacts_without_db(monkeypatch):
    from types import SimpleNamespace

    from ai_brain.core.kb.store import materialize

    def boom(_project_id):
        raise AssertionError("must not reopen project/artifact sessions")

    monkeypatch.setattr(materialize, "load_project", boom)
    monkeypatch.setattr(materialize, "load_artifacts", boom)
    bids = materialize.list_bid_ids(
        "p1",
        artifacts=[
            SimpleNamespace(vendor_id="bdo"),
            SimpleNamespace(vendor_id="trifinance-inetum"),
            SimpleNamespace(vendor_id=""),
        ],
    )
    assert bids == ["bdo", "trifinance-inetum"]
