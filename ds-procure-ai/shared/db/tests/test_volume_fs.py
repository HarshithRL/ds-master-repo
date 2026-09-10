"""UC volume Files API helpers (no FUSE mkdir on /Volumes)."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from databricks.sdk.errors import ResourceAlreadyExists

from shared.db import volume_fs


def test_ensure_dir_uses_local_mkdir_for_sqlite(tmp_path, monkeypatch):
    monkeypatch.delenv("MATE_DB_BACKEND", raising=False)
    target = tmp_path / "proj" / "uploads"
    volume_fs.ensure_dir(target)
    assert target.is_dir()


def test_ensure_dir_uses_files_api_for_uc(monkeypatch):
    monkeypatch.setenv("MATE_DB_BACKEND", "uc")
    created: list[str] = []

    class _Files:
        def create_directory(self, directory_path: str) -> None:
            created.append(directory_path)

    monkeypatch.setattr(
        "shared.databricks_runtime.workspace_client",
        lambda: SimpleNamespace(files=_Files()),
    )
    volume_fs.ensure_dir(
        Path("/Volumes/automation_d/bronze/bronze_volume/mate/proj-1/uploads")
    )
    assert created == [
        "/Volumes/automation_d/bronze/bronze_volume/mate/",
        "/Volumes/automation_d/bronze/bronze_volume/mate/proj-1/",
        "/Volumes/automation_d/bronze/bronze_volume/mate/proj-1/uploads/",
    ]


def test_ensure_dir_ignores_already_exists(monkeypatch):
    monkeypatch.setenv("MATE_DB_BACKEND", "uc")

    class _Files:
        def create_directory(self, directory_path: str) -> None:
            raise ResourceAlreadyExists("exists")

    monkeypatch.setattr(
        "shared.databricks_runtime.workspace_client",
        lambda: SimpleNamespace(files=_Files()),
    )
    volume_fs.ensure_dir(Path("/Volumes/automation_d/bronze/bronze_volume/mate/p1"))


def test_write_bytes_uploads_via_files_api(monkeypatch):
    monkeypatch.setenv("MATE_DB_BACKEND", "uc")
    uploaded: dict[str, bytes] = {}

    class _Files:
        def create_directory(self, directory_path: str) -> None:
            return None

        def upload(self, file_path: str, contents: BytesIO, overwrite: bool = False) -> None:
            uploaded["path"] = file_path
            uploaded["data"] = contents.read()
            uploaded["overwrite"] = overwrite

    monkeypatch.setattr(
        "shared.databricks_runtime.workspace_client",
        lambda: SimpleNamespace(files=_Files()),
    )
    volume_fs.write_bytes(
        Path("/Volumes/automation_d/bronze/bronze_volume/mate/p1/uploads/a.bin"),
        b"hello",
    )
    assert uploaded["path"] == "/Volumes/automation_d/bronze/bronze_volume/mate/p1/uploads/a.bin"
    assert uploaded["data"] == b"hello"
    assert uploaded["overwrite"] is True
