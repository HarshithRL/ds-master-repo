from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import ArtifactDocument, BlockType, ContentBlock, SourceLocation

IMAGE_PLACEHOLDER = re.compile(r"^\[(image|chart)\b", re.IGNORECASE)
PROSE_TYPES = frozenset(
    {
        BlockType.HEADING,
        BlockType.TEXT,
        BlockType.LIST,
        BlockType.OCR,
        BlockType.NOTE,
    }
)
TABLE_TYPES = frozenset({BlockType.TABLE})
SOLO_TYPES = frozenset({BlockType.CHART})

_ENCODING = None


@dataclass(frozen=True)
class ChunkOptions:
    target_tokens: int = 800
    max_tokens: int = 1200
    min_tokens: int = 250


@dataclass
class DocumentChunk:
    ordinal: int
    chunk_type: str
    text: str
    token_count: int
    heading_path: list[str] = field(default_factory=list)
    block_ids: list[str] = field(default_factory=list)
    location: dict[str, Any] = field(default_factory=dict)
    table_json: str | None = None
    page_kind: str | None = None
    reconstructor: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ordinal": self.ordinal,
            "chunk_type": self.chunk_type,
            "text": self.text,
            "token_count": self.token_count,
            "heading_path": list(self.heading_path),
            "block_ids": list(self.block_ids),
            "location": dict(self.location),
        }
        if self.table_json is not None:
            payload["table_json"] = self.table_json
        if self.page_kind is not None:
            payload["page_kind"] = self.page_kind
        if self.reconstructor is not None:
            payload["reconstructor"] = self.reconstructor
        return payload


def _tiktoken_encoding():
    global _ENCODING
    if _ENCODING is None:
        import tiktoken

        _ENCODING = tiktoken.get_encoding("cl100k_base")
    return _ENCODING


def estimate_tokens(text: str) -> int:
    stripped = text.strip()
    if not stripped:
        return 0
    return max(1, len(_tiktoken_encoding().encode(stripped)))


def render_table_markdown(cells: list[list[str]]) -> str:
    """2D cell matrix -> GitHub-flavored table. Header repeated by caller on row-splits."""
    if not cells:
        return ""
    from ._markdown_convertor import MarkdownEscaper

    norm = [
        [MarkdownEscaper.cell((c or "").replace("\n", " ")) for c in row] for row in cells
    ]
    width = max(len(r) for r in norm)
    norm = [r + [""] * (width - len(r)) for r in norm]
    head, *body = norm
    lines = ["| " + " | ".join(head) + " |", "|" + " --- |" * width]
    lines += ["| " + " | ".join(r) + " |" for r in body]
    return "\n".join(lines)


def chunk_document(
    document: ArtifactDocument,
    options: ChunkOptions | None = None,
) -> list[DocumentChunk]:
    options = options or ChunkOptions()
    filename = _filename(document)
    emitted: list[DocumentChunk] = []
    prose_group: list[ContentBlock] = []

    def flush_prose() -> None:
        if not prose_group:
            return
        emitted.append(_make_prose_chunk(prose_group, filename, len(emitted)))
        prose_group.clear()

    for block in document.blocks:
        if _is_skippable(block):
            continue
        if block.type in TABLE_TYPES:
            flush_prose()
            emitted.extend(
                _split_table_chunks(block, filename, options, start_ordinal=len(emitted))
            )
            continue
        if block.type in SOLO_TYPES:
            flush_prose()
            emitted.append(_make_solo_chunk(block, filename, len(emitted)))
            continue
        if block.type not in PROSE_TYPES:
            continue
        if prose_group and (
            _boundary_key(block) != _boundary_key(prose_group[0])
            or _prose_tokens(prose_group + [block], filename) > options.max_tokens
        ):
            flush_prose()
        prose_group.append(block)
        if _prose_tokens(prose_group, filename) >= options.target_tokens:
            flush_prose()

    flush_prose()
    return _merge_small_prose(emitted, options)


def _filename(document: ArtifactDocument) -> str:
    name = (document.metadata.filename or "").strip()
    if name:
        return Path(name).name
    if document.source:
        return Path(document.source).name
    return "document"


def _is_skippable(block: ContentBlock) -> bool:
    if block.type == BlockType.IMAGE:
        return True
    text = (block.text or "").strip()
    if IMAGE_PLACEHOLDER.match(text):
        return True
    if block.type == BlockType.TABLE:
        return not (block.table or text)
    return not text


def _boundary_key(block: ContentBlock) -> tuple[int | None, str | None, tuple[str, ...]]:
    return (
        block.location.slide,
        block.location.sheet,
        tuple(block.heading_path),
    )


def _breadcrumb(
    filename: str,
    heading_path: list[str],
    location: SourceLocation | None = None,
) -> str:
    label = f"[{filename}]"
    if heading_path:
        return f"{label} {' > '.join(heading_path)}"
    if location is not None and location.sheet:
        return f"{label} {location.sheet}"
    if location is not None and location.slide is not None:
        return f"{label} Slide {location.slide}"
    return label


def _retrieval_text(prefix: str, body: str) -> str:
    body = body.strip()
    if not body:
        return prefix
    return f"{prefix}\n{body}"


def _prose_body(blocks: list[ContentBlock]) -> str:
    parts = [block.text.strip() for block in blocks if block.text.strip()]
    return "\n\n".join(parts)


def _prose_tokens(blocks: list[ContentBlock], filename: str) -> int:
    if not blocks:
        return 0
    prefix = _breadcrumb(filename, list(blocks[0].heading_path), blocks[0].location)
    return estimate_tokens(_retrieval_text(prefix, _prose_body(blocks)))


def _make_prose_chunk(
    blocks: list[ContentBlock],
    filename: str,
    ordinal: int,
) -> DocumentChunk:
    heading_path = list(blocks[0].heading_path)
    text = _retrieval_text(
        _breadcrumb(filename, heading_path, blocks[0].location),
        _prose_body(blocks),
    )
    extra = blocks[0].extra or {}
    return DocumentChunk(
        ordinal=ordinal,
        chunk_type="text",
        text=text,
        token_count=estimate_tokens(text),
        heading_path=heading_path,
        block_ids=_block_ids(blocks),
        location=_span_location(blocks),
        page_kind=extra.get("page_kind"),
        reconstructor=extra.get("reconstructor"),
    )


def _make_solo_chunk(block: ContentBlock, filename: str, ordinal: int) -> DocumentChunk:
    heading_path = list(block.heading_path)
    extra = block.extra or {}
    text = _retrieval_text(
        _breadcrumb(filename, heading_path, block.location),
        block.text.strip(),
    )
    return DocumentChunk(
        ordinal=ordinal,
        chunk_type="text",
        text=text,
        token_count=estimate_tokens(text),
        heading_path=heading_path,
        block_ids=_block_ids([block]),
        location=_span_location([block]),
        page_kind=extra.get("page_kind"),
        reconstructor=extra.get("reconstructor"),
    )


def _table_meta(block: ContentBlock) -> tuple[str | None, str | None]:
    extra = block.extra or {}
    return extra.get("page_kind"), extra.get("reconstructor")


def _table_chunk(
    *,
    ordinal: int,
    text: str,
    heading_path: list[str],
    block: ContentBlock,
    matrix: list[list[str]],
) -> DocumentChunk:
    page_kind, reconstructor = _table_meta(block)
    return DocumentChunk(
        ordinal=ordinal,
        chunk_type="table",
        text=text,
        token_count=estimate_tokens(text),
        heading_path=heading_path,
        block_ids=_block_ids([block]),
        location=_span_location([block]),
        table_json=json.dumps(matrix, ensure_ascii=False),
        page_kind=page_kind,
        reconstructor=reconstructor,
    )


def _split_table_chunks(
    block: ContentBlock,
    filename: str,
    options: ChunkOptions,
    *,
    start_ordinal: int,
) -> list[DocumentChunk]:
    rows = _table_rows(block)
    heading_path = list(block.heading_path)
    prefix = _breadcrumb(filename, heading_path, block.location)

    def render(subset: list[list[str]]) -> str:
        return _retrieval_text(prefix, render_table_markdown(subset))

    if not rows:
        text = _retrieval_text(prefix, block.text.strip())
        return [
            _table_chunk(
                ordinal=start_ordinal,
                text=text,
                heading_path=heading_path,
                block=block,
                matrix=[],
            )
        ]

    if estimate_tokens(render(rows)) <= options.max_tokens or len(rows) == 1:
        return [
            _table_chunk(
                ordinal=start_ordinal,
                text=render(rows),
                heading_path=heading_path,
                block=block,
                matrix=rows,
            )
        ]

    header, body = rows[0], rows[1:]
    groups: list[list[list[str]]] = []
    current = [header]
    for row in body:
        candidate = current + [row]
        if estimate_tokens(render(candidate)) > options.max_tokens and len(current) > 1:
            groups.append(current)
            current = [header, row]
        else:
            current = candidate
    groups.append(current)

    return [
        _table_chunk(
            ordinal=start_ordinal + offset,
            text=render(group),
            heading_path=heading_path,
            block=block,
            matrix=group,
        )
        for offset, group in enumerate(groups)
    ]


def _shares_heading_ancestor(left: list[str], right: list[str]) -> bool:
    shared = 0
    for a, b in zip(left, right):
        if a != b:
            break
        shared += 1
    return shared >= 1


def _compatible_chunk_locations(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return left.get("slide") == right.get("slide") and left.get("sheet") == right.get("sheet")


def _join_prose_chunks(
    first: DocumentChunk, second: DocumentChunk, *, ordinal: int
) -> DocumentChunk:
    shared: list[str] = []
    for a, b in zip(first.heading_path, second.heading_path):
        if a != b:
            break
        shared.append(a)
    text = first.text.rstrip() + "\n\n" + second.text.lstrip()
    ids: list[str] = []
    seen: set[str] = set()
    for ident in list(first.block_ids) + list(second.block_ids):
        if not ident or ident in seen:
            continue
        seen.add(ident)
        ids.append(ident)
    location = dict(first.location)
    if second.location.get("page") is not None and location.get("page") is not None:
        if second.location["page"] != location["page"]:
            location["page_end"] = second.location.get("page_end", second.location["page"])
    return DocumentChunk(
        ordinal=ordinal,
        chunk_type="text",
        text=text,
        token_count=estimate_tokens(text),
        heading_path=shared or list(first.heading_path),
        block_ids=ids,
        location=location,
        page_kind=first.page_kind or second.page_kind,
        reconstructor=first.reconstructor or second.reconstructor,
    )


def _with_ordinal(chunk: DocumentChunk, ordinal: int) -> DocumentChunk:
    if chunk.ordinal == ordinal:
        return chunk
    chunk.ordinal = ordinal
    return chunk


def _merge_small_prose(
    chunks: list[DocumentChunk], options: ChunkOptions
) -> list[DocumentChunk]:
    if options.min_tokens <= 0 or len(chunks) < 2:
        return [_with_ordinal(chunk, i) for i, chunk in enumerate(chunks)]
    current = list(chunks)
    changed = True
    while changed:
        changed = False
        nxt: list[DocumentChunk] = []
        i = 0
        while i < len(current):
            this = current[i]
            nxt_chunk = current[i + 1] if i + 1 < len(current) else None
            if (
                nxt_chunk is not None
                and this.chunk_type == "text"
                and nxt_chunk.chunk_type == "text"
                and this.token_count < options.min_tokens
                and _shares_heading_ancestor(this.heading_path, nxt_chunk.heading_path)
                and _compatible_chunk_locations(this.location, nxt_chunk.location)
                and estimate_tokens(this.text + "\n\n" + nxt_chunk.text) <= options.max_tokens
            ):
                nxt.append(_join_prose_chunks(this, nxt_chunk, ordinal=len(nxt)))
                i += 2
                changed = True
                continue
            nxt.append(this)
            i += 1
        current = nxt
    return [_with_ordinal(chunk, i) for i, chunk in enumerate(current)]


def _table_rows(block: ContentBlock) -> list[list[str]]:
    if block.table:
        return [[("" if cell is None else str(cell)) for cell in row] for row in block.table]
    if not block.text.strip():
        return []
    return [line.split(" | ") for line in block.text.splitlines() if line.strip()]


def _block_ids(blocks: list[ContentBlock]) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for block in blocks:
        ident = block.block_id or block.id
        if not ident or ident in seen:
            continue
        seen.add(ident)
        ids.append(ident)
    return ids


def _span_location(blocks: list[ContentBlock]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    pages = [block.location.page for block in blocks if block.location.page is not None]
    if pages:
        payload["page"] = pages[0]
        if pages[-1] != pages[0]:
            payload["page_end"] = pages[-1]
    slides = [block.location.slide for block in blocks if block.location.slide is not None]
    if slides:
        payload["slide"] = slides[0]
    sheets = [block.location.sheet for block in blocks if block.location.sheet]
    if sheets:
        payload["sheet"] = sheets[0]
    ranges = [block.location.cell_range for block in blocks if block.location.cell_range]
    if ranges:
        payload["cell_range"] = ranges[0]
    same_page = bool(pages) and len(set(pages)) == 1
    boxes = [block.location.bbox for block in blocks if block.location.bbox]
    if len(boxes) == 1:
        payload["bbox"] = [round(float(item), 1) for item in boxes[0]]
    elif boxes and same_page:
        payload["bbox"] = [
            round(float(min(box[0] for box in boxes)), 1),
            round(float(min(box[1] for box in boxes)), 1),
            round(float(max(box[2] for box in boxes)), 1),
            round(float(max(box[3] for box in boxes)), 1),
        ]
    return payload
