"""Repo-relative sqlite and project data paths must ignore process cwd."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_sqlite_path_relative_uses_repo_root_not_cwd(tmp_path, monkeypatch):
    from shared.db.connection import sqlite_path

    monkeypatch.setenv("MATE_SQLITE_PATH", "data/studio/mate.sqlite")
    elsewhere = tmp_path / "flask-cwd"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert sqlite_path() == (REPO_ROOT / "data" / "studio" / "mate.sqlite").resolve()


def test_sqlite_path_absolute_unchanged(tmp_path, monkeypatch):
    from shared.db.connection import sqlite_path

    target = tmp_path / "abs" / "mate.sqlite"
    monkeypatch.setenv("MATE_SQLITE_PATH", str(target))
    monkeypatch.chdir(tmp_path)
    assert sqlite_path() == target.resolve()


def test_projects_data_root_relative_uses_repo_root_not_cwd(tmp_path, monkeypatch):
    from shared.db.paths import projects_data_root

    monkeypatch.setenv("MATE_PROJECTS_DATA_ROOT", "data/studio/projects")
    elsewhere = tmp_path / "brain-cwd"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert projects_data_root() == (REPO_ROOT / "data" / "studio" / "projects").resolve()


def test_pack_store_uses_shared_projects_data_root(tmp_path, monkeypatch):
    from ai_brain.core.procurement_ai.packs import store as pack_store
    from shared.db.paths import projects_data_root

    monkeypatch.setenv("MATE_PROJECTS_DATA_ROOT", "data/studio/projects")
    monkeypatch.chdir(tmp_path)
    assert pack_store.projects_data_root() == projects_data_root()
