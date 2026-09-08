from __future__ import annotations

import re

from ...blocks import make_content_block
from ...models import BlockType, ContentBlock, SourceLocation
from ..pdf_geometry import overlap_ratio, round_bbox, union_bbox
from ..pdf_headings import lines_to_blocks
from ..pdf_layout import LayoutLine
from ..pdf_tables import MAX_TABLES_PER_PAGE, PdfTableExtractor, table_to_text
from .base import ReconstructPage, lines_outside_tables, stamp_blocks

_YEAR = re.compile(r"^(19|20)\d{2}$")


class GridReconstructor:
    name = "grid"

    def reconstruct(
        self, ctx: ReconstructPage, start_index: int
    ) -> tuple[int, list[ContentBlock]]:
        index = start_index
        tables: list[tuple[list[list[str]], tuple[float, float, float, float], str]] = []
        if ctx.options.include_tables:
            tables = PdfTableExtractor().extract(
                ctx.page, ctx.path, ctx.page_index, "table", ctx.options.password
            )
        leftover = lines_outside_tables(ctx.lines, [bbox for _, bbox, _ in tables])
        year_source = ctx.lines if _has_year_headers(ctx.lines) else leftover
        if _has_year_headers(year_source) or _looks_like_grid_chips(leftover):
            rebuilt = rebuild_table_from_lines(year_source)
            if rebuilt is not None:
                matrix, bbox = rebuilt
                tables = _replace_overlapping(tables, matrix, bbox)
                leftover = []
            elif leftover:
                leftover = [line for line in leftover if not _looks_like_cell_chip(line)]
        else:
            leftover = [line for line in leftover if not _looks_like_cell_chip(line)]

        blocks: list[ContentBlock] = []
        for table_i, (matrix, bbox, engine) in enumerate(tables[:MAX_TABLES_PER_PAGE]):
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

        if leftover:
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
        blocks.sort(key=_yx)
        return index, blocks


def rebuild_table_from_lines(
    lines: list[LayoutLine],
) -> tuple[list[list[str]], tuple[float, float, float, float]] | None:
    if len(lines) < 8:
        return None
    col_xs = _column_anchors(lines)
    row_ys = _cluster_positions(
        [(line.bbox[1] + line.bbox[3]) / 2 for line in lines], gap=8.0
    )
    if len(col_xs) < 2 or len(row_ys) < 3:
        return None
    matrix = [["" for _ in col_xs] for _ in row_ys]
    for line in lines:
        col = _nearest_index(col_xs, (line.bbox[0] + line.bbox[2]) / 2)
        row = _nearest_index(row_ys, (line.bbox[1] + line.bbox[3]) / 2)
        if matrix[row][col]:
            matrix[row][col] = f"{matrix[row][col]} {line.text}".strip()
        else:
            matrix[row][col] = line.text
    cleaned = _clean_keep_year_columns(matrix)
    if len(cleaned) < 2 or max(len(row) for row in cleaned) < 2:
        return None
    return cleaned, round_bbox(union_bbox([line.bbox for line in lines]))


def _column_anchors(lines: list[LayoutLine]) -> list[float]:
    year_lines = [line for line in lines if _YEAR.match(line.text.strip())]
    if len(year_lines) < 3:
        return _cluster_positions([line.bbox[0] for line in lines], gap=24.0)
    year_centers = _cluster_positions(
        [(line.bbox[0] + line.bbox[2]) / 2 for line in year_lines], gap=16.0
    )
    left_edge = min(year_centers) - 20
    label_xs = [
        line.bbox[0]
        for line in lines
        if (line.bbox[0] + line.bbox[2]) / 2 < left_edge
    ]
    if label_xs:
        return [min(label_xs), *year_centers]
    return year_centers


def _clean_keep_year_columns(matrix: list[list[str]]) -> list[list[str]]:
    rows = [row for row in matrix if any(cell.strip() for cell in row)]
    if not rows:
        return []
    width = max(len(row) for row in rows)
    padded = [row + [""] * (width - len(row)) for row in rows]
    year_cols = {
        col
        for col in range(width)
        if any(_YEAR.match((row[col] or "").strip()) for row in padded)
    }
    keep = [
        col
        for col in range(width)
        if col in year_cols or any((row[col] or "").strip() for row in padded)
    ]
    if not keep:
        return []
    return [[row[col] for col in keep] for row in padded]


def _has_year_headers(lines: list[LayoutLine]) -> bool:
    years = sorted(
        {int(line.text.strip()) for line in lines if _YEAR.match(line.text.strip())}
    )
    if len(years) < 3:
        return False
    return sum(1 for a, b in zip(years, years[1:]) if b - a == 1) >= 2


def _looks_like_grid_chips(lines: list[LayoutLine]) -> bool:
    if _has_year_headers(lines) and len(lines) >= 8:
        return True
    if len(lines) < 12:
        return False
    short = sum(1 for line in lines if len(line.text) < 40)
    return short / len(lines) >= 0.8


def _looks_like_cell_chip(line: LayoutLine) -> bool:
    text = line.text.strip()
    return len(text) < 24 and not text.endswith((".", ":", ";"))


def _replace_overlapping(
    tables: list[tuple[list[list[str]], tuple[float, float, float, float], str]],
    matrix: list[list[str]],
    bbox: tuple[float, float, float, float],
) -> list[tuple[list[list[str]], tuple[float, float, float, float], str]]:
    kept = [
        table
        for table in tables
        if overlap_ratio(table[1], bbox) < 0.4
    ]
    kept.append((matrix, bbox, "reconstruct.grid"))
    return kept


def _cluster_positions(values: list[float], gap: float) -> list[float]:
    if not values:
        return []
    ordered = sorted(values)
    clusters: list[list[float]] = [[ordered[0]]]
    for value in ordered[1:]:
        if value - clusters[-1][-1] <= gap:
            clusters[-1].append(value)
        else:
            clusters.append([value])
    return [sum(cluster) / len(cluster) for cluster in clusters]


def _nearest_index(centers: list[float], value: float) -> int:
    return min(range(len(centers)), key=lambda index: abs(centers[index] - value))


def _yx(block: ContentBlock) -> tuple[float, float]:
    bbox = block.location.bbox
    if bbox is None:
        return (10_000.0, 0.0)
    return (bbox[1], bbox[0])
