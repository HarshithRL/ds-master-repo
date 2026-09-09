from __future__ import annotations


def round_bbox(bbox: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    return (
        round(float(bbox[0]), 1),
        round(float(bbox[1]), 1),
        round(float(bbox[2]), 1),
        round(float(bbox[3]), 1),
    )


def union_bbox(boxes: list[tuple[float, float, float, float]]) -> tuple[float, float, float, float]:
    return (
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    )


def overlap_ratio(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    inter = iw * ih
    area = max(1.0, (ax1 - ax0) * (ay1 - ay0))
    return inter / area


def overlaps_any(
    bbox: tuple[float, float, float, float],
    others: list[tuple[float, float, float, float]],
    threshold: float = 0.45,
) -> bool:
    return any(overlap_ratio(bbox, other) >= threshold for other in others)


def contained_in(
    inner: tuple[float, float, float, float],
    outer: tuple[float, float, float, float],
    padding: float = 4.0,
) -> bool:
    return (
        inner[0] >= outer[0] - padding
        and inner[1] >= outer[1] - padding
        and inner[2] <= outer[2] + padding
        and inner[3] <= outer[3] + padding
    )


def covered_by_any(
    bbox: tuple[float, float, float, float],
    others: list[tuple[float, float, float, float]],
    *,
    padding: float = 4.0,
    overlap: float = 0.3,
) -> bool:
    return any(
        contained_in(bbox, other, padding) or overlap_ratio(bbox, other) >= overlap
        for other in others
    )


def vector_item_count(page) -> int:
    count = 0
    try:
        drawings = page.get_drawings()
    except Exception:
        return 0
    for drawing in drawings:
        for item in drawing.get("items") or []:
            kind = item[0] if item else ""
            if kind in {"l", "re", "qu", "c"}:
                count += 1
    return count
