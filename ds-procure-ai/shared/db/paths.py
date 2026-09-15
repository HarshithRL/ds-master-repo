"""Local file storage path conventions (bytes live under data/projects or UC volume)."""

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


def db_backend() -> str:
    """Mate app-data backend: sqlite (default) or uc."""
    raw = os.getenv("MATE_DB_BACKEND", "sqlite").strip().lower()
    return "uc" if raw == "uc" else "sqlite"


def uc_catalog() -> str:
    return os.getenv("MATE_UC_CATALOG", "").strip()


def uc_schema() -> str:
    return os.getenv("MATE_UC_SCHEMA", "bronze").strip() or "bronze"


def uc_volume() -> str:
    return os.getenv("MATE_UC_VOLUME", "bronze_volume").strip() or "bronze_volume"


def uc_volume_root() -> Path:
    """FUSE path for the Mate files volume: /Volumes/{catalog}/bronze/bronze_volume/mate."""
    catalog = uc_catalog()
    if not catalog:
        raise RuntimeError("MATE_UC_CATALOG is required when MATE_DB_BACKEND=uc")
    return Path("/Volumes") / catalog / uc_schema() / uc_volume() / "mate"


def projects_data_root() -> Path:
    if db_backend() == "uc":
        return uc_volume_root()
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
