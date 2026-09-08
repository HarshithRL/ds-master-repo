from __future__ import annotations

from ...models import BlockType, ContentBlock
from ..pdf_headings import lines_to_blocks
from .base import ReconstructPage, fallback_text_or_ocr, stamp_blocks


class ScannedReconstructor:
    name = "scanned"

    def reconstruct(
        self, ctx: ReconstructPage, start_index: int
    ) -> tuple[int, list[ContentBlock]]:
        index = start_index
        index, blocks = lines_to_blocks(
            ctx.lines,
            ctx.kind,
            ctx.page_no,
            index,
            ctx.width,
            ctx.height,
            reconstructor=self.name,
        )
        has_text = any(block.type not in {BlockType.IMAGE, BlockType.CHART} for block in blocks)
        if not has_text:
            index, blocks = fallback_text_or_ocr(ctx, index, self.name)
            if not blocks:
                ctx.warnings.append(
                    f"Page {ctx.page_no} is a {ctx.kind} page with little extractable text."
                )
        stamp_blocks(blocks, reconstructor=self.name, page_kind=ctx.kind)
        return index, blocks
