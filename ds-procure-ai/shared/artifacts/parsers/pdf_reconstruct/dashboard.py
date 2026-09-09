from __future__ import annotations

import re
from collections.abc import Callable

from ...blocks import make_content_block
from ...models import BlockType, ContentBlock, SourceLocation
from ..pdf_geometry import contained_in, overlap_ratio, round_bbox, union_bbox
from ..pdf_layout import LayoutLine
from ..pdf_tables import PdfTableExtractor, table_to_text
from ..pdf_visuals import extract_visuals
from .base import ReconstructPage, lines_outside_tables, stamp_blocks

_SCORE_LETTER = re.compile(r"^[A-E][+-]?$")
_TRAILING_DASH = re.compile(r"^\d+-$")
_DECIMAL_VALUE = re.compile(r"^\d+[.,]\d+$")


def cluster_tiles(
    lines: list[LayoutLine],
    page: object | None = None,
    page_width: float = 0.0,
    page_height: float = 0.0,
) -> list[list[LayoutLine]]:
    if not lines:
        return []
    assigned: dict[int, int] = {}
    drawing_tiles: list[list[LayoutLine]] = []
    boxes = _tile_boxes_from_drawings(page, page_width, page_height) if page is not None else []
    for line in lines:
        box_index = _containing_tile(line, boxes)
        if box_index is None:
            continue
        while len(drawing_tiles) <= box_index:
            drawing_tiles.append([])
        drawing_tiles[box_index].append(line)
        assigned[id(line)] = box_index
    leftover = [line for line in lines if id(line) not in assigned]
    tiles: list[list[LayoutLine]] = []
    for group in drawing_tiles:
        if group:
            tiles.extend(_extract_kpi_pairs(group))
    tiles.extend(_extract_kpi_pairs(leftover))
    return [group for group in tiles if group]


def tile_text(lines: list[LayoutLine]) -> str:
    used: set[int] = set()
    ordered = sorted(lines, key=lambda line: (round(line.bbox[1] / 4), line.bbox[0]))
    parts: list[str] = []
    for current in ordered:
        if id(current) in used:
            continue
        if _is_label(current.text):
            partner = _nearest_value(current, ordered, used)
            if partner is not None:
                parts.append(f"{current.text.strip()} {partner.text.strip()}")
                used.add(id(current))
                used.add(id(partner))
                continue
        parts.append(current.text.strip())
        used.add(id(current))
    return " ".join(part for part in parts if part)


class DashboardReconstructor:
    name = "dashboard"

    def reconstruct(
        self, ctx: ReconstructPage, start_index: int
    ) -> tuple[int, list[ContentBlock]]:
        index = start_index
        tables: list[tuple[list[list[str]], tuple[float, float, float, float], str]] = []
        if ctx.options.include_tables:
            for matrix, bbox, engine in PdfTableExtractor().extract(
                ctx.page, ctx.path, ctx.page_index, ctx.kind, ctx.options.password
            ):
                if len(matrix) >= 3 and max(len(row) for row in matrix) >= 3:
                    tables.append((matrix, bbox, engine))
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
            ctx.page, leftover, "dashboard", ctx.page_no, table_boxes, index
        )
        blocks.extend(visual_blocks)

        tiles = cluster_tiles(leftover, ctx.page, ctx.width, ctx.height)
        tiles.sort(key=_tile_origin)
        for group in tiles:
            text = tile_text(group)
            if not text:
                continue
            index += 1
            blocks.append(
                make_content_block(
                    seq_id=f"pdf-{index:04d}",
                    block_type=BlockType.TEXT,
                    text=text,
                    location=SourceLocation(
                        page=ctx.page_no,
                        bbox=round_bbox(union_bbox([item.bbox for item in group])),
                        page_width=ctx.width,
                        page_height=ctx.height,
                    ),
                    extra={
                        "engine": "pymupdf",
                        "page_kind": ctx.kind,
                        "reconstructor": self.name,
                        "role": "kpi",
                    },
                )
            )
        stamp_blocks(blocks, reconstructor=self.name, page_kind=ctx.kind)
        return index, blocks


def _tile_origin(group: list[LayoutLine]) -> tuple[float, float]:
    box = union_bbox([item.bbox for item in group])
    return (box[1], box[0])


def _extract_kpi_pairs(lines: list[LayoutLine]) -> list[list[LayoutLine]]:
    if not lines:
        return []
    used: set[int] = set()
    tiles: list[list[LayoutLine]] = []
    for line in lines:
        if id(line) in used or not _is_label(line.text):
            continue
        partner = _nearest_kpi_value(line, lines, used)
        if partner is None:
            continue
        tiles.append([line, partner])
        used.add(id(line))
        used.add(id(partner))
    rest = [line for line in lines if id(line) not in used]
    tiles.extend(_proximity_clusters(rest))
    return tiles


def _nearest_value(
    label: LayoutLine, lines: list[LayoutLine], used: set[int]
) -> LayoutLine | None:
    return _nearest_matching_value(label, lines, used, _is_value)


def _nearest_kpi_value(
    label: LayoutLine, lines: list[LayoutLine], used: set[int]
) -> LayoutLine | None:
    return _nearest_matching_value(label, lines, used, _is_kpi_value)


def _nearest_matching_value(
    label: LayoutLine,
    lines: list[LayoutLine],
    used: set[int],
    predicate: Callable[[str], bool],
) -> LayoutLine | None:
    best: LayoutLine | None = None
    best_gap = 1e9
    for line in lines:
        if line is label or id(line) in used or not predicate(line.text):
            continue
        if not _label_value_aligned(label, line):
            continue
        gap = abs(line.bbox[1] - label.bbox[3])
        if gap < best_gap:
            best = line
            best_gap = gap
    return best


def _is_kpi_value(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if any(ch in stripped for ch in "€$£%"):
        return True
    if _SCORE_LETTER.fullmatch(stripped):
        return True
    if _TRAILING_DASH.fullmatch(stripped):
        return True
    return bool(_DECIMAL_VALUE.fullmatch(stripped) and len(stripped) <= 6)


def _label_value_aligned(label: LayoutLine, value: LayoutLine) -> bool:
    line_h = max(label.font_size, value.font_size, 10.0)
    gap = value.bbox[1] - label.bbox[3]
    h_overlap = min(label.bbox[2], value.bbox[2]) - max(label.bbox[0], value.bbox[0])
    if 0 <= gap <= 1.2 * line_h and h_overlap > -8:
        return True
    return _same_row(label, value) and value.bbox[0] >= label.bbox[0] - 4


def _is_label(text: str) -> bool:
    stripped = text.strip()
    if not stripped or _is_value(stripped):
        return False
    return len(stripped) <= 48 and not stripped.endswith((".", ",", ";"))


def _is_value(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if any(ch in stripped for ch in "€$£%"):
        return True
    if _SCORE_LETTER.fullmatch(stripped):
        return True
    if _TRAILING_DASH.fullmatch(stripped):
        return True
    if _DECIMAL_VALUE.fullmatch(stripped):
        return True
    digits = sum(ch.isdigit() for ch in stripped)
    return digits >= 1 and digits >= max(1, len(stripped) // 3)


def _same_row(a: LayoutLine, b: LayoutLine) -> bool:
    ay = (a.bbox[1] + a.bbox[3]) / 2
    by = (b.bbox[1] + b.bbox[3]) / 2
    return abs(ay - by) < max(a.font_size, b.font_size, 10.0) * 1.2


def _tile_boxes_from_drawings(
    page: object, page_width: float, page_height: float
) -> list[tuple[float, float, float, float]]:
    boxes: list[tuple[float, float, float, float]] = []
    try:
        drawings = page.get_drawings()  # type: ignore[attr-defined]
    except Exception:
        return boxes
    for drawing in drawings:
        rect = drawing.get("rect")
        if rect is None:
            continue
        box = round_bbox((float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1)))
        width = box[2] - box[0]
        height = box[3] - box[1]
        if width < 50 or height < 28:
            continue
        if page_width and width > page_width * 0.7:
            continue
        if page_height and height > page_height * 0.45:
            continue
        boxes.append(box)
    return _merge_similar_boxes(boxes)


def _merge_similar_boxes(
    boxes: list[tuple[float, float, float, float]],
) -> list[tuple[float, float, float, float]]:
    merged: list[tuple[float, float, float, float]] = []
    for box in boxes:
        placed = False
        for index, existing in enumerate(merged):
            if overlap_ratio(box, existing) >= 0.7:
                merged[index] = round_bbox(union_bbox([box, existing]))
                placed = True
                break
        if not placed:
            merged.append(box)
    return merged


def _containing_tile(
    line: LayoutLine, boxes: list[tuple[float, float, float, float]]
) -> int | None:
    for index, box in enumerate(boxes):
        if contained_in(line.bbox, box, padding=6.0):
            return index
    return None


def _proximity_clusters(lines: list[LayoutLine]) -> list[list[LayoutLine]]:
    remaining = list(lines)
    clusters: list[list[LayoutLine]] = []
    while remaining:
        seed = remaining.pop(0)
        cluster = [seed]
        changed = True
        while changed:
            changed = False
            keep: list[LayoutLine] = []
            for line in remaining:
                if _near_cluster(line, cluster):
                    cluster.append(line)
                    changed = True
                else:
                    keep.append(line)
            remaining = keep
        clusters.append(cluster)
    return clusters


def _near_cluster(line: LayoutLine, cluster: list[LayoutLine]) -> bool:
    for member in cluster:
        v_gap = max(0.0, line.bbox[1] - member.bbox[3], member.bbox[1] - line.bbox[3])
        h_gap = max(0.0, line.bbox[0] - member.bbox[2], member.bbox[0] - line.bbox[2])
        v_overlap = min(line.bbox[3], member.bbox[3]) - max(line.bbox[1], member.bbox[1])
        h_overlap = min(line.bbox[2], member.bbox[2]) - max(line.bbox[0], member.bbox[0])
        if v_gap < 16 and h_overlap > 0:
            return True
        if h_gap < 24 and v_overlap > 0:
            return True
    return False
