from __future__ import annotations

from pathlib import Path

import pymupdf

from ..exceptions import ArtifactParseError, CorruptArtifact, EncryptedArtifact
from ..heading_stack import HeadingStack
from ..ids import file_artifact_id
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
)
from .pdf_chrome import PdfHeaderFooterDetector
from .pdf_geometry import round_bbox
from .pdf_headings import apply_heading_paths
from .pdf_layout import PdfLayoutExtractor, PdfPageClassifier
from .pdf_reconstruct import ReconstructPage, reconstructor_for
from .pdf_reconstruct.letter import LetterReconstructor


class PdfParser:
    kind = ArtifactType.PDF

    def parse(self, path: Path, options: ParseOptions) -> ArtifactDocument:
        try:
            document = pymupdf.open(str(path))
        except Exception as exc:
            raise CorruptArtifact(f"Failed to open PDF: {path.name}") from exc

        encrypted = bool(document.is_encrypted)
        try:
            if encrypted:
                if not document.authenticate(options.password or ""):
                    raise EncryptedArtifact(
                        f"PDF is encrypted and requires a valid password: {path.name}"
                    )
            page_count = document.page_count
            selected = list(document)
            if options.max_pages is not None:
                selected = selected[: options.max_pages]
            meta = document.metadata or {}
            title = _meta_str(meta.get("title"))
            author = _meta_str(meta.get("author"))
            created = _meta_str(meta.get("creationDate"))
            modified = _meta_str(meta.get("modDate"))

            chrome = PdfHeaderFooterDetector().detect(selected)
            classifier = PdfPageClassifier()
            extractor = PdfLayoutExtractor()
            chrome_detector = PdfHeaderFooterDetector()
            letter = LetterReconstructor()
            stack = HeadingStack()

            blocks: list[ContentBlock] = []
            pages: list[PageInfo] = []
            warnings: list[str] = []
            index = 0

            for page_index, page in enumerate(selected):
                page_no = page.number + 1
                page_width = float(page.rect.width or 0)
                page_height = float(page.rect.height or 0)
                page_kind = classifier.classify(page)
                pages.append(
                    PageInfo(
                        page=page_no,
                        width=page_width,
                        height=page_height,
                        rotation=int(page.rotation or 0),
                        kind=page_kind,
                        mediabox=_page_mediabox(page),
                    )
                )

                lines = [
                    line
                    for line in extractor.lines(page, page_no)
                    if not chrome_detector.is_chrome(
                        line.text, line.bbox, page_height or 1, chrome
                    )
                ]
                ctx = ReconstructPage(
                    page=page,
                    page_no=page_no,
                    page_index=page_index,
                    kind=page_kind,
                    width=page_width,
                    height=page_height,
                    path=path,
                    options=options,
                    lines=lines,
                    warnings=warnings,
                )
                reconstructor = reconstructor_for(page_kind)
                index, page_blocks = reconstructor.reconstruct(ctx, index)
                if not page_blocks and page_kind not in {"digital", "mixed", "scanned"}:
                    warnings.append(
                        f"Page {page_no} {page_kind} reconstructor returned no blocks; falling back to letter."
                    )
                    index, page_blocks = letter.reconstruct(ctx, index)

                apply_heading_paths(page_blocks, stack)
                blocks.extend(page_blocks)
        except EncryptedArtifact:
            raise
        except ArtifactParseError:
            raise
        except Exception as exc:
            raise ArtifactParseError(f"Failed to extract PDF {path.name}: {exc}") from exc
        finally:
            document.close()

        if not blocks:
            warnings.append("No extractable text or tables found (possible scanned PDF).")

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
            artifact_type=ArtifactType.PDF,
            artifact_id=file_artifact_id(path),
            coord_system=COORD_PDF_POINTS,
            metadata=ArtifactMetadata(
                filename=path.name,
                artifact_type=ArtifactType.PDF,
                mime_type=MIME_BY_TYPE[ArtifactType.PDF],
                title=title,
                author=author,
                created=created,
                modified=modified,
                page_count=page_count,
                encrypted=encrypted,
            ),
            pages=pages,
            outline=outline,
            blocks=blocks,
            warnings=warnings,
        )


def _page_mediabox(page) -> tuple[float, float, float, float] | None:
    try:
        mediabox = page.mediabox
        crop = page.rect
        if (
            abs(float(mediabox.width) - float(crop.width)) < 0.5
            and abs(float(mediabox.height) - float(crop.height)) < 0.5
        ):
            return None
        return round_bbox(
            (float(mediabox.x0), float(mediabox.y0), float(mediabox.x1), float(mediabox.y1))
        )
    except Exception:
        return None


def _meta_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
