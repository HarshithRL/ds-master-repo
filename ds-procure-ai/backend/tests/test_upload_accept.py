"""Upload accept path: HTTP 202, pending parse, no inline parse_and_store."""

from __future__ import annotations

import io
import shutil
import tempfile
import time
from pathlib import Path

import pytest
from flask import Flask

from shared.db import init_db
from shared.db import connection as db_connection
from shared.db.repos import artifacts as artifact_repo
from shared.db.repos import projects as project_repo
from shared.db.repos.artifacts import UploadFile
from shared.db.repos.users import upsert_user_from_identity

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
    yield {"db_path": db_path, "data_root": data_root}
    if db_connection._engine is not None:
        db_connection._engine.dispose()
    db_connection._engine = None
    db_connection._SessionLocal = None
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture()
def client(db_env, monkeypatch):
    monkeypatch.setattr("routes.procurement.require_workspace_id", lambda: "owner-1")
    from routes.procurement import procurement_bp

    app = Flask(__name__)
    app.secret_key = "test"
    app.config["TESTING"] = True
    app.register_blueprint(procurement_bp)
    return app.test_client()


def _create_project():
    return project_repo.create("owner-1", _DEFAULT_CREATE_PAYLOAD)


def _post_upload(client, project_id, filename="Vendor_A.pdf", payload=b"%PDF-1.4 test"):
    return client.post(
        f"/api/procurement/projects/{project_id}/files",
        data={"files": (io.BytesIO(payload), filename)},
        content_type="multipart/form-data",
    )


def test_create_upload_sets_parse_status_pending(db_env):
    created = _create_project()
    artifact = artifact_repo.create_upload(
        created.id,
        "owner-1",
        UploadFile(filename="Vendor_A.pdf", stream=io.BytesIO(b"%PDF-1.4"), content_type="application/pdf"),
    )
    assert artifact.parse_status == "pending"


def test_upload_returns_202_without_inline_parse(client, db_env, monkeypatch):
    created = _create_project()
    parse_calls: list[str] = []
    enqueued: list[tuple[str, list[str]]] = []

    def fake_parse(artifact):
        parse_calls.append(artifact.id)
        return artifact

    def fake_enqueue(project_id, artifact_ids):
        enqueued.append((project_id, list(artifact_ids)))

    monkeypatch.setattr("routes.procurement.enqueue_ingest", fake_enqueue)
    monkeypatch.setattr("services.artifact_parse.parse_and_store", fake_parse)
    monkeypatch.setattr("ai_brain.core.kb.ingest._parse_and_store", fake_parse)
    monkeypatch.setattr("routes.procurement.parse_and_store", fake_parse, raising=False)

    response = _post_upload(client, created.id)
    body = response.get_json()

    assert response.status_code == 202
    assert parse_calls == []
    assert len(enqueued) == 1
    assert enqueued[0][0] == created.id
    assert body["uploaded"][0]["parseStatus"] == "pending"
    assert body["uploaded"][0]["name"] == "Vendor_A.pdf"


def test_upload_accept_under_one_second_when_parse_is_slow(client, db_env, monkeypatch):
    created = _create_project()

    def slow_parse(artifact):
        time.sleep(1.2)
        return artifact

    threads: list = []

    def tracking_enqueue(project_id, artifact_ids):
        from ai_brain.core.kb.ingest import enqueue_ingest as real_enqueue

        thread = real_enqueue(project_id, artifact_ids)
        threads.append(thread)
        return thread

    monkeypatch.setattr("routes.procurement.parse_and_store", slow_parse, raising=False)
    monkeypatch.setattr("services.artifact_parse.parse_and_store", slow_parse)
    monkeypatch.setattr("ai_brain.core.kb.ingest._parse_and_store", slow_parse)
    monkeypatch.setattr("routes.procurement.enqueue_ingest", tracking_enqueue)

    started = time.perf_counter()
    response = _post_upload(client, created.id)
    elapsed = time.perf_counter() - started

    assert response.status_code == 202
    assert elapsed < 1.0
    assert response.get_json()["uploaded"][0]["parseStatus"] == "pending"
    for thread in threads:
        thread.join(timeout=5)
