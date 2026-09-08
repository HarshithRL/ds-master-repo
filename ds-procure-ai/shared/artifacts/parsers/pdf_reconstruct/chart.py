from __future__ import annotations

import re

from ...blocks import make_content_block
from ...models import BlockType, ContentBlock, SourceLocation
from ..pdf_geometry import round_bbox, union_bbox
from ..pdf_headings import lines_to_blocks
from ..pdf_visuals import extract_visuals, nearest_caption
from .base import ReconstructPage, stamp_blocks

_INVENTED_SCORE = re.compile(r"\b(9\d|/100)\b")


class ChartReconstructor:
    name = "chart"

    def reconstruct(
        self, ctx: ReconstructPage, start_index: int
    ) -> tuple[int, list[ContentBlock]]:
        index = start_index
        index, visuals = extract_visuals(
            ctx.page, ctx.lines, "chart", ctx.page_no, [], index
        )
        visual_blocks = [
            block for block in visuals if block.type in {BlockType.IMAGE, BlockType.CHART}
        ]
        blocks: list[ContentBlock] = []
        if visual_blocks:
            index, chart_block = _merge_visuals(visual_blocks, ctx, index)
            blocks.append(chart_block)
        else:
            index += 1
            caption = _safe_caption(nearest_caption(ctx.lines, (0.0, 0.0, ctx.width, ctx.height)))
            text = f"{caption}\n[chart]".strip() if caption else "[chart]"
            blocks.append(
                make_content_block(
                    seq_id=f"pdf-{index:04d}",
                    block_type=BlockType.CHART,
                    text=text,
                    location=SourceLocation(
                        page=ctx.page_no,
                        bbox=round_bbox((0.0, 0.0, ctx.width, ctx.height * 0.7)),
                        page_width=ctx.width,
                        page_height=ctx.height,
                    ),
                    extra={
                        "engine": "pymupdf",
                        "page_kind": ctx.kind,
                        "reconstructor": self.name,
                    },
                )
            )

        caption_text = {block.text.split("\n", 1)[0].strip() for block in blocks}
        leftover = [
            line
            for line in ctx.lines
            if line.text.strip() not in caption_text and not _INVENTED_SCORE.search(line.text)
        ]
        index, text_blocks = lines_to_blocks(
            leftover,
            ctx.kind,
            ctx.page_no,
            index,
            ctx.width,
            ctx.height,
            reconstructor=self.name,
        )
        blocks.extend(text_blocks)
        stamp_blocks(blocks, reconstructor=self.name, page_kind=ctx.kind)
        return index, blocks


def _merge_visuals(
    visuals: list[ContentBlock], ctx: ReconstructPage, index: int
) -> tuple[int, ContentBlock]:
    boxes = [block.location.bbox for block in visuals if block.location.bbox]
    bbox = round_bbox(union_bbox(boxes)) if boxes else round_bbox((0.0, 0.0, ctx.width, ctx.height))
    captions = []
    for block in visuals:
        first = block.text.split("\n", 1)[0].strip()
        if first and first not in {"[chart]", "[image]"} and not _INVENTED_SCORE.search(first):
            captions.append(first)
    caption = _safe_caption(captions[0] if captions else nearest_caption(ctx.lines, bbox))
    text = f"{caption}\n[chart]".strip() if caption else "[chart]"
    index += 1
    return index, make_content_block(
        seq_id=f"pdf-{index:04d}",
        block_type=BlockType.CHART,
        text=text,
        location=SourceLocation(
            page=ctx.page_no,
            bbox=bbox,
            page_width=ctx.width,
            page_height=ctx.height,
        ),
        extra={
            "engine": "pymupdf",
            "page_kind": ctx.kind,
            "reconstructor": "chart",
        },
    )


def _safe_caption(text: str) -> str:
    stripped = (text or "").strip()
    if not stripped or _INVENTED_SCORE.search(stripped):
        return ""
    return stripped
