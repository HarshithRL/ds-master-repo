from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from .models import (
    ArtifactDocument,
    ArtifactType,
    BlockType,
    ContentBlock,
    SourceLocation,
)


@dataclass(frozen=True)
class MarkdownConvertOptions:
    front_matter: bool = True
    section_breaks: bool = True
    source_hints: bool = True
    guess_headings: bool = True
    collapse_blank_lines: bool = True


@dataclass
class MarkdownDocument:
    markdown: str
    section_count: int = 0
    table_count: int = 0
    warnings: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return self.markdown


class MarkdownTableBuilder:
    """Render a 2D cell matrix as a GitHub-flavored Markdown table."""

    def build(self, rows: list[list[str]] | None) -> str:
        matrix = self._normalize(rows or [])
        if not matrix:
            return ""
        header, *body = matrix
        if not body:
            body = [[""] * len(header)]
        width = len(header)
        lines = [
            self._row(header, width),
            "|" + "|".join(" --- " for _ in range(width)) + "|",
        ]
        for row in body:
            lines.append(self._row(row, width))
        return "\n".join(lines)

    @staticmethod
    def _normalize(rows: list[list[str]]) -> list[list[str]]:
        cleaned: list[list[str]] = []
        for row in rows:
            cells = [("" if cell is None else str(cell)).replace("\n", " ").strip() for cell in row]
            if any(cells):
                cleaned.append(cells)
        if not cleaned:
            return []
        width = max(len(row) for row in cleaned)
        return [row + [""] * (width - len(row)) for row in cleaned]

    @staticmethod
    def _row(cells: list[str], width: int) -> str:
        padded = cells + [""] * (width - len(cells))
        escaped = [MarkdownEscaper.cell(cell) for cell in padded]
        return "| " + " | ".join(escaped) + " |"


class MarkdownEscaper:
    _cell_pipe = re.compile(r"\|")
    _heading_prefix = re.compile(r"^#{1,6}\s+")

    @classmethod
    def cell(cls, text: str) -> str:
        return cls._cell_pipe.sub("\\|", text).strip()

    @classmethod
    def inline(cls, text: str) -> str:
        return text.replace("\r\n", "\n").strip()

    @classmethod
    def heading_text(cls, text: str) -> str:
        cleaned = cls.inline(text)
        return cls._heading_prefix.sub("", cleaned)


class LocationAnnotator:
    """Emit an HTML loc comment so viewers can open page + bbox without leaking filename into body text."""

    def comment(self, block: ContentBlock) -> str:
        location = block.location
        parts: list[str] = []
        if location.page is not None:
            parts.append(f"page={location.page}")
        elif location.slide is not None:
            parts.append(f"slide={location.slide}")
        elif location.sheet:
            parts.append(f"sheet={location.sheet}")
        if block.block_id:
            parts.append(f"block={block.block_id}")
        parts.append(f"type={block.type.value}")
        return f"<!-- loc {' '.join(parts)} -->"


class BlockMarkdownRenderer:
    def __init__(self, options: MarkdownConvertOptions) -> None:
        self.options = options
        self.tables = MarkdownTableBuilder()
        self.escape = MarkdownEscaper
        self.locations = LocationAnnotator()
        self._document: ArtifactDocument | None = None

    def bind(self, document: ArtifactDocument | None) -> None:
        self._document = document

    def render(self, block: ContentBlock) -> str:
        if block.type == BlockType.HEADING:
            return self._heading(block)
        if block.type == BlockType.TABLE:
            return self._table(block)
        if block.type == BlockType.LIST:
            return self._list(block)
        if block.type == BlockType.NOTE:
            return self._note(block)
        if block.type in {BlockType.IMAGE, BlockType.CHART}:
            return self._image(block)
        return self._text(block)

    def _heading(self, block: ContentBlock) -> str:
        level = self._heading_level(block)
        title = self.escape.heading_text(block.text.split("\n", 1)[0])
        if not title:
            return ""
        body = self._maybe_hint(f"{'#' * level} {title}", block)
        rest = block.text.split("\n", 1)[1:]
        if rest and rest[0].strip():
            return body + "\n\n" + self.escape.inline(rest[0])
        return body

    def _heading_level(self, block: ContentBlock) -> int:
        style = str(block.extra.get("style") or "")
        match = re.search(r"heading\s*(\d+)", style, flags=re.I)
        if match:
            return min(max(int(match.group(1)), 1), 6)
        if block.level:
            return min(max(int(block.level) + 2, 3), 6)
        return 3

    def _table(self, block: ContentBlock) -> str:
        table = self.tables.build(block.table)
        if not table and block.text.strip():
            guessed = [line.split(" | ") for line in block.text.splitlines() if line.strip()]
            table = self.tables.build(guessed)
        if not table:
            return ""
        title = None
        if block.location.sheet:
            title = f"### {block.location.sheet}"
            if block.location.cell_range:
                title += f" (`{block.location.cell_range}`)"
        pieces = [p for p in (title, table, self._hint_line(block)) if p]
        return "\n\n".join(pieces)

    def _list(self, block: ContentBlock) -> str:
        lines = []
        for raw in block.text.splitlines():
            item = raw.strip()
            if not item:
                continue
            item = re.sub(r"^([•●○▪►]|\d+[.)]|[-*+])\s*", "", item)
            lines.append(f"- {item}")
        body = "\n".join(lines) or f"- {self.escape.inline(block.text)}"
        hint = self._hint_line(block)
        return body if not hint else f"{body}\n{hint}"

    def _note(self, block: ContentBlock) -> str:
        quoted = "\n".join(f"> {line}" if line else ">" for line in block.text.splitlines())
        header = "> **Notes**"
        if block.location.slide is not None:
            header = f"> **Notes — slide {block.location.slide}**"
        return f"{header}\n{quoted}"

    def _image(self, block: ContentBlock) -> str:
        kind = "chart" if block.type == BlockType.CHART else "image"
        caption = re.sub(r"\[(image|chart)\]", "", block.text, flags=re.I).strip()
        caption = self.escape.inline(caption.split("\n", 1)[0]) if caption else ""
        caption = caption.replace('"', "'")
        href = f"#{block.block_id}" if block.block_id else ""
        title = f' "{caption}"' if caption else ""
        image = f"![{kind}]({href}{title})"
        return self._maybe_hint(image, block)

    def _text(self, block: ContentBlock) -> str:
        text = block.text.strip()
        if not text:
            return ""
        if self.options.guess_headings and self._looks_like_heading(block, text):
            clone = ContentBlock(
                id=block.id,
                type=BlockType.HEADING,
                text=text.split("\n", 1)[0],
                location=block.location,
                extra=block.extra,
                block_id=block.block_id,
                level=block.level,
                heading_path=list(block.heading_path),
            )
            remainder = text.split("\n", 1)[1:]
            heading = self._heading(clone)
            if remainder and remainder[0].strip():
                return heading + "\n\n" + self._paragraphs(remainder[0])
            return heading
        body = self._paragraphs(text)
        hint = self._hint_line(block)
        return body if not hint else f"{body}\n{hint}"

    def _paragraphs(self, text: str) -> str:
        chunks: list[str] = []
        for para in re.split(r"\n\s*\n", text.strip()):
            lines = [line.rstrip() for line in para.splitlines() if line.strip()]
            if not lines:
                continue
            if all(self._looks_like_bullet(line) for line in lines):
                items = []
                for line in lines:
                    items.append("- " + re.sub(r"^([•●○▪►]|\d+[.)]|[-*+])\s*", "", line.strip()))
                chunks.append("\n".join(items))
            else:
                chunks.append(" ".join(line.strip() for line in lines))
        return "\n\n".join(chunks)

    @staticmethod
    def _looks_like_bullet(line: str) -> bool:
        return bool(re.match(r"^\s*([•●○▪►]|\d+[.)]|[-*+])\s+\S", line))

    @staticmethod
    def _looks_like_heading(block: ContentBlock, text: str) -> bool:
        first = text.split("\n", 1)[0].strip()
        if not first or len(first) > 60 or first.endswith((".", "?", "!", ",")):
            return False
        if "," in first or block.location.sheet or block.location.cell_range:
            return False
        words = first.split()
        if len(words) > 6:
            return False
        letters = re.sub(r"[^A-Za-z]", "", first)
        return bool(letters) and letters.upper() == letters and len(letters) >= 3

    def _hint_line(self, block: ContentBlock) -> str:
        if not self.options.source_hints:
            return ""
        return self.locations.comment(block)

    def _maybe_hint(self, body: str, block: ContentBlock) -> str:
        hint = self._hint_line(block)
        return body if not hint else f"{body}\n{hint}"


class MarkdownSectionPlanner:
    """Insert page / slide / sheet section headings when the source changes."""

    def __init__(self, artifact_type: ArtifactType, enabled: bool) -> None:
        self.artifact_type = artifact_type
        self.enabled = enabled
        self._last_key: tuple | None = None
        self.section_count = 0

    def heading_for(self, block: ContentBlock) -> str | None:
        if not self.enabled:
            return None
        key = self._key(block.location)
        if key is None or key == self._last_key:
            return None
        self._last_key = key
        self.section_count += 1
        loc = block.location
        if loc.page is not None:
            return f"## Page {loc.page}"
        if loc.slide is not None:
            return f"## Slide {loc.slide}"
        if loc.sheet and block.type != BlockType.TABLE:
            return f"## Sheet: {loc.sheet}"
        return None

    @staticmethod
    def _key(location: SourceLocation) -> tuple | None:
        if location.page is not None:
            return ("page", location.page)
        if location.slide is not None:
            return ("slide", location.slide)
        if location.sheet:
            return ("sheet", location.sheet)
        return None


class MarkdownFrontMatter:
    def render(self, document: ArtifactDocument) -> str:
        meta = document.metadata
        page_count = meta.page_count or len(document.pages) or meta.slide_count or meta.sheet_count
        rows = [
            ("artifact_id", document.artifact_id),
            ("filename", meta.filename),
            ("coord_system", document.coord_system),
            ("pages", page_count),
        ]
        lines = ["---"]
        for key, value in rows:
            if value is None or value == "":
                continue
            lines.append(f"{key}: {self._yaml_value(value)}")
        lines.append("---")
        return "\n".join(lines)

    @staticmethod
    def _yaml_value(value: object) -> str:
        text = str(value)
        if re.search(r'[:#{}[\],&*?]|^\s|[\n"]', text):
            return '"' + text.replace('"', '\\"') + '"'
        return text


class MarkdownConvertor:
    """Convert parsed ArtifactDocument blocks into structured Markdown."""

    def __init__(self, options: MarkdownConvertOptions | None = None) -> None:
        self.options = options or MarkdownConvertOptions()
        self._front_matter = MarkdownFrontMatter()
        self._renderer = BlockMarkdownRenderer(self.options)

    def convert(self, document: ArtifactDocument) -> str:
        return self.convert_document(document).markdown

    def convert_document(self, document: ArtifactDocument) -> MarkdownDocument:
        parts: list[str] = []
        warnings: list[str] = []
        table_count = 0
        planner = MarkdownSectionPlanner(document.artifact_type, self.options.section_breaks)
        self._renderer.bind(document)

        if self.options.front_matter:
            parts.append(self._front_matter.render(document))

        if not document.blocks:
            warnings.append("No content blocks to convert.")
            body = "\n\n".join(parts)
            return MarkdownDocument(markdown=body.strip() + "\n", warnings=warnings)

        for block in document.blocks:
            if block.type == BlockType.TABLE:
                table_count += 1
            section = planner.heading_for(block)
            if section:
                parts.append(section)
            rendered = self._renderer.render(block)
            if rendered:
                parts.append(rendered)

        markdown = "\n\n".join(part for part in parts if part and part.strip())
        if self.options.collapse_blank_lines:
            markdown = re.sub(r"\n{3,}", "\n\n", markdown).strip()
        if document.warnings:
            warnings.extend(document.warnings)
        return MarkdownDocument(
            markdown=markdown + "\n",
            section_count=planner.section_count,
            table_count=table_count,
            warnings=warnings,
        )

    def convert_blocks(self, blocks: Iterable[ContentBlock]) -> str:
        self._renderer.bind(None)
        parts = [self._renderer.render(block) for block in blocks]
        text = "\n\n".join(part for part in parts if part)
        return re.sub(r"\n{3,}", "\n\n", text).strip() + ("\n" if text else "")
