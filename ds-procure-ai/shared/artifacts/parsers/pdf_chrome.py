from __future__ import annotations

import re
from collections import Counter

from .pdf_layout import PdfLayoutExtractor

_HEADER_NOISE = re.compile(
    r"(?i)^("
    r"etex\s+group(\s*[|I]\s*\d+)?"
    r"|confidential"
    r"|printed\s+on(\s*[:.].*)?"
    r"|printed\s+by(\s*[:.].*)?"
    r"|page\s+\d+(\s+of\s+\d+)?"
    r"|page\s+\d+\s*/\s*\d+"
    r"|\d+\s*/\s*\d+"
    r"|\d{1,3}"
    r")$"
)
_PRINTED_BY = re.compile(r"(?i)\bprinted\s+by\b")
_COMPANY_PRINTED_BY = re.compile(r"(?i)\bcompany\s*:.*\bprinted\s+by\b")


def chrome_key(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def is_header_noise(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    if _HEADER_NOISE.match(stripped):
        return True
    lowered = chrome_key(stripped)
    if lowered.startswith("etex group i") or lowered.startswith("etex group |"):
        return True
    if lowered.startswith("printed on") or lowered.startswith("printed by"):
        return True
    if _PRINTED_BY.search(stripped) or _COMPANY_PRINTED_BY.search(stripped):
        return True
    if re.match(r"(?i)^page\s+\d+(\s+of\s+\d+)?$", lowered):
        return True
    return False


class PdfHeaderFooterDetector:
    def detect(self, pages: list) -> set[str]:
        extractor = PdfLayoutExtractor()
        counts: Counter[str] = Counter()
        for index, page in enumerate(pages, start=1):
            height = page.rect.height or 1
            top = height * 0.10
            bottom = height * 0.90
            for line in extractor.lines(page, index):
                y0 = line.bbox[1]
                if y0 > top and y0 < bottom:
                    continue
                key = chrome_key(line.text)
                if key:
                    counts[key] += 1
        threshold = max(2, int(len(pages) * 0.4))
        return {key for key, seen in counts.items() if seen >= threshold}

    def is_chrome(
        self,
        text: str,
        bbox: tuple[float, float, float, float],
        page_height: float,
        chrome: set[str],
    ) -> bool:
        if is_header_noise(text):
            return True
        key = chrome_key(text)
        if key and key in chrome:
            return True
        y0 = bbox[1]
        in_band = y0 <= page_height * 0.10 or y0 >= page_height * 0.90
        if in_band and (is_header_noise(text) or (key and key in chrome)):
            return True
        if in_band and re.fullmatch(r"\d{1,3}", text.strip()):
            return True
        return False
