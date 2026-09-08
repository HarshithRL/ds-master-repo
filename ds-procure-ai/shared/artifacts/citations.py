from __future__ import annotations

from typing import Any

from .models import ContentBlock, COORD_PDF_POINTS


def citation_from_block(
    block: ContentBlock,
    artifact_id: str,
    coord_system: str = COORD_PDF_POINTS,
    quote: str | None = None,
) -> dict[str, Any]:
    location = block.location
    text = (quote if quote is not None else block.text).strip()
    if "\n" in text:
        text = text.split("\n", 1)[0].strip()
    return {
        "block_id": block.block_id,
        "artifact_id": artifact_id,
        "type": block.type.value,
        "page": location.page,
        "bbox": [round(float(v), 1) for v in location.bbox] if location.bbox else None,
        "page_width": round(float(location.page_width), 1) if location.page_width is not None else None,
        "page_height": round(float(location.page_height), 1) if location.page_height is not None else None,
        "coord_system": coord_system,
        "heading_path": list(block.heading_path),
        "quote": text,
    }
