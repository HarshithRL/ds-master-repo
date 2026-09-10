"""Regression: parse persistence, matrix corpus, materialize sidecar, rfp chunks."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

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
    monkeypatch.setenv("MATE_PROJECTS_DATA_ROOT", str(Path(tmp) / "data"))
    init_db()
    yield Path(tmp)
    if db_connection._engine is not None:
        db_connection._engine.dispose()
    db_connection._engine = None
    db_connection._SessionLocal = None
    shutil.rmtree(tmp, ignore_errors=True)


def _seed_user_project(project_id: str = "p1"):
    from shared.db.connection import session_scope
    from shared.db.models import AppUser, Project

    now = utc_now_iso()
    with session_scope() as session:
        session.add(AppUser(workspace_id="u1", created_at=now, updated_at=now))
        session.add(
            Project(
                id=project_id,
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


def test_save_parse_result_omitted_json_does_not_wipe(db_env):
    from shared.db.connection import session_scope
    from shared.db.models import Artifact
    from shared.db.repos import artifacts as artifact_repo

    _seed_user_project()
    now = utc_now_iso()
    with session_scope() as session:
        session.add(
            Artifact(
                id="a1",
                project_id="p1",
                uploaded_by="u1",
                kind="upload",
                original_name="doc.pdf",
                storage_relpath="rel/a1",
                created_at=now,
                parse_status="ok",
                parsed_json='{"markdown":"hello"}',
                parsed_relpath="parsed/a1.json",
            )
        )
    saved = artifact_repo.save_parse_result("a1", parse_status="error", parse_error="boom")
    assert saved.parse_status == "error"
    assert saved.parse_error == "boom"
    assert saved.parsed_json == '{"markdown":"hello"}'
    assert saved.parsed_relpath == "parsed/a1.json"


def test_save_parse_result_can_explicitly_clear(db_env):
    from shared.db.connection import session_scope
    from shared.db.models import Artifact
    from shared.db.repos import artifacts as artifact_repo

    _seed_user_project()
    now = utc_now_iso()
    with session_scope() as session:
        session.add(
            Artifact(
                id="a2",
                project_id="p1",
                uploaded_by="u1",
                kind="upload",
                original_name="doc.pdf",
                storage_relpath="rel/a2",
                created_at=now,
                parse_status="ok",
                parsed_json='{"markdown":"hello"}',
                parsed_relpath="parsed/a2.json",
            )
        )
    saved = artifact_repo.save_parse_result(
        "a2",
        parse_status="error",
        parse_error="wipe",
        parsed_json=None,
        parsed_relpath=None,
    )
    assert saved.parsed_json is None
    assert saved.parsed_relpath is None


def test_stale_ok_artifact_ids_detects_missing_chunks_and_markdown(db_env):
    from shared.db.connection import session_scope
    from shared.db.models import Artifact, Chunk
    from ai_brain.core.kb.extract.ingest import stale_ok_artifact_ids

    _seed_user_project()
    now = utc_now_iso()
    with session_scope() as session:
        session.add(
            Artifact(
                id="ok-empty",
                project_id="p1",
                uploaded_by="u1",
                kind="upload",
                original_name="empty.pdf",
                storage_relpath="rel/empty",
                created_at=now,
                parse_status="ok",
                parsed_json='{"parser":"AzureDocumentIntelligence","markdown_relpath":"empty.md"}',
            )
        )
        session.add(
            Artifact(
                id="ok-good",
                project_id="p1",
                uploaded_by="u1",
                kind="upload",
                original_name="good.pdf",
                storage_relpath="rel/good",
                created_at=now,
                parse_status="ok",
                parsed_json='{"markdown":"## Page 1\\nbody"}',
            )
        )
        session.add(
            Chunk(
                id="c1",
                project_id="p1",
                artifact_id="ok-good",
                ordinal=0,
                chunk_type="text",
                text="body",
                token_count=1,
                heading_path_json="[]",
                block_ids_json="[]",
                location_json="{}",
                created_at=now,
            )
        )
    stale = stale_ok_artifact_ids("p1")
    assert "ok-empty" in stale
    assert "ok-good" not in stale


def test_materialize_uses_md_sidecar_when_json_lacks_markdown(db_env, monkeypatch):
    from shared.db.connection import session_scope
    from shared.db.models import Artifact
    from shared.db.paths import artifact_absolute_path, parsed_storage_relpath
    from ai_brain.core.kb.store.materialize import project_files

    _seed_user_project()
    now = utc_now_iso()
    rel = parsed_storage_relpath("p1", "art-side")
    abs_json = artifact_absolute_path(rel)
    abs_json.parent.mkdir(parents=True, exist_ok=True)
    abs_json.write_text(
        json.dumps({"parser": "AzureDocumentIntelligence", "markdown_relpath": "art-side.md"}),
        encoding="utf-8",
    )
    abs_json.with_suffix(".md").write_text("## Page 1\nSidecar body from disk.\n", encoding="utf-8")
    with session_scope() as session:
        session.add(
            Artifact(
                id="art-side",
                project_id="p1",
                uploaded_by="u1",
                kind="upload",
                original_name="Vendor Proposal.pdf",
                storage_relpath="uploads/art-side.pdf",
                created_at=now,
                parse_status="ok",
                vendor_id="ey",
                doc_role="proposal",
                parsed_json=abs_json.read_text(encoding="utf-8"),
                parsed_relpath=rel,
            )
        )
    files = project_files("p1")
    bodies = "\n".join(files.values())
    assert "Sidecar body from disk" in bodies
    assert "no usable markdown" not in bodies


def test_list_bid_chunks_rfp_uses_doc_role(db_env):
    from shared.db.connection import session_scope
    from shared.db.models import Artifact, Chunk
    from ai_brain.core.kb.api.mcp_tools import list_bid_chunks

    _seed_user_project()
    now = utc_now_iso()
    with session_scope() as session:
        session.add(
            Artifact(
                id="rfp1",
                project_id="p1",
                uploaded_by="u1",
                kind="upload",
                original_name="RFP_Swift.docx",
                storage_relpath="rel/rfp1",
                created_at=now,
                parse_status="ok",
                vendor_id=None,
                doc_role="rfp",
                parsed_json='{"markdown":"rfp text"}',
            )
        )
        session.add(
            Chunk(
                id="chunk-rfp",
                project_id="p1",
                artifact_id="rfp1",
                ordinal=0,
                chunk_type="text",
                text="requirement one",
                token_count=2,
                heading_path_json='["Scope"]',
                block_ids_json="[]",
                location_json='{"page":1}',
                created_at=now,
            )
        )
    manifest = list_bid_chunks("rfp", project_id="p1")
    assert "chunk-rfp" in manifest
    assert "(no chunks)" not in manifest


@pytest.mark.asyncio
async def test_parse_one_uses_parse_and_store(db_env, monkeypatch):
    from ai_brain.core.procurement_ai import file_ingest

    calls: list[str] = []

    class FakeArtifact:
        id = "f1"
        project_id = "p1"
        original_name = "x.pdf"
        parse_status = "ok"
        parse_error = None
        parsed_json = json.dumps({"markdown": "## Page 1\nhello"})

    def fake_load(aid: str):
        assert aid == "f1"
        return FakeArtifact()

    def fake_parse_and_store(artifact):
        calls.append("parse_and_store")
        return FakeArtifact()

    monkeypatch.setattr("ai_brain.core.kb.extract.ingest.load_artifact", fake_load)
    monkeypatch.setattr(
        "backend.services.artifact_parse.parse_and_store",
        fake_parse_and_store,
        raising=False,
    )
    # Also patch via services path used as fallback.
    import sys
    import types

    services_mod = types.ModuleType("services")
    artifact_parse_mod = types.ModuleType("services.artifact_parse")
    artifact_parse_mod.parse_and_store = fake_parse_and_store
    sys.modules["services"] = services_mod
    sys.modules["services.artifact_parse"] = artifact_parse_mod
    monkeypatch.setattr(
        file_ingest.chunk_repo,
        "list_for_artifact",
        lambda _aid: [SimpleNamespace(id="c1", ordinal=0, text="hello")],
    )

    out = await file_ingest.parse_one(
        {"project_id": "p1", "file": {"file_id": "f1", "filename": "x.pdf"}}
    )
    assert calls == ["parse_and_store"]
    assert out["file_results"][0]["status"] == "chunked"
    assert out["file_results"][0]["chunk_count"] == 1


@pytest.mark.asyncio
async def test_parse_one_marks_error_when_no_sql_chunks(db_env, monkeypatch):
    from ai_brain.core.procurement_ai import file_ingest

    class FakeArtifact:
        id = "f2"
        project_id = "p1"
        original_name = "x.pdf"
        parse_status = "ok"
        parse_error = None
        parsed_json = json.dumps({"markdown": "## Page 1\nhello"})

    monkeypatch.setattr(
        "ai_brain.core.kb.extract.ingest.load_artifact",
        lambda _aid: FakeArtifact(),
    )
    import sys
    import types

    mod = types.ModuleType("services.artifact_parse")
    mod.parse_and_store = lambda artifact: FakeArtifact()
    sys.modules["services"] = types.ModuleType("services")
    sys.modules["services.artifact_parse"] = mod
    sys.modules["backend.services.artifact_parse"] = mod

    saved: dict = {}

    def fake_save(aid, **kwargs):
        saved.update(kwargs)
        return FakeArtifact()

    monkeypatch.setattr(file_ingest.artifact_repo, "save_parse_result", fake_save)
    monkeypatch.setattr(file_ingest.chunk_repo, "list_for_artifact", lambda _aid: [])

    out = await file_ingest.parse_one(
        {"project_id": "p1", "file": {"file_id": "f2", "filename": "x.pdf"}}
    )
    assert out["file_results"][0]["status"] == "failed"
    assert saved.get("parse_status") == "error"
    assert "no SQL chunks" in (saved.get("parse_error") or out["file_results"][0]["error"])


def test_memory_chunk_store_gated_off_by_default(monkeypatch):
    from ai_brain.core.procurement_ai import file_ingest

    monkeypatch.delenv("MATE_USE_MEMORY_CHUNK_STORE", raising=False)
    file_ingest._CHUNK_STORE.clear()
    file_ingest._store_chunks("p1", [{"file_id": "a", "chunk_id": "1", "text": "x"}])
    assert file_ingest._CHUNK_STORE.get("p1") in (None, [])


@pytest.mark.asyncio
async def test_compare_xlsx_writes_workbook_on_agent_failure(db_env, monkeypatch):
    from shared.db.connection import session_scope
    from shared.db.models import Artifact, Project, AppUser
    from ai_brain.core.procurement_ai.subagents import compare_xlsx as compare_mod

    now = utc_now_iso()
    with session_scope() as session:
        session.add(AppUser(workspace_id="u1", created_at=now, updated_at=now))
        session.add(
            Project(
                id="p-xlsx",
                code="PRJ-X",
                owner_id="u1",
                module_id="procurement-ai-assistant",
                name="x",
                status="Active",
                priority="Medium",
                progress=0,
                created_at=now,
                updated_at=now,
                business_process="indirect_it_services",
            )
        )
        session.add(
            Artifact(
                id="ax",
                project_id="p-xlsx",
                uploaded_by="u1",
                kind="upload",
                original_name="v.pdf",
                storage_relpath="rel/ax",
                created_at=now,
                parse_status="ok",
                vendor_id="ey",
                doc_role="proposal",
                parsed_json='{"markdown":"## Page 1\\nok"}',
            )
        )

    async def boom(*_a, **_k):
        raise RuntimeError("agent exploded")

    async def no_corpus(_pid):
        return None

    monkeypatch.setattr(compare_mod, "extract_comparison_matrix", boom, raising=False)
    monkeypatch.setattr(
        "ai_brain.core.procurement_ai.subagents.comparison_matrix.extract_comparison_matrix",
        boom,
    )
    monkeypatch.setattr(compare_mod, "_ensure_corpus", no_corpus)
    monkeypatch.setattr(
        "ai_brain.core.kb.build.pipeline.ensure_vendor_bids",
        lambda _pid: None,
    )

    out = await compare_mod.compare_xlsx({"project_id": "p-xlsx"})
    href = (out.get("procurement") or {}).get("xlsx_href") or ""
    assert href, out
    assert "Download:" in ((out.get("procurement") or {}).get("assistant_reply") or "")
    from ai_brain.core.procurement_ai.packs import store as pack_store

    path = pack_store.pack_file("p-xlsx", "comparison_matrix.xlsx")
    assert path.exists()
