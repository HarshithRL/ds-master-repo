"""UC volume directories/files via the Databricks Files API.

Databricks Apps does not expose a writable FUSE mount at ``/Volumes``. Local
``Path.mkdir`` fails with ``[Errno 13] Permission denied: '/Volumes'``.
Visitor OBO when bound (user WRITE VOLUME); else the app service principal.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import shutil

from shared.db.paths import db_backend
from shared.logger_global import get_logger

__all__ = [
    "delete_dir",
    "ensure_dir",
    "exists",
    "read_bytes",
    "read_text",
    "write_bytes",
    "write_text",
]

log = get_logger(__name__)


def _files_client():
    from shared.databricks_runtime import (
        obo_is_bound,
        request_workspace_client,
        workspace_client,
    )

    if obo_is_bound():
        return request_workspace_client()
    return workspace_client()


def ensure_dir(path: Path) -> None:
    if db_backend() != "uc":
        path.mkdir(parents=True, exist_ok=True)
        return
    _files_mkdirs(path)


def write_bytes(path: Path, data: bytes) -> None:
    if db_backend() != "uc":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return
    ensure_dir(path.parent)
    posix = path.as_posix()
    try:
        _files_client().files.upload(posix, BytesIO(data), overwrite=True)
    except Exception as exc:
        log.warning("uc volume write failed path={} exc_type={}: {}", posix, type(exc).__name__, exc)
        raise
    log.debug("uc volume wrote path={}", posix)


def write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    write_bytes(path, text.encode(encoding))


def read_bytes(path: Path) -> bytes:
    """Read file contents from a UC Volume (Files API) or local FS."""
    if db_backend() != "uc":
        return path.read_bytes()
    posix = path.as_posix()
    try:
        resp = _files_client().files.download(posix)
        return resp.contents.read()
    except Exception as exc:
        log.warning("uc volume read failed path={} exc_type={}: {}", posix, type(exc).__name__, exc)
        raise


def read_text(path: Path, *, encoding: str = "utf-8") -> str:
    """Read text from a UC Volume (Files API) or local FS."""
    return read_bytes(path).decode(encoding)


def exists(path: Path) -> bool:
    """Check whether a file or directory exists on UC Volume (Files API) or local FS."""
    if db_backend() != "uc":
        return path.exists()
    posix = path.as_posix()
    try:
        _files_client().files.get_metadata(posix)
        return True
    except Exception as exc:
        log.debug("uc volume not found path={} exc_type={}: {}", posix, type(exc).__name__, exc)
        return False


def delete_dir(path: Path) -> None:
    """Recursively remove a directory tree.

    Databricks Apps has no FUSE mount, so `shutil.rmtree` silently no-ops on a
    UC Volume path; and the Files API only deletes *empty* directories, so the
    contents have to be walked and removed first.
    """
    if db_backend() != "uc":
        shutil.rmtree(path, ignore_errors=True)
        return
    _files_rmtree(path.as_posix().rstrip("/"))


def _files_rmtree(posix: str) -> None:
    client = _files_client()
    try:
        entries = list(client.files.list_directory_contents(posix))
    except Exception as exc:
        log.warning("uc volume list failed path={}: {}", posix, exc)
        return
    for entry in entries:
        child = str(getattr(entry, "path", "") or "").rstrip("/")
        if not child or child == posix:
            continue
        if bool(getattr(entry, "is_directory", False)):
            _files_rmtree(child)
            continue
        try:
            client.files.delete(child)
        except Exception as exc:
            log.warning("uc volume file delete failed path={}: {}", child, exc)
    try:
        client.files.delete_directory(posix)
    except Exception as exc:
        log.warning("uc volume dir delete failed path={}: {}", posix, exc)


def _files_mkdirs(path: Path) -> None:
    posix = path.as_posix().rstrip("/")
    parts = [part for part in posix.split("/") if part]
    if len(parts) < 4 or parts[0] != "Volumes":
        raise RuntimeError(f"UC volume path must start with /Volumes/<catalog>/<schema>/<volume>: {posix}")

    from databricks.sdk.errors import DatabricksError, ResourceAlreadyExists

    client = _files_client()
    current = "/" + "/".join(parts[:4])
    for part in parts[4:]:
        current = f"{current}/{part}"
        try:
            client.files.create_directory(f"{current}/")
        except ResourceAlreadyExists:
            continue
        except DatabricksError as exc:
            if getattr(exc, "error_code", "") == "RESOURCE_ALREADY_EXISTS":
                continue
            raise
    log.debug("uc volume dir ready path={}", posix)
