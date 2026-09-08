from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


def file_artifact_id(source: str | Path | bytes) -> str:
    hasher = hashlib.sha256()
    if isinstance(source, bytes):
        hasher.update(source)
    else:
        path = Path(source)
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                hasher.update(chunk)
    return "sha256:" + hasher.hexdigest()[:16]


def make_block_id(
    *,
    block_type: str,
    text: str,
    page: int | str | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    sheet: str | None = None,
    extra_key: Any = None,
) -> str:
    _ = text
    payload = "|".join(
        (
            block_type,
            "" if page is None else str(page),
            _bbox_key(bbox),
            sheet or "",
            "" if extra_key is None else str(extra_key),
        )
    )
    return "b_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def _bbox_key(bbox: tuple[float, float, float, float] | None) -> str:
    if bbox is None:
        return ""
    return ",".join(f"{round(float(value), 1):.1f}" for value in bbox)
