from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .chunking import DocumentChunk

COORD_PDF_POINTS = "pdf_points_top_left"


class ArtifactType(str, Enum):
    PDF = "pdf"
    PPT = "ppt"
    EXCEL = "excel"
    WORD = "word"


class BlockType(str, Enum):
    HEADING = "heading"
    TEXT = "text"
    LIST = "list"
    TABLE = "table"
    IMAGE = "image"
    CHART = "chart"
    OCR = "ocr"
    NOTE = "note"


@dataclass(frozen=True)
class ParseOptions:
    password: str | None = None
    include_tables: bool = True
    include_images: bool = False
    include_hidden_sheets: bool = False
    max_pages: int | None = None
    use_ocr: bool = False


@dataclass
class SourceLocation:
    page: int | None = None
    slide: int | None = None
    sheet: str | None = None
    bbox: tuple[float, float, float, float] | None = None
    page_width: float | None = None
    page_height: float | None = None
    paragraph_index: int | None = None
    table_index: int | None = None
    row: int | None = None
    col: int | None = None
    cell_range: str | None = None
    shape_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for key, value in self.__dict__.items():
            if value is None:
                continue
            if key == "bbox":
                payload[key] = [round(float(item), 1) for item in value]
            elif key in {"page_width", "page_height"}:
                payload[key] = round(float(value), 1)
            else:
                payload[key] = value
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> SourceLocation:
        if not data:
            return cls()
        bbox = data.get("bbox")
        bbox_t: tuple[float, float, float, float] | None = None
        if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
            bbox_t = (
                float(bbox[0]),
                float(bbox[1]),
                float(bbox[2]),
                float(bbox[3]),
            )
        return cls(
            page=_opt_int(data.get("page")),
            slide=_opt_int(data.get("slide")),
            sheet=_opt_str(data.get("sheet")),
            bbox=bbox_t,
            page_width=_opt_float(data.get("page_width")),
            page_height=_opt_float(data.get("page_height")),
            paragraph_index=_opt_int(data.get("paragraph_index")),
            table_index=_opt_int(data.get("table_index")),
            row=_opt_int(data.get("row")),
            col=_opt_int(data.get("col")),
            cell_range=_opt_str(data.get("cell_range")),
            shape_id=_opt_str(data.get("shape_id")),
        )


@dataclass
class PageInfo:
    page: int
    width: float
    height: float
    rotation: int = 0
    kind: str = "digital"
    mediabox: tuple[float, float, float, float] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "page": self.page,
            "width": round(float(self.width), 1),
            "height": round(float(self.height), 1),
            "rotation": int(self.rotation),
            "kind": self.kind,
        }
        if self.mediabox is not None:
            payload["mediabox"] = [round(float(item), 1) for item in self.mediabox]
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PageInfo:
        mediabox = data.get("mediabox")
        mediabox_t: tuple[float, float, float, float] | None = None
        if isinstance(mediabox, (list, tuple)) and len(mediabox) == 4:
            mediabox_t = (
                float(mediabox[0]),
                float(mediabox[1]),
                float(mediabox[2]),
                float(mediabox[3]),
            )
        return cls(
            page=int(data.get("page") or 0),
            width=float(data.get("width") or 0),
            height=float(data.get("height") or 0),
            rotation=int(data.get("rotation") or 0),
            kind=str(data.get("kind") or "digital"),
            mediabox=mediabox_t,
        )


@dataclass
class OutlineItem:
    title: str
    page: int | None
    level: int
    block_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "page": self.page,
            "level": self.level,
            "block_id": self.block_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OutlineItem:
        return cls(
            title=str(data.get("title") or ""),
            page=_opt_int(data.get("page")),
            level=int(data.get("level") or 0),
            block_id=str(data.get("block_id") or ""),
        )


@dataclass
class ContentBlock:
    id: str
    type: BlockType
    text: str
    location: SourceLocation = field(default_factory=SourceLocation)
    table: list[list[str]] | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    block_id: str = ""
    level: int | None = None
    heading_path: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "block_id": self.block_id,
            "type": self.type.value,
            "level": self.level,
            "heading_path": list(self.heading_path),
            "text": self.text,
            "location": self.location.to_dict(),
        }
        if self.table is not None:
            payload["table"] = self.table
        if self.extra:
            payload["extra"] = self.extra
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContentBlock:
        block_type = _block_type(data.get("type"))
        heading_path = data.get("heading_path") or []
        extra = data.get("extra") if isinstance(data.get("extra"), dict) else {}
        table = data.get("table")
        matrix: list[list[str]] | None = None
        if isinstance(table, list):
            matrix = [[("" if cell is None else str(cell)) for cell in row] for row in table]
        ident = str(data.get("id") or data.get("block_id") or "")
        return cls(
            id=ident,
            type=block_type,
            text=str(data.get("text") or ""),
            location=SourceLocation.from_dict(
                data.get("location") if isinstance(data.get("location"), dict) else None
            ),
            table=matrix,
            extra=dict(extra),
            block_id=str(data.get("block_id") or ident),
            level=_opt_int(data.get("level")),
            heading_path=[str(item) for item in heading_path],
        )


@dataclass
class ArtifactMetadata:
    filename: str
    artifact_type: ArtifactType
    mime_type: str | None = None
    title: str | None = None
    author: str | None = None
    created: str | None = None
    modified: str | None = None
    page_count: int | None = None
    slide_count: int | None = None
    sheet_count: int | None = None
    encrypted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "artifact_type": self.artifact_type.value,
            "mime_type": self.mime_type,
            "title": self.title,
            "author": self.author,
            "created": self.created,
            "modified": self.modified,
            "page_count": self.page_count,
            "slide_count": self.slide_count,
            "sheet_count": self.sheet_count,
            "encrypted": self.encrypted,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any] | None,
        *,
        default_filename: str = "document",
        default_type: ArtifactType | None = None,
    ) -> ArtifactMetadata:
        raw = data or {}
        artifact_type = _artifact_type(
            raw.get("artifact_type"),
            fallback=default_type or ArtifactType.PDF,
        )
        return cls(
            filename=str(raw.get("filename") or default_filename),
            artifact_type=artifact_type,
            mime_type=_opt_str(raw.get("mime_type")),
            title=_opt_str(raw.get("title")),
            author=_opt_str(raw.get("author")),
            created=_opt_str(raw.get("created")),
            modified=_opt_str(raw.get("modified")),
            page_count=_opt_int(raw.get("page_count")),
            slide_count=_opt_int(raw.get("slide_count")),
            sheet_count=_opt_int(raw.get("sheet_count")),
            encrypted=bool(raw.get("encrypted", False)),
        )


@dataclass
class ArtifactDocument:
    source: str
    artifact_type: ArtifactType
    metadata: ArtifactMetadata
    blocks: list[ContentBlock] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    markdown: str = ""
    artifact_id: str = ""
    coord_system: str = ""
    pages: list[PageInfo] = field(default_factory=list)
    outline: list[OutlineItem] = field(default_factory=list)
    chunks: list[DocumentChunk] = field(default_factory=list)
    parser: str = ""

    def plain_text(self) -> str:
        return "\n\n".join(block.text for block in self.blocks if block.text.strip()).strip()

    def md_text(self) -> str:
        if self.markdown.strip():
            return self.markdown.rstrip("\n")
        from ._markdown_convertor import MarkdownConvertor

        return MarkdownConvertor().convert(self).rstrip("\n")

    def tables(self) -> list[ContentBlock]:
        return [block for block in self.blocks if block.type == BlockType.TABLE]

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "source": self.source,
            "artifact_type": self.artifact_type.value,
            "coord_system": self.coord_system,
            "metadata": self.metadata.to_dict(),
            "pages": [page.to_dict() for page in self.pages],
            "outline": [item.to_dict() for item in self.outline],
            "blocks": [block.to_dict() for block in self.blocks],
            "warnings": list(self.warnings),
            "markdown": self.md_text(),
            "parser": self.parser,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ArtifactDocument:
        """Reconstruct from artifact.parsed_json (W1 backfill; never re-parse)."""
        source = str(data.get("source") or "")
        artifact_type = _artifact_type(data.get("artifact_type"))
        meta_raw = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
        filename = Path(source).name if source else "document"
        metadata = ArtifactMetadata.from_dict(
            meta_raw,
            default_filename=str(meta_raw.get("filename") or filename),
            default_type=artifact_type,
        )
        if "artifact_type" not in (data or {}):
            artifact_type = metadata.artifact_type
        blocks_raw = data.get("blocks") or []
        pages_raw = data.get("pages") or []
        outline_raw = data.get("outline") or []
        return cls(
            source=source,
            artifact_type=artifact_type,
            metadata=metadata,
            blocks=[
                ContentBlock.from_dict(block)
                for block in blocks_raw
                if isinstance(block, dict)
            ],
            warnings=[str(item) for item in (data.get("warnings") or [])],
            markdown=str(data.get("markdown") or ""),
            artifact_id=str(data.get("artifact_id") or ""),
            coord_system=str(data.get("coord_system") or ""),
            pages=[PageInfo.from_dict(page) for page in pages_raw if isinstance(page, dict)],
            outline=[
                OutlineItem.from_dict(item) for item in outline_raw if isinstance(item, dict)
            ],
            parser=str(data.get("parser") or ""),
        )


MIME_BY_TYPE = {
    ArtifactType.PDF: "application/pdf",
    ArtifactType.PPT: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ArtifactType.EXCEL: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ArtifactType.WORD: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def source_name(source: str | Path | bytes, filename: str | None) -> str:
    if filename:
        return Path(filename).name
    if isinstance(source, (str, Path)):
        return Path(source).name
    return "memory.bin"


def _opt_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _opt_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _opt_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _artifact_type(value: Any, fallback: ArtifactType = ArtifactType.PDF) -> ArtifactType:
    if isinstance(value, ArtifactType):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return ArtifactType(value.strip().lower())
        except ValueError:
            return fallback
    return fallback


def _block_type(value: Any) -> BlockType:
    if isinstance(value, BlockType):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return BlockType(value.strip().lower())
        except ValueError:
            return BlockType.TEXT
    return BlockType.TEXT
