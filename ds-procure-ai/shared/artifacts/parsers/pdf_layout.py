from __future__ import annotations

import re
from dataclasses import dataclass

from .pdf_geometry import vector_item_count

_LIGATURES = {
    "\ufb00": "ff",
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
    "\u2013": "-",
    "\u2014": "-",
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u00a0": " ",
}

_BOLD_FLAG = 1 << 4


@dataclass
class LayoutLine:
    text: str
    bbox: tuple[float, float, float, float]
    font_size: float
    bold: bool
    page: int


class PdfTextNormalizer:
    def normalize(self, text: str) -> str:
        for src, dst in _LIGATURES.items():
            text = text.replace(src, dst)
        text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def line(self, text: str) -> str:
        return self.normalize(text).replace("\n", " ").strip()


class PdfLayoutExtractor:
    def lines(self, page, page_no: int) -> list[LayoutLine]:
        normalizer = PdfTextNormalizer()
        raw: list[LayoutLine] = []
        try:
            data = page.get_text("dict")
        except Exception:
            return raw
        for block in data.get("blocks") or []:
            if block.get("type") != 0:
                continue
            for line in block.get("lines") or []:
                spans = line.get("spans") or []
                if not spans:
                    continue
                text = normalizer.line("".join(str(span.get("text") or "") for span in spans))
                if not text:
                    continue
                bbox = tuple(float(v) for v in line.get("bbox") or (0, 0, 0, 0))
                sizes = [float(span.get("size") or 0) for span in spans]
                flags = [int(span.get("flags") or 0) for span in spans]
                raw.append(
                    LayoutLine(
                        text=text,
                        bbox=(bbox[0], bbox[1], bbox[2], bbox[3]),
                        font_size=max(sizes) if sizes else 0.0,
                        bold=any(flag & _BOLD_FLAG for flag in flags),
                        page=page_no,
                    )
                )
        return sort_reading_lines(raw)


def sort_reading_lines(lines: list[LayoutLine]) -> list[LayoutLine]:
    return sorted(lines, key=lambda line: (round(line.bbox[1] / 12), line.bbox[0]))


_KPI_SCORE = re.compile(r"\b[A-E][+-]?\b|\b\d-\b|\b\d+\.\d{2}\b")
_YEAR_TOKEN = re.compile(r"\b((?:19|20)\d{2})\b")


class PdfPageClassifier:
    def classify(self, page) -> str:
        text = (page.get_text("text") or "").strip()
        n_chars = len(text)
        n_images = len(page.get_images())
        n_vectors = vector_item_count(page)
        n_tables = 0
        try:
            n_tables = len(page.find_tables().tables or [])
        except Exception:
            n_tables = 0
        short, long, x_clusters, n_lines = self._line_profile(page)

        if n_chars < 40 and n_images >= 1:
            return "scanned" if n_chars < 15 or n_images >= 2 else "design"
        if n_chars < 120 and n_images >= 1:
            return "design"

        year_grid = _looks_like_year_grid(text, short, n_lines)
        kpi_cover = _looks_like_kpi_cover(text, short, long, n_lines, n_tables)
        dashboard = (
            n_tables <= 1
            and n_lines >= 10
            and short >= 8
            and long <= 3
            and x_clusters >= 3
            and n_chars >= 80
        )
        chart = (
            40 <= n_chars < 500
            and long <= 1
            and (n_vectors >= 50 or n_images >= 1)
        )
        if year_grid:
            return "table"
        if dashboard and chart:
            if short >= 12 and n_chars >= 300:
                return "dashboard"
            return "chart"
        if dashboard or kpi_cover:
            return "dashboard"
        if chart:
            return "chart"

        if n_tables >= 2 or (n_vectors > 40 and n_chars < 1500):
            return "table"
        if n_tables and n_chars < 200:
            return "table"
        if n_chars == 0:
            return "scanned"
        return "digital"

    @staticmethod
    def _line_profile(page) -> tuple[int, int, int, int]:
        short = 0
        long = 0
        xs: set[int] = set()
        count = 0
        try:
            data = page.get_text("dict")
        except Exception:
            return 0, 0, 0, 0
        for block in data.get("blocks") or []:
            if block.get("type") != 0:
                continue
            for line in block.get("lines") or []:
                spans = line.get("spans") or []
                text = "".join(str(span.get("text") or "") for span in spans).strip()
                if not text:
                    continue
                count += 1
                if len(text) <= 40:
                    short += 1
                if len(text) > 80:
                    long += 1
                bbox = line.get("bbox") or (0, 0, 0, 0)
                xs.add(int(round(float(bbox[0]) / 40.0)))
        return short, long, len(xs), count


def _looks_like_kpi_cover(
    text: str, short: int, long: int, n_lines: int, n_tables: int
) -> bool:
    if n_tables > 1 or n_lines < 8 or short < 8 or long > 8:
        return False
    has_currency = any(ch in text for ch in "€$£")
    has_score = bool(_KPI_SCORE.search(text))
    return has_currency or has_score


def _looks_like_year_grid(text: str, short: int, n_lines: int) -> bool:
    years = sorted({int(match.group(1)) for match in _YEAR_TOKEN.finditer(text)})
    if len(years) < 3 or n_lines < 8 or short < 8:
        return False
    consecutive = sum(1 for a, b in zip(years, years[1:]) if b - a == 1)
    return consecutive >= 2
