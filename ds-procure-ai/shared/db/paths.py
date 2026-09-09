"""Local file storage path conventions (bytes live under data/projects)."""

from __future__ import annotations

import os
from pathlib import Path

from shared.bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path()

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DATA_ROOT = _REPO_ROOT / "data" / "projects"


def resolve_under_repo(raw: str) -> Path:
    """Resolve a path against the repo root so Flask cwd vs brain cwd cannot split storage."""
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = _REPO_ROOT / path
    return path.resolve()


def projects_data_root() -> Path:
    override = os.getenv("MATE_PROJECTS_DATA_ROOT", "").strip()
    if override:
        return resolve_under_repo(override)
    return _DEFAULT_DATA_ROOT


def project_root(project_id: str) -> Path:
    return projects_data_root() / project_id


def artifact_storage_relpath(project_id: str, artifact_id: str, original_name: str) -> str:
    safe_name = Path(original_name).name
    return f"{project_id}/uploads/{artifact_id}_{safe_name}"


def parsed_storage_relpath(project_id: str, artifact_id: str) -> str:
    return f"{project_id}/parsed/{artifact_id}.json"


def artifact_absolute_path(storage_relpath: str) -> Path:
    return projects_data_root() / storage_relpath
