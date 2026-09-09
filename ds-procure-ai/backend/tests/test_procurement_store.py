"""Procurement persistence tests."""

from __future__ import annotations

import io
import json
import shutil
import tempfile
from pathlib import Path

import pytest

from shared.artifacts.chunking import DocumentChunk
from shared.db import init_db
from shared.db import connection as db_connection
from shared.db.repos import artifacts as artifact_repo
from shared.db.repos import chunks as chunk_repo
from shared.db.repos import projects as project_repo
from shared.db.repos.artifacts import UploadFile
from shared.db.repos.users import upsert_user_from_identity
from services.artifact_parse import parse_and_store
from services.procurement_serializers import (
    dashboard_payload,
    documents_payload,
    workspace_payload,
)

_DEFAULT_CREATE_PAYLOAD = {
    "name": "Test Project",
    "workflowEntryPoint": "Sourcing",
}


@pytest.fixture()
def db_env(monkeypatch):
    if db_connection._engine is not None:
        db_connection._engine.dispose()
    db_connection._engine = None
    db_connection._SessionLocal = None

    tmp = tempfile.mkdtemp()
    db_path = Path(tmp) / "test.sqlite"
    data_root = Path(tmp) / "data" / "projects"
    monkeypatch.setenv("MATE_SQLITE_PATH", str(db_path))
    monkeypatch.setenv("MATE_PROJECTS_DATA_ROOT", str(data_root))
    init_db()
    upsert_user_from_identity(
        {
            "user": {
                "id": "owner-1",
                "display_name": "Owner One",
                "user_name": "owner1",
                "email": "owner1@example.com",
            }
        }
    )
    upsert_user_from_identity(
        {
            "user": {
                "id": "owner-2",
                "display_name": "Owner Two",
                "user_name": "owner2",
                "email": "owner2@example.com",
            }
        }
    )
    yield {"db_path": db_path, "data_root": data_root}
    if db_connection._engine is not None:
        db_connection._engine.dispose()
    db_connection._engine = None
    db_connection._SessionLocal = None
    shutil.rmtree(tmp, ignore_errors=True)


def test_project_crud_scoped_to_owner(db_env):
    created = project_repo.create(
        "owner-1",
        {
            **_DEFAULT_CREATE_PAYLOAD,
            "name": "Office Supplies",
            "category": "Office Supplies",
            "targetSpend": "1000000",
            "requirements": [{"ref": "REQ-01", "text": "Must deliver", "weight": "High"}],
        },
    )
    assert created.id
    assert created.code.startswith("PRJ-")
    assert created.workflow_entry_point == "Sourcing"

    fetched = project_repo.get_for_owner(created.id, "owner-1")
    assert fetched.name == "Office Supplies"

    with pytest.raises(project_repo.ProjectNotFoundError):
        project_repo.get_for_owner(created.id, "owner-2")

    updated = project_repo.update_for_owner(
        created.id,
        "owner-1",
        {"status": "Evaluation", "progress": 25},
    )
    assert updated.status == "Evaluation"
    assert updated.progress == 25

    rows, total = project_repo.list_for_owner("owner-1")
    assert total == 1
    assert rows[0].id == created.id

    project_repo.delete_for_owner(created.id, "owner-1")
    with pytest.raises(project_repo.ProjectNotFoundError):
        project_repo.get_for_owner(created.id, "owner-1")


def test_artifact_upload_serializes_to_documents_and_workspace(db_env):
    created = project_repo.create("owner-1", _DEFAULT_CREATE_PAYLOAD)
    upload = UploadFile(
        filename="Vendor_A.pdf",
        stream=io.BytesIO(b"%PDF-1.4 test"),
        content_type="application/pdf",
    )
    artifact_repo.create_upload(created.id, "owner-1", upload)

    artifacts = artifact_repo.list_for_project(created.id, "owner-1")
    project = project_repo.get_for_owner(created.id, "owner-1")
    assert artifacts[0].parse_status == "pending"

    docs = documents_payload(artifacts)
    assert len(docs["fileGroups"]) == 1
    assert docs["fileGroups"][0]["files"][0]["name"] == "Vendor_A.pdf"

    workspace = workspace_payload(project, artifacts, user_initial="O")
    assert workspace["files"]["inputsCount"] == 1
    assert workspace["chatMessages"] == []


def test_dashboard_counts_reflect_projects(db_env):
    upsert_user_from_identity(
        {
            "user": {
                "id": "dash-owner",
                "display_name": "Dash Owner",
                "user_name": "dash",
                "email": "dash@example.com",
            }
        }
    )
    project_repo.create(
        "dash-owner",
        {**_DEFAULT_CREATE_PAYLOAD, "name": "Active One", "targetSpend": "500000"},
    )
    project_repo.create(
        "dash-owner",
        {**_DEFAULT_CREATE_PAYLOAD, "name": "Active Two", "targetSpend": "250000"},
    )
    projects = project_repo.list_all_for_owner("dash-owner")
    payload = dashboard_payload(projects)
    assert payload["projectStatus"]["total"] == 2
    assert payload["kpis"][0]["value"] == "2"


def test_peek_next_code_does_not_insert_row(db_env):
    before, before_total = project_repo.list_for_owner("owner-1")
    preview = project_repo.peek_next_code()
    after, after_total = project_repo.list_for_owner("owner-1")
    assert preview.startswith("PRJ-")
    assert before_total == after_total
    assert len(before) == len(after)


def test_create_with_previewed_code_persists_code(db_env):
    preview = project_repo.peek_next_code()
    created = project_repo.create(
        "owner-1",
        {**_DEFAULT_CREATE_PAYLOAD, "projectId": preview, "name": "Previewed"},
    )
    assert created.code == preview


def test_create_without_code_auto_assigns(db_env):
    created = project_repo.create("owner-1", {**_DEFAULT_CREATE_PAYLOAD, "name": "Auto"})
    assert created.code.startswith("PRJ-")


def test_create_with_only_project_id_defaults_untitled(db_env):
    preview = project_repo.peek_next_code()
    created = project_repo.create("owner-1", {"projectId": preview})
    assert created.code == preview
    assert created.name == project_repo.UNTITLED
    assert created.workflow_entry_point == project_repo.UNTITLED
    assert created.business_process == project_repo.UNTITLED
    assert created.requester == project_repo.UNTITLED
    assert created.dept == project_repo.UNTITLED
    assert created.category == project_repo.UNTITLED
    assert created.region == project_repo.UNTITLED
    assert created.award_horizon == project_repo.UNTITLED
    assert created.description == project_repo.UNTITLED


def test_create_missing_workflow_defaults_untitled(db_env):
    created = project_repo.create("owner-1", {"name": "No workflow"})
    assert created.name == "No workflow"
    assert created.workflow_entry_point == project_repo.UNTITLED


def test_create_rejects_invalid_workflow_entry_point(db_env):
    with pytest.raises(project_repo.ProjectValidationError, match="workflowEntryPoint"):
        project_repo.create(
            "owner-1",
            {"name": "Bad workflow", "workflowEntryPoint": "Unknown"},
        )


def test_update_applies_real_values_and_skips_untitled(db_env):
    created = project_repo.create("owner-1", {"projectId": project_repo.peek_next_code()})
    updated = project_repo.update_for_owner(
        created.id,
        "owner-1",
        {"name": "Office Supplies", "workflowEntryPoint": "Sourcing"},
    )
    assert updated.name == "Office Supplies"
    assert updated.workflow_entry_point == "Sourcing"

    skipped = project_repo.update_for_owner(
        created.id,
        "owner-1",
        {"name": "untitled", "workflowEntryPoint": "", "businessProcess": "Direct"},
    )
    assert skipped.name == "Office Supplies"
    assert skipped.workflow_entry_point == "Sourcing"
    assert skipped.business_process == "Direct"


def test_project_to_dict_includes_new_fields(db_env):
    created = project_repo.create(
        "owner-1",
        {
            **_DEFAULT_CREATE_PAYLOAD,
            "name": "Full Fields",
            "businessProcess": "Direct",
            "requester": "Alex",
            "dept": "Procurement",
        },
    )
    row = project_repo.project_to_dict(created)
    assert row["workflowEntryPoint"] == "Sourcing"
    assert row["businessProcess"] == "Direct"
    assert row["requester"] == "Alex"
    assert row["dept"] == "Procurement"


def test_parse_and_store_corrupt_upload_does_not_raise(db_env):
    created = project_repo.create("owner-1", _DEFAULT_CREATE_PAYLOAD)
    upload = UploadFile(
        filename="Vendor_A.pdf",
        stream=io.BytesIO(b"%PDF-1.4 test"),
        content_type="application/pdf",
    )
    artifact = artifact_repo.create_upload(created.id, "owner-1", upload)
    parsed = parse_and_store(artifact)
    assert parsed.parse_status in {"error", "skipped"}
    assert parsed.parsed_json is None
    assert chunk_repo.list_for_artifact(parsed.id) == []


def test_parse_and_store_skips_unsupported_type(db_env):
    created = project_repo.create("owner-1", _DEFAULT_CREATE_PAYLOAD)
    upload = UploadFile(
        filename="notes.txt",
        stream=io.BytesIO(b"plain text notes"),
        content_type="text/plain",
    )
    artifact = artifact_repo.create_upload(created.id, "owner-1", upload)
    parsed = parse_and_store(artifact)
    assert parsed.parse_status == "skipped"
    assert parsed.parsed_json is None
    assert chunk_repo.list_for_artifact(parsed.id) == []


def test_parse_and_store_persists_final_json(db_env, monkeypatch):
    created = project_repo.create("owner-1", _DEFAULT_CREATE_PAYLOAD)
    upload = UploadFile(
        filename="Vendor_A.pdf",
        stream=io.BytesIO(b"%PDF-1.4 test"),
        content_type="application/pdf",
    )
    artifact = artifact_repo.create_upload(created.id, "owner-1", upload)

    class _Doc:
        chunks = [
            DocumentChunk(
                ordinal=0,
                chunk_type="text",
                text="[Vendor_A.pdf] Intro\nHello",
                token_count=8,
                heading_path=["Intro"],
                block_ids=["b_abc"],
                location={"page": 1},
            )
        ]

        def to_dict(self):
            return {
                "artifact_id": "sha256:deadbeefdeadbee",
                "source": "Vendor_A.pdf",
                "artifact_type": "pdf",
                "coord_system": "pdf_points_top_left",
                "metadata": {},
                "pages": [],
                "outline": [],
                "blocks": [],
                "warnings": [],
                "markdown": "# Vendor A",
            }

    monkeypatch.setattr(
        "services.artifact_parse.ArtifactHandler.parse",
        lambda self, *args, **kwargs: _Doc(),
    )

    parsed = parse_and_store(artifact)
    assert parsed.parse_status == "ok"
    payload = json.loads(parsed.parsed_json)
    for key in ("artifact_id", "blocks", "markdown", "pages", "outline"):
        assert key in payload
    assert "chunks" not in payload
    parsed_path = Path(db_env["data_root"]) / parsed.parsed_relpath
    assert parsed_path.is_file()
    assert json.loads(parsed_path.read_text(encoding="utf-8"))["markdown"] == "# Vendor A"

    stored = chunk_repo.list_for_artifact(parsed.id)
    assert len(stored) == 1
    assert stored[0].project_id == created.id
    assert stored[0].artifact_id == parsed.id
    assert stored[0].text == "[Vendor_A.pdf] Intro\nHello"
    assert stored[0].ordinal == 0
    project_chunks = chunk_repo.list_for_project(created.id)
    assert len(project_chunks) == 1
    assert project_chunks[0].id == stored[0].id

    artifact_repo.delete_for_owner(parsed.id, "owner-1")
    assert not parsed_path.exists()
    assert chunk_repo.list_for_artifact(parsed.id) == []
    assert chunk_repo.list_for_project(created.id) == []


def test_parse_and_store_clears_chunks_on_failed_reparse(db_env, monkeypatch):
    from shared.artifacts.exceptions import UnsupportedArtifact

    created = project_repo.create("owner-1", _DEFAULT_CREATE_PAYLOAD)
    upload = UploadFile(
        filename="Vendor_A.pdf",
        stream=io.BytesIO(b"%PDF-1.4 test"),
        content_type="application/pdf",
    )
    artifact = artifact_repo.create_upload(created.id, "owner-1", upload)

    class _Doc:
        chunks = [
            DocumentChunk(
                ordinal=0,
                chunk_type="text",
                text="[Vendor_A.pdf] Keep\nBody",
                token_count=6,
                heading_path=["Keep"],
                block_ids=["b_keep"],
                location={"page": 1},
            )
        ]

        def to_dict(self):
            return {
                "artifact_id": "sha256:deadbeefdeadbee",
                "source": "Vendor_A.pdf",
                "artifact_type": "pdf",
                "coord_system": "pdf_points_top_left",
                "metadata": {},
                "pages": [],
                "outline": [],
                "blocks": [],
                "warnings": [],
                "markdown": "# Keep",
            }

    monkeypatch.setattr(
        "services.artifact_parse.ArtifactHandler.parse",
        lambda self, *args, **kwargs: _Doc(),
    )
    parsed = parse_and_store(artifact)
    assert len(chunk_repo.list_for_artifact(parsed.id)) == 1

    def _skip(self, *args, **kwargs):
        raise UnsupportedArtifact("reparse skipped")

    monkeypatch.setattr("services.artifact_parse.ArtifactHandler.parse", _skip)
    retried = parse_and_store(parsed)
    assert retried.parse_status == "skipped"
    assert chunk_repo.list_for_artifact(retried.id) == []
    assert chunk_repo.list_for_project(created.id) == []


