"""UC volume directories/files via the Databricks Files API.

Databricks Apps does not expose a writable FUSE mount at ``/Volumes``. Local
``Path.mkdir`` fails with ``[Errno 13] Permission denied: '/Volumes'``.
Visitor OBO when bound (user WRITE VOLUME); else the app service principal.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from shared.db.paths import db_backend
from shared.logger_global import get_logger

__all__ = [
    "ensure_dir",
    "exists",
    "read_bytes",
    "read_text",
    "write_bytes",
    "write_text",
]

log = get_logger(__name__)

_FILES_SCOPE = "files.files"


def _files_client():
    from shared.databricks_runtime import (
        obo_is_bound,
        obo_token_scopes,
        request_workspace_client,
        workspace_client,
    )

    # Mirror shared/db/connection.py's _SQL_SCOPE check: only trust the
    # visitor OBO token for the Files API if it actually carries the
    # files.files scope. An app deploy/update that hasn't (re)granted this
    # scope yet still issues OBO tokens without it — using them anyway
    # causes every volume read/write to fail permission checks, which
    # exists()/read_text() then swallow, masking real data as "not found".
    if obo_is_bound() and _FILES_SCOPE in obo_token_scopes():
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
    _files_client().files.upload(posix, BytesIO(data), overwrite=True)
    log.debug("uc volume wrote path={}", posix)


def write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    write_bytes(path, text.encode(encoding))


def read_bytes(path: Path) -> bytes:
    """Read file contents from a UC Volume (Files API) or local FS."""
    if db_backend() != "uc":
        return path.read_bytes()
    posix = path.as_posix()
    resp = _files_client().files.download(posix)
    return resp.contents.read()


def read_text(path: Path, *, encoding: str = "utf-8") -> str:
    """Read text from a UC Volume (Files API) or local FS."""
    return read_bytes(path).decode(encoding)


def exists(path: Path) -> bool:
    """Check whether a file or directory exists on UC Volume (Files API) or local FS."""
    if db_backend() != "uc":
        return path.exists()
    posix = path.as_posix()
    try:
        _files_client().files.get_status(posix)
        return True
    except Exception as exc:
        log.debug("uc volume exists check failed path={}: {}", posix, exc)
        return False


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
