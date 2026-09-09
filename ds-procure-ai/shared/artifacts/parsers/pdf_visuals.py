from __future__ import annotations

from ..blocks import make_content_block
from ..models import BlockType, ContentBlock, SourceLocation
from .pdf_geometry import overlap_ratio, round_bbox, union_bbox, vector_item_count
from .pdf_layout import LayoutLine

_MIN_IMAGE_EDGE = 24.0
_HEADER_BAND = 0.12
_FOOTER_BAND = 0.90
_CHART_CURVES = 50
_SKIP_DRAWING_CHARTS = {"design", "dashboard", "table"}


def extract_visuals(
    page,
    lines: list[LayoutLine],
    page_kind: str,
    page_no: int,
    table_boxes: list[tuple[float, float, float, float]],
    start_index: int,
) -> tuple[int, list[ContentBlock]]:
    width = float(page.rect.width or 0)
    height = float(page.rect.height or 1)
    blocks: list[ContentBlock] = []
    index = start_index
    image_boxes: list[tuple[float, float, float, float]] = []

    for item in _image_infos(page):
        bbox = item.get("bbox")
        if not bbox or len(bbox) < 4:
            continue
        box = round_bbox((float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])))
        if _skip_logo(box, width, height):
            continue
        if any(overlap_ratio(box, table) >= 0.5 for table in table_boxes):
            continue
        image_boxes.append(box)
        caption = nearest_caption(lines, box)
        placeholder = "[chart]" if _looks_like_chart(page, box, page_kind) else "[image]"
        text = f"{caption}\n{placeholder}".strip() if caption else placeholder
        block_type = BlockType.CHART if placeholder == "[chart]" else BlockType.IMAGE
        index += 1
        blocks.append(
            make_content_block(
                seq_id=f"pdf-{index:04d}",
                block_type=block_type,
                text=text,
                location=SourceLocation(
                    page=page_no,
                    bbox=box,
                    page_width=width,
                    page_height=height,
                ),
                extra={"engine": "pymupdf", "page_kind": page_kind},
            )
        )

    chart_box = _drawing_chart_bbox(page, table_boxes, image_boxes, page_kind)
    if chart_box is not None:
        caption = nearest_caption(lines, chart_box)
        text = f"{caption}\n[chart]".strip() if caption else "[chart]"
        index += 1
        blocks.append(
            make_content_block(
                seq_id=f"pdf-{index:04d}",
                block_type=BlockType.CHART,
                text=text,
                location=SourceLocation(
                    page=page_no,
                    bbox=chart_box,
                    page_width=width,
                    page_height=height,
                ),
                extra={"engine": "pymupdf.drawings", "page_kind": page_kind},
            )
        )
    return index, blocks


def _image_infos(page) -> list[dict]:
    try:
        infos = page.get_image_info(xrefs=True)
        if infos:
            return list(infos)
    except Exception:
        pass
    try:
        data = page.get_text("dict")
    except Exception:
        return []
    found: list[dict] = []
    for block in data.get("blocks") or []:
        if block.get("type") == 1 and block.get("bbox"):
            found.append({"bbox": block.get("bbox")})
    return found


def _skip_logo(
    bbox: tuple[float, float, float, float],
    page_width: float,
    page_height: float,
) -> bool:
    x0, y0, x1, y1 = bbox
    width = x1 - x0
    height = y1 - y0
    if width < _MIN_IMAGE_EDGE or height < _MIN_IMAGE_EDGE:
        return True
    if y1 <= page_height * _HEADER_BAND and width < page_width * 0.55:
        return True
    if y0 >= page_height * _FOOTER_BAND:
        return True
    return False


def _looks_like_chart(page, bbox: tuple[float, float, float, float], page_kind: str) -> bool:
    if page_kind in _SKIP_DRAWING_CHARTS:
        return False
    curves = 0
    try:
        drawings = page.get_drawings()
    except Exception:
        return False
    for drawing in drawings:
        rect = drawing.get("rect")
        if rect is None:
            continue
        draw_box = (float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1))
        if overlap_ratio(draw_box, bbox) < 0.2:
            continue
        for item in drawing.get("items") or []:
            if item and item[0] in {"c", "qu", "l"}:
                curves += 1
    return curves >= _CHART_CURVES


def _drawing_chart_bbox(
    page,
    table_boxes: list[tuple[float, float, float, float]],
    image_boxes: list[tuple[float, float, float, float]],
    page_kind: str,
) -> tuple[float, float, float, float] | None:
    if page_kind in _SKIP_DRAWING_CHARTS:
        return None
    if vector_item_count(page) < _CHART_CURVES:
        return None
    boxes: list[tuple[float, float, float, float]] = []
    try:
        drawings = page.get_drawings()
    except Exception:
        return None
    for drawing in drawings:
        rect = drawing.get("rect")
        if rect is None:
            continue
        box = round_bbox((float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1)))
        width = box[2] - box[0]
        height = box[3] - box[1]
        if width < 40 or height < 40:
            continue
        if any(overlap_ratio(box, table) >= 0.4 for table in table_boxes):
            continue
        if any(overlap_ratio(box, image) >= 0.5 for image in image_boxes):
            continue
        boxes.append(box)
    if len(boxes) < 3:
        return None
    merged = round_bbox(union_bbox(boxes))
    area = (merged[2] - merged[0]) * (merged[3] - merged[1])
    page_area = float(page.rect.width or 1) * float(page.rect.height or 1)
    if area / page_area > 0.85:
        return None
    return merged


def nearest_caption(lines: list[LayoutLine], bbox: tuple[float, float, float, float]) -> str:
    best = ""
    best_gap = 48.0
    for line in lines:
        text = line.text.strip()
        if not text or len(text) > 80:
            continue
        if any(ch.isdigit() for ch in text) and sum(ch.isdigit() for ch in text) > 4:
            continue
        cy = (line.bbox[1] + line.bbox[3]) / 2
        above = bbox[1] - cy
        below = cy - bbox[3]
        gap = above if 0 <= above < best_gap else below if 0 <= below < best_gap else None
        if gap is None:
            continue
        best_gap = gap
        best = text
    return best
