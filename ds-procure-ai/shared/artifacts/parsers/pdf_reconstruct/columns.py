from __future__ import annotations

from ...models import ContentBlock
from ..pdf_layout import LayoutLine, sort_reading_lines

_MIN_GAP = 80.0
_MIN_LINES_PER_COLUMN = 3


def split_text_columns(
    lines: list[LayoutLine], page_width: float
) -> tuple[list[LayoutLine], list[LayoutLine], float] | None:
    if not lines or page_width <= 0:
        return None
    xs = sorted({round(line.bbox[0] / 20) * 20 for line in lines})
    if len(xs) < 4:
        return None
    gaps = [(xs[i + 1] - xs[i], i) for i in range(len(xs) - 1)]
    gap, idx = max(gaps)
    if gap < _MIN_GAP:
        return None
    split_x = (xs[idx] + xs[idx + 1]) / 2
    if split_x < page_width * 0.25 or split_x > page_width * 0.75:
        return None
    left = [line for line in lines if line.bbox[0] < split_x]
    right = [line for line in lines if line.bbox[0] >= split_x]
    if len(left) < _MIN_LINES_PER_COLUMN or len(right) < _MIN_LINES_PER_COLUMN:
        return None
    return sort_reading_lines(left), sort_reading_lines(right), split_x


def column_groups(
    lines: list[LayoutLine], page_width: float
) -> tuple[list[list[LayoutLine]], float | None]:
    split = split_text_columns(lines, page_width)
    if split is None:
        return [sort_reading_lines(lines)], None
    left, right, split_x = split
    return [left, right], split_x


def order_blocks(
    blocks: list[ContentBlock], split_x: float | None
) -> list[ContentBlock]:
    def key(block: ContentBlock) -> tuple[int, float, float]:
        bbox = block.location.bbox
        if bbox is None:
            return (0, 10_000.0, 0.0)
        column = 0 if split_x is None or bbox[0] < split_x else 1
        return (column, bbox[1], bbox[0])

    return sorted(blocks, key=key)
