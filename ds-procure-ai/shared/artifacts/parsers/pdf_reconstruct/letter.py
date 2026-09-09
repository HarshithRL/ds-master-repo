from __future__ import annotations

from ...models import BlockType, ContentBlock, SourceLocation
from ...blocks import make_content_block
from ..pdf_geometry import round_bbox
from ..pdf_headings import lines_to_blocks
from ..pdf_tables import PdfTableExtractor, table_to_text
from ..pdf_visuals import extract_visuals
from .base import ReconstructPage, lines_outside_tables, stamp_blocks
from .columns import column_groups, order_blocks


class LetterReconstructor:
    name = "letter"

    def reconstruct(
        self, ctx: ReconstructPage, start_index: int
    ) -> tuple[int, list[ContentBlock]]:
        index = start_index
        tables: list[tuple[list[list[str]], tuple[float, float, float, float], str]] = []
        if ctx.options.include_tables:
            tables = PdfTableExtractor().extract(
                ctx.page, ctx.path, ctx.page_index, ctx.kind, ctx.options.password
            )
        table_boxes = [bbox for _, bbox, _ in tables]
        leftover = lines_outside_tables(ctx.lines, table_boxes)

        blocks: list[ContentBlock] = []
        for table_i, (matrix, bbox, engine) in enumerate(tables):
            index += 1
            blocks.append(
                make_content_block(
                    seq_id=f"pdf-{index:04d}",
                    block_type=BlockType.TABLE,
                    text=table_to_text(matrix),
                    table=matrix,
                    location=SourceLocation(
                        page=ctx.page_no,
                        bbox=round_bbox(bbox),
                        page_width=ctx.width,
                        page_height=ctx.height,
                        table_index=table_i,
                    ),
                    extra={
                        "engine": engine,
                        "page_kind": ctx.kind,
                        "reconstructor": self.name,
                    },
                )
            )

        index, visual_blocks = extract_visuals(
            ctx.page, leftover, ctx.kind, ctx.page_no, table_boxes, index
        )
        blocks.extend(visual_blocks)

        groups, split_x = column_groups(leftover, ctx.width)
        text_blocks: list[ContentBlock] = []
        for group in groups:
            index, grouped = lines_to_blocks(
                group,
                ctx.kind,
                ctx.page_no,
                index,
                ctx.width,
                ctx.height,
                reconstructor=self.name,
            )
            text_blocks.extend(grouped)
        blocks.extend(text_blocks)
        stamp_blocks(blocks, reconstructor=self.name, page_kind=ctx.kind)
        return index, order_blocks(blocks, split_x)
