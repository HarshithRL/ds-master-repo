from __future__ import annotations

from typing import Any

from .ids import make_block_id
from .models import BlockType, ContentBlock, SourceLocation


def make_content_block(
    *,
    seq_id: str,
    block_type: BlockType,
    text: str,
    location: SourceLocation | None = None,
    table: list[list[str]] | None = None,
    extra: dict[str, Any] | None = None,
    level: int | None = None,
    heading_path: list[str] | None = None,
) -> ContentBlock:
    loc = location or SourceLocation()
    page_key: int | str | None = loc.page
    if page_key is None:
        page_key = loc.slide
    extra_key = loc.cell_range or loc.shape_id or loc.paragraph_index or loc.table_index
    return ContentBlock(
        id=seq_id,
        block_id=make_block_id(
            block_type=block_type.value,
            text=text,
            page=page_key,
            bbox=loc.bbox,
            sheet=loc.sheet,
            extra_key=extra_key,
        ),
        type=block_type,
        text=text,
        location=loc,
        table=table,
        extra=extra or {},
        level=level,
        heading_path=list(heading_path or []),
    )
