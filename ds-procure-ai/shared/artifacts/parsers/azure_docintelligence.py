from __future__ import annotations

import os
from pathlib import Path

from shared.logger_global import get_logger

from ..exceptions import ArtifactParseError
from ..ids import file_artifact_id, make_block_id
from ..models import (
    COORD_PDF_POINTS,
    ArtifactDocument,
    ArtifactMetadata,
    ArtifactType,
    BlockType,
    ContentBlock,
    MIME_BY_TYPE,
    OutlineItem,
    PageInfo,
    ParseOptions,
    SourceLocation,
)

MODEL_ID = "prebuilt-layout"
log = get_logger(__name__)
_INCH_TO_POINT = 72.0
_HEADING_ROLES = {"title": 1, "sectionHeading": 2}
_SKIP_ROLES = {"pageHeader", "pageFooter", "pageNumber"}


class AzureDocIntelligenceParser:
    """Layout parse via Azure Document Intelligence. Old parsers stay on disk."""

    kind: ArtifactType = ArtifactType.PDF

    def parse(self, path: Path, options: ParseOptions) -> ArtifactDocument:
        endpoint, key = _credentials()
        try:
            from azure.ai.formrecognizer import DocumentAnalysisClient
            from azure.core.credentials import AzureKeyCredential
        except ImportError as exc:
            raise ArtifactParseError(
                "azure-ai-formrecognizer is required for Document Intelligence parsing."
            ) from exc

        client = DocumentAnalysisClient(endpoint=endpoint, credential=AzureKeyCredential(key))
        pages = _pages_arg(options.max_pages)
        log.info(
            "azure document intelligence start parser={} model={} file={}",
            self.__class__.__name__,
            MODEL_ID,
            path.name,
        )
        try:
            with path.open("rb") as handle:
                poller = client.begin_analyze_document(MODEL_ID, handle, pages=pages)
                result = poller.result()
        except ArtifactParseError:
            raise
        except Exception as exc:
            log.warning(
                "azure document intelligence failed parser={} model={} file={} detail={}",
                self.__class__.__name__,
                MODEL_ID,
                path.name,
                str(exc),
            )
            raise ArtifactParseError(f"Document Intelligence failed for {path.name}: {exc}") from exc

        document = document_from_layout(path, self.kind, result, options)
        document.parser = self.__class__.__name__
        log.info(
            "azure document intelligence done parser={} model={} file={} blocks={} pages={}",
            document.parser,
            MODEL_ID,
            path.name,
            len(document.blocks),
            len(document.pages),
        )
        return document


class AzurePdfParser(AzureDocIntelligenceParser):
    kind = ArtifactType.PDF


class AzureDocxParser(AzureDocIntelligenceParser):
    kind: ArtifactType = ArtifactType.WORD

    def parse(self, path: Path, options: ParseOptions) -> ArtifactDocument:
        # Document Intelligence rejects Office uploads with InvalidContent; the
        # bundled python-docx parser still yields usable text.
        try:
            return super().parse(path, options)
        except ArtifactParseError as exc:
            from .docx_parser import DocxParser

            log.warning(
                "docx falling back to local parser file={} detail={}", path.name, exc
            )
            return DocxParser().parse(path, options)


class AzurePptxParser(AzureDocIntelligenceParser):
    kind: ArtifactType = ArtifactType.PPT

    def parse(self, path: Path, options: ParseOptions) -> ArtifactDocument:
        try:
            return super().parse(path, options)
        except ArtifactParseError as exc:
            from .pptx_parser import PptxParser

            log.warning(
                "pptx falling back to local parser file={} detail={}", path.name, exc
            )
            return PptxParser().parse(path, options)


def document_from_layout(path: Path, kind: ArtifactType, result, options: ParseOptions) -> ArtifactDocument:
    pages = _pages(result, kind)
    blocks = _blocks(result, kind, options)
    if not blocks:
        raise ArtifactParseError(f"Document Intelligence returned no content for {path.name}.")

    page_count = len(pages) or _page_count(result)
    outline = [
        OutlineItem(
            title=block.text.split("\n", 1)[0].strip(),
            page=block.location.page,
            level=block.level or 2,
            block_id=block.block_id,
        )
        for block in blocks
        if block.type == BlockType.HEADING
    ]
    return ArtifactDocument(
        source=str(path),
        artifact_type=kind,
        artifact_id=file_artifact_id(path),
        coord_system=COORD_PDF_POINTS,
        metadata=ArtifactMetadata(
            filename=path.name,
            artifact_type=kind,
            mime_type=MIME_BY_TYPE.get(kind),
            page_count=page_count,
            slide_count=page_count if kind == ArtifactType.PPT else None,
        ),
        pages=pages,
        outline=outline,
        blocks=blocks,
        warnings=[],
    )


def _credentials() -> tuple[str, str]:
    endpoint = (
        os.getenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT")
        or os.getenv("azure-di-endpoint")
        or ""
    ).strip()
    key = (
        os.getenv("AZURE_DOCUMENT_INTELLIGENCE_KEY")
        or os.getenv("azure-di-key")
        or ""
    ).strip()
    if not endpoint or not key:
        endpoint, key = _credentials_from_secret_scope()
    if not endpoint or not key:
        raise ArtifactParseError(
            "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT and AZURE_DOCUMENT_INTELLIGENCE_KEY are required."
        )
    os.environ["AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT"] = endpoint
    os.environ["AZURE_DOCUMENT_INTELLIGENCE_KEY"] = key
    return endpoint, key


def _credentials_from_secret_scope() -> tuple[str, str]:
    """Apps secret resources may inject by resource key; fall back to scope read."""
    scope = (os.getenv("MATE_DI_SECRET_SCOPE") or "procure-ai").strip()
    endpoint_key = (
        os.getenv("MATE_DI_ENDPOINT_SECRET_KEY")
        or "azure-document-intelligence-endpoint"
    ).strip()
    key_key = (
        os.getenv("MATE_DI_KEY_SECRET_KEY") or "azure-document-intelligence-key"
    ).strip()
    try:
        from shared.databricks_runtime import workspace_client

        client = workspace_client()
        endpoint = _secret_value(client.secrets.get_secret(scope, endpoint_key))
        key = _secret_value(client.secrets.get_secret(scope, key_key))
        return endpoint, key
    except Exception:
        return "", ""


def _secret_value(secret: object) -> str:
    raw = getattr(secret, "value", secret)
    if raw is None:
        return ""
    if isinstance(raw, bytes):
        import base64

        try:
            return base64.b64decode(raw).decode("utf-8").strip()
        except Exception:
            return raw.decode("utf-8", errors="ignore").strip()
    text = str(raw).strip()
    if not text:
        return ""
    # Some SDK builds still return base64 text.
    try:
        import base64

        decoded = base64.b64decode(text).decode("utf-8")
        if decoded and decoded.isprintable():
            return decoded.strip()
    except Exception:
        pass
    return text


def _pages_arg(max_pages: int | None) -> str | None:
    if not max_pages or max_pages < 1:
        return None
    return f"1-{int(max_pages)}"


def _pages(result, kind: ArtifactType) -> list[PageInfo]:
    pages: list[PageInfo] = []
    for page in getattr(result, "pages", None) or []:
        number = int(getattr(page, "page_number", 0) or 0)
        if number < 1:
            continue
        width = _points(getattr(page, "width", None))
        height = _points(getattr(page, "height", None))
        pages.append(
            PageInfo(
                page=number,
                width=width,
                height=height,
                rotation=int(getattr(page, "angle", 0) or 0),
                kind="azure-layout",
            )
        )
    return pages


def _blocks(result, kind: ArtifactType, options: ParseOptions) -> list[ContentBlock]:
    table_spans = _span_set(getattr(result, "tables", None) or []) if options.include_tables else set()
    blocks: list[ContentBlock] = []
    heading_path: list[str] = []
    paragraphs = list(getattr(result, "paragraphs", None) or [])
    if paragraphs:
        for index, paragraph in enumerate(paragraphs):
            if _covered_by_table(paragraph, table_spans):
                continue
            block = _paragraph_block(paragraph, index, kind, heading_path)
            if block is None:
                continue
            if block.type == BlockType.HEADING:
                heading_path = _push_heading(heading_path, block.level or 1, block.text)
                block.heading_path = list(heading_path)
            else:
                block.heading_path = list(heading_path)
            blocks.append(block)
    else:
        blocks.extend(_line_blocks(result, kind))

    if options.include_tables:
        for index, table in enumerate(getattr(result, "tables", None) or []):
            block = _table_block(table, index, kind, heading_path)
            if block is not None:
                blocks.append(block)

    blocks.sort(key=_block_order)
    return blocks


def _paragraph_block(paragraph, index: int, kind: ArtifactType, heading_path: list[str]) -> ContentBlock | None:
    text = str(getattr(paragraph, "content", "") or "").strip()
    if not text:
        return None
    role = str(getattr(paragraph, "role", "") or "")
    if role in _SKIP_ROLES:
        return None
    level = _HEADING_ROLES.get(role)
    block_type = BlockType.HEADING if level else BlockType.TEXT
    page, bbox, width, height = _region(paragraph)
    location = _location(kind, page, bbox, width, height, index)
    block_id = make_block_id(block_type=block_type.value, text=text, page=page, bbox=bbox, extra_key=index)
    return ContentBlock(
        id=block_id,
        block_id=block_id,
        type=block_type,
        text=text,
        level=level,
        heading_path=list(heading_path),
        location=location,
        extra={"engine": "azure-document-intelligence", "model": MODEL_ID, "role": role or None},
    )


def _table_block(table, index: int, kind: ArtifactType, heading_path: list[str]) -> ContentBlock | None:
    matrix = _table_matrix(table)
    if not matrix:
        return None
    text = "\n".join(" | ".join(cell for cell in row) for row in matrix).strip()
    if not text:
        return None
    page, bbox, width, height = _region(table)
    location = _location(kind, page, bbox, width, height, index)
    block_id = make_block_id(block_type=BlockType.TABLE.value, text=text, page=page, bbox=bbox, extra_key=index)
    return ContentBlock(
        id=block_id,
        block_id=block_id,
        type=BlockType.TABLE,
        text=text,
        table=matrix,
        heading_path=list(heading_path),
        location=location,
        extra={"engine": "azure-document-intelligence", "model": MODEL_ID},
    )


def _line_blocks(result, kind: ArtifactType) -> list[ContentBlock]:
    blocks: list[ContentBlock] = []
    for page in getattr(result, "pages", None) or []:
        number = int(getattr(page, "page_number", 0) or 0)
        width = _points(getattr(page, "width", None))
        height = _points(getattr(page, "height", None))
        lines = []
        for line in getattr(page, "lines", None) or []:
            content = str(getattr(line, "content", "") or "").strip()
            if content:
                lines.append(content)
        text = "\n".join(lines).strip()
        if not text:
            continue
        location = _location(kind, number or None, None, width, height, 0)
        block_id = make_block_id(block_type=BlockType.TEXT.value, text=text, page=number or None, extra_key=number)
        blocks.append(
            ContentBlock(
                id=block_id,
                block_id=block_id,
                type=BlockType.TEXT,
                text=text,
                location=location,
                extra={"engine": "azure-document-intelligence", "model": MODEL_ID, "fallback": "page-lines"},
            )
        )
    if blocks:
        return blocks
    content = str(getattr(result, "content", "") or "").strip()
    if not content:
        return []
    block_id = make_block_id(block_type=BlockType.TEXT.value, text=content, extra_key="content")
    return [
        ContentBlock(
            id=block_id,
            block_id=block_id,
            type=BlockType.TEXT,
            text=content,
            extra={"engine": "azure-document-intelligence", "model": MODEL_ID, "fallback": "content"},
        )
    ]


def _table_matrix(table) -> list[list[str]]:
    row_count = int(getattr(table, "row_count", 0) or 0)
    col_count = int(getattr(table, "column_count", 0) or 0)
    cells = list(getattr(table, "cells", None) or [])
    if row_count < 1 or col_count < 1:
        if not cells:
            return []
        row_count = max(int(getattr(cell, "row_index", 0) or 0) for cell in cells) + 1
        col_count = max(int(getattr(cell, "column_index", 0) or 0) for cell in cells) + 1
    matrix = [["" for _ in range(col_count)] for _ in range(row_count)]
    for cell in cells:
        row = int(getattr(cell, "row_index", 0) or 0)
        col = int(getattr(cell, "column_index", 0) or 0)
        if 0 <= row < row_count and 0 <= col < col_count:
            matrix[row][col] = str(getattr(cell, "content", "") or "").strip()
    return matrix


def _region(item) -> tuple[int | None, tuple[float, float, float, float] | None, float, float]:
    regions = getattr(item, "bounding_regions", None) or []
    if not regions:
        return None, None, 0.0, 0.0
    region = regions[0]
    page = int(getattr(region, "page_number", 0) or 0) or None
    return page, _polygon_bbox(getattr(region, "polygon", None)), 0.0, 0.0


def _location(kind, page, bbox, width, height, index) -> SourceLocation:
    slide = page if kind == ArtifactType.PPT else None
    return SourceLocation(
        page=page,
        slide=slide,
        bbox=bbox,
        page_width=width or None,
        page_height=height or None,
        paragraph_index=index,
    )


def _polygon_bbox(polygon) -> tuple[float, float, float, float] | None:
    xs: list[float] = []
    ys: list[float] = []
    if not polygon:
        return None
    first = polygon[0]
    if hasattr(first, "x"):
        for point in polygon:
            xs.append(_points(point.x))
            ys.append(_points(point.y))
    elif isinstance(first, (int, float)):
        xs = [_points(polygon[i]) for i in range(0, len(polygon), 2)]
        ys = [_points(polygon[i]) for i in range(1, len(polygon), 2)]
    elif isinstance(first, (list, tuple)) and len(first) >= 2:
        for point in polygon:
            xs.append(_points(point[0]))
            ys.append(_points(point[1]))
    if not xs or not ys:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def _points(value) -> float:
    if value is None:
        return 0.0
    return round(float(value) * _INCH_TO_POINT, 1)


def _span_set(tables) -> set[tuple[int, int]]:
    spans: set[tuple[int, int]] = set()
    for table in tables:
        for span in getattr(table, "spans", None) or []:
            offset = int(getattr(span, "offset", 0) or 0)
            length = int(getattr(span, "length", 0) or 0)
            if length > 0:
                spans.add((offset, offset + length))
    return spans


def _covered_by_table(paragraph, table_spans: set[tuple[int, int]]) -> bool:
    if not table_spans:
        return False
    for span in getattr(paragraph, "spans", None) or []:
        offset = int(getattr(span, "offset", 0) or 0)
        length = int(getattr(span, "length", 0) or 0)
        end = offset + length
        for start, stop in table_spans:
            if offset >= start and end <= stop:
                return True
    return False


def _push_heading(path: list[str], level: int, text: str) -> list[str]:
    title = text.split("\n", 1)[0].strip()
    kept = path[: max(level - 1, 0)]
    kept.append(title)
    return kept


def _page_count(result) -> int:
    pages = getattr(result, "pages", None) or []
    return len(pages)


def _block_order(block: ContentBlock) -> tuple[int, float, int]:
    page = block.location.page or 0
    top = block.location.bbox[1] if block.location.bbox else 0.0
    return (page, top, block.location.paragraph_index or 0)
