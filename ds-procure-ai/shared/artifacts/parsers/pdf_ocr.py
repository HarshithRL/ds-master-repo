from __future__ import annotations

from ..blocks import make_content_block
from ..models import BlockType, ContentBlock, SourceLocation
from .pdf_layout import PdfTextNormalizer


class PdfOcrFallback:
    def extract(self, page, warnings: list[str], page_no: int) -> str:
        try:
            import pytesseract
            from PIL import Image
        except ImportError:
            warnings.append(
                f"Page {page_no} looks scanned/design but OCR was requested and pytesseract is not installed."
            )
            return ""
        try:
            pixmap = page.get_pixmap(dpi=200)
            image = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
            text = pytesseract.image_to_string(image) or ""
            return PdfTextNormalizer().normalize(text)
        except Exception as exc:
            warnings.append(f"OCR failed on page {page_no}: {exc}")
            return ""

    def as_block(
        self,
        text: str,
        page_no: int,
        page_width: float,
        page_height: float,
        page_kind: str,
        index: int,
    ) -> tuple[int, ContentBlock]:
        index += 1
        block = make_content_block(
            seq_id=f"pdf-{index:04d}",
            block_type=BlockType.OCR,
            text=text,
            location=SourceLocation(
                page=page_no,
                page_width=page_width,
                page_height=page_height,
            ),
            extra={"engine": "ocr", "page_kind": page_kind},
        )
        return index, block
