from __future__ import annotations

from ...models import ContentBlock
from ..pdf_headings import lines_to_blocks, merge_cover_titles
from ..pdf_visuals import extract_visuals
from .base import ReconstructPage, fallback_text_or_ocr, stamp_blocks


class CoverReconstructor:
    name = "cover"

    def reconstruct(
        self, ctx: ReconstructPage, start_index: int
    ) -> tuple[int, list[ContentBlock]]:
        index = start_index
        lines = merge_cover_titles(ctx.lines, "design")
        index, visual_blocks = extract_visuals(
            ctx.page, lines, "design", ctx.page_no, [], index
        )
        index, text_blocks = lines_to_blocks(
            lines,
            ctx.kind,
            ctx.page_no,
            index,
            ctx.width,
            ctx.height,
            reconstructor=self.name,
        )
        blocks: list[ContentBlock] = [*visual_blocks, *text_blocks]
        if not blocks:
            index, blocks = fallback_text_or_ocr(ctx, index, self.name)
            if not blocks:
                ctx.warnings.append(
                    f"Page {ctx.page_no} is a {ctx.kind} page with little extractable text."
                )
        stamp_blocks(blocks, reconstructor=self.name, page_kind=ctx.kind)
        return index, blocks
