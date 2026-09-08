from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from ...blocks import make_content_block
from ...models import BlockType, ContentBlock, ParseOptions, SourceLocation
from ..pdf_geometry import covered_by_any, round_bbox
from ..pdf_layout import LayoutLine, PdfTextNormalizer
from ..pdf_ocr import PdfOcrFallback


@dataclass
class ReconstructPage:
    page: Any
    page_no: int
    page_index: int
    kind: str
    width: float
    height: float
    path: Path
    options: ParseOptions
    lines: list[LayoutLine]
    warnings: list[str] = field(default_factory=list)


class PdfReconstructor(Protocol):
    name: str

    def reconstruct(
        self, ctx: ReconstructPage, start_index: int
    ) -> tuple[int, list[ContentBlock]]:
        ...


def stamp_blocks(
    blocks: list[ContentBlock], *, reconstructor: str, page_kind: str
) -> list[ContentBlock]:
    for block in blocks:
        block.extra["reconstructor"] = reconstructor
        block.extra.setdefault("page_kind", page_kind)
    return blocks


def lines_outside_tables(
    lines: list[LayoutLine],
    table_boxes: list[tuple[float, float, float, float]],
) -> list[LayoutLine]:
    if not table_boxes:
        return list(lines)
    return [line for line in lines if not covered_by_any(line.bbox, table_boxes)]


def fallback_text_or_ocr(
    ctx: ReconstructPage,
    start_index: int,
    reconstructor: str,
) -> tuple[int, list[ContentBlock]]:
    index = start_index
    if ctx.options.use_ocr:
        ocr_text = PdfOcrFallback().extract(ctx.page, ctx.warnings, ctx.page_no)
        if ocr_text:
            index, block = PdfOcrFallback().as_block(
                ocr_text, ctx.page_no, ctx.width, ctx.height, ctx.kind, index
            )
            stamp_blocks([block], reconstructor=reconstructor, page_kind=ctx.kind)
            return index, [block]
    fallback = PdfTextNormalizer().normalize(ctx.page.get_text("text") or "")
    if not fallback:
        return index, []
    index += 1
    block = make_content_block(
        seq_id=f"pdf-{index:04d}",
        block_type=BlockType.TEXT,
        text=fallback,
        location=SourceLocation(
            page=ctx.page_no,
            bbox=round_bbox((0.0, 0.0, ctx.width, ctx.height)),
            page_width=ctx.width,
            page_height=ctx.height,
        ),
        extra={"engine": "pymupdf.text", "page_kind": ctx.kind, "reconstructor": reconstructor},
    )
    return index, [block]
