from __future__ import annotations

import re
import statistics

from ..blocks import make_content_block
from ..heading_stack import HeadingStack
from ..models import BlockType, ContentBlock, SourceLocation
from .pdf_geometry import round_bbox, union_bbox
from .pdf_layout import LayoutLine

_LIST_RE = re.compile(r"^\s*([•●○▪►▪]|[-*+]|\d+[.)]|[A-Za-z][.)])\s+\S")
_NUMBERED_TITLE = re.compile(r"^(\d+(?:\.\d+){0,3})\.?\s+(\S.*)$")
_ALSO_SEE = re.compile(r"(?i)^also\s+see\b")
_MONTH = (
    r"(?:january|february|march|april|may|june|july|august|september|october|"
    r"november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)"
)
_DATE = re.compile(
    rf"(?i)^(?:\d{{1,2}}\s+{_MONTH}\s+\d{{2,4}}|{_MONTH}\s+\d{{1,2}},?\s+\d{{2,4}})$"
)
_POSTCODE = re.compile(r"^\d{1,5}\s+[A-Z]{3,}$")
_SHORT_CODE = re.compile(r"^[A-Z]{2,5}$")
_NUMERIC_RANGE = re.compile(r"^\d[\d\s]*\s*[–-]\s*\d[\d\s]*$")
_CURRENCY_OR_KPI = re.compile(r"[€$£]\s*[\d.,]+")
_MOSTLY_NUMERIC = re.compile(r"^[\d.,\s%/+-]+$")


def heading_level(text: str, font_size: float = 0.0, bold: bool = False, cut: float = 11.0) -> int | None:
    stripped = text.strip()
    if not stripped or len(stripped) > 80:
        return None
    if re.fullmatch(r"N\.?B\.?", stripped, re.I):
        return None
    if _looks_like_non_heading(stripped):
        return None
    numbered = _NUMBERED_TITLE.match(stripped)
    if numbered:
        rest = numbered.group(2).strip()
        if not _is_numbered_title(rest):
            return None
        return min(numbered.group(1).count(".") + 1, 6)
    if font_size < cut:
        return None
    if stripped.endswith((".", ",", ";", ":")):
        return None
    if looks_like_sentence(stripped):
        return None
    if font_size >= cut * 1.15:
        return 1
    return 2


def _is_numbered_title(rest: str) -> bool:
    if not rest or _ALSO_SEE.match(rest):
        return False
    if len(rest) > 70:
        return False
    if looks_like_sentence(rest):
        return False
    words = [word for word in rest.split() if word]
    if not words or len(words) > 12:
        return False
    if rest[:1].islower():
        return False
    titleish = sum(1 for word in words if word[:1].isupper() or not word[:1].isalpha())
    return titleish >= max(1, len(words) - 1)


def _looks_like_non_heading(text: str) -> bool:
    if _DATE.match(text):
        return True
    if _POSTCODE.match(text):
        return True
    if _SHORT_CODE.match(text):
        return True
    if _NUMERIC_RANGE.match(text):
        return True
    if _CURRENCY_OR_KPI.search(text) and len(text.split()) <= 4:
        return True
    if _MOSTLY_NUMERIC.match(text) and any(ch.isdigit() for ch in text):
        return True
    return False


def looks_like_sentence(text: str) -> bool:
    if len(text) > 80:
        return True
    mid = text[1:-1] if len(text) > 2 else text
    if "." in mid or "," in mid:
        words = text.split()
        title_case = sum(1 for word in words if word[:1].isupper()) >= max(1, len(words) - 1)
        return not (title_case and len(words) <= 8)
    return False


def merge_cover_titles(lines: list[LayoutLine], page_kind: str) -> list[LayoutLine]:
    if page_kind != "design" or len(lines) < 2:
        return lines
    sizes = [line.font_size for line in lines if line.font_size > 0]
    if not sizes:
        return lines
    cut = max(sizes) * 0.85
    merged: list[LayoutLine] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if _cover_title_line(line, cut):
            group = [line]
            cursor = index + 1
            while cursor < len(lines) and _cover_title_line(lines[cursor], cut):
                nxt = lines[cursor]
                gap = nxt.bbox[1] - group[-1].bbox[3]
                if gap < 0 or gap > 48:
                    break
                group.append(nxt)
                cursor += 1
            if len(group) >= 2:
                merged.append(
                    LayoutLine(
                        text=" ".join(item.text for item in group),
                        bbox=union_bbox([item.bbox for item in group]),
                        font_size=max(item.font_size for item in group),
                        bold=any(item.bold for item in group),
                        page=line.page,
                    )
                )
                index = cursor
                continue
        merged.append(line)
        index += 1
    return merged


def _cover_title_line(line: LayoutLine, cut: float) -> bool:
    text = line.text.strip()
    if not text or len(text) > 80 or line.font_size < cut:
        return False
    return not looks_like_sentence(text)


def lines_to_blocks(
    lines: list[LayoutLine],
    page_kind: str,
    page_no: int,
    index: int,
    page_width: float,
    page_height: float,
    reconstructor: str | None = None,
) -> tuple[int, list[ContentBlock]]:
    if not lines:
        return index, []
    sizes = [line.font_size for line in lines if line.font_size > 0]
    median_body = statistics.median(sizes) if sizes else 11.0
    cut = max(11.0, float(median_body) * 1.28)
    heading_flags = [heading_level(line.text, line.font_size, line.bold, cut) is not None for line in lines]
    groups = _merge_line_groups(lines, heading_flags)
    blocks: list[ContentBlock] = []
    for group in groups:
        first = group[0]
        text = "\n".join(item.text for item in group).strip()
        if not text:
            continue
        level = heading_level(first.text, first.font_size, first.bold, cut) if len(group) == 1 else None
        if level is not None:
            block_type = BlockType.HEADING
        elif all(_LIST_RE.match(item.text) for item in group):
            block_type = BlockType.LIST
            level = None
        else:
            block_type = BlockType.LIST if _LIST_RE.match(text.split("\n", 1)[0]) else BlockType.TEXT
            level = None
        index += 1
        bbox = round_bbox(union_bbox([item.bbox for item in group]))
        blocks.append(
            make_content_block(
                seq_id=f"pdf-{index:04d}",
                block_type=block_type,
                text=text,
                location=SourceLocation(
                    page=page_no,
                    bbox=bbox,
                    page_width=page_width,
                    page_height=page_height,
                ),
                extra={
                    "engine": "pymupdf",
                    "page_kind": page_kind,
                    "font_size": round(first.font_size, 2),
                    **({"reconstructor": reconstructor} if reconstructor else {}),
                },
                level=level,
            )
        )
    return index, blocks


def apply_heading_paths(blocks: list[ContentBlock], stack: HeadingStack) -> None:
    for block in blocks:
        if block.type == BlockType.HEADING:
            level = block.level or 2
            block.heading_path = stack.push(level, block.text.split("\n", 1)[0].strip())
        else:
            block.heading_path = stack.path()


def _merge_line_groups(lines: list[LayoutLine], heading_flags: list[bool]) -> list[list[LayoutLine]]:
    groups: list[list[LayoutLine]] = []
    current: list[LayoutLine] = []
    for line, is_heading in zip(lines, heading_flags):
        standalone = is_heading or bool(_LIST_RE.match(line.text))
        if standalone:
            if current:
                groups.append(current)
                current = []
            groups.append([line])
            continue
        if not current:
            current = [line]
            continue
        prev = current[-1]
        gap = line.bbox[1] - prev.bbox[3]
        similar = abs(line.font_size - prev.font_size) <= max(0.8, prev.font_size * 0.1)
        if similar and 0 <= gap < 1.2 * max(prev.font_size, 1.0):
            current.append(line)
        else:
            groups.append(current)
            current = [line]
    if current:
        groups.append(current)
    return groups
