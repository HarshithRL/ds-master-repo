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


def _files_client():
    from shared.databricks_runtime import (
        obo_is_bound,
        obo_token_scopes,
        request_workspace_client,
        workspace_client,
    )

    # Visitor OBO owns this data (per-user WRITE VOLUME) — the app SP is not
    # a fallback identity for volume access; it has no grants here by design.
    # scopes is logged only for diagnosis of *why* OBO fails, not to gate it.
    bound = obo_is_bound()
    scopes = obo_token_scopes() if bound else []
    log.warning("TRACE_TMP files_client bound={} scopes={}", bound, scopes)
    if bound:
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
        log.warning("TRACE_TMP write_bytes() ok path={} bytes={}", posix, len(data))
    except Exception as exc:
        log.warning("TRACE_TMP write_bytes() FAILED path={} exc_type={} exc={}", posix, type(exc).__name__, exc)
        raise


def write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    write_bytes(path, text.encode(encoding))


def read_bytes(path: Path) -> bytes:
    """Read file contents from a UC Volume (Files API) or local FS."""
    if db_backend() != "uc":
        return path.read_bytes()
    posix = path.as_posix()
    try:
        resp = _files_client().files.download(posix)
        data = resp.contents.read()
        log.warning("TRACE_TMP read_bytes() ok path={} bytes={}", posix, len(data))
        return data
    except Exception as exc:
        log.warning("TRACE_TMP read_bytes() FAILED path={} exc_type={} exc={}", posix, type(exc).__name__, exc)
        raise


def read_text(path: Path, *, encoding: str = "utf-8") -> str:
    """Read text from a UC Volume (Files API) or local FS."""
    return read_bytes(path).decode(encoding)


def exists(path: Path) -> bool:
    """Check whether a file or directory exists on UC Volume (Files API) or local FS."""
    log.warning("TRACE_TMP exists() db_backend={} path={}", db_backend(), path)
    if db_backend() != "uc":
        return path.exists()
    posix = path.as_posix()
    try:
        _files_client().files.get_status(posix)
        log.warning("TRACE_TMP exists() -> True path={}", posix)
        return True
    except Exception as exc:
        log.warning("TRACE_TMP exists() -> False path={} exc_type={} exc={}", posix, type(exc).__name__, exc)
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
