from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from pathlib import Path

from .pdf_geometry import round_bbox, vector_item_count

MAX_TABLES_PER_PAGE = 12
PDFPLUMBER_TIMEOUT_SEC = 8.0


def drop_empty_columns(table: list[list[str]]) -> list[list[str]]:
    if not table:
        return []
    width = max(len(row) for row in table)
    keep = [
        col
        for col in range(width)
        if any((row[col] if col < len(row) else "").strip() for row in table)
    ]
    if not keep:
        return []
    return [[(row[col] if col < len(row) else "") for col in keep] for row in table]


def clean_table(table: list[list[object]] | None) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in table or []:
        cells = ["" if cell is None else str(cell).strip() for cell in row]
        if any(cells):
            rows.append(cells)
    return drop_empty_columns(rows)


def table_to_text(table: list[list[str]]) -> str:
    return "\n".join(" | ".join(row) for row in table)


class PdfTableExtractor:
    def extract(
        self,
        page,
        path: Path,
        page_index: int,
        kind: str,
        password: str | None,
    ) -> list[tuple[list[list[str]], tuple[float, float, float, float], str]]:
        found: list[tuple[list[list[str]], tuple[float, float, float, float], str]] = []
        try:
            for table in page.find_tables().tables or []:
                matrix = clean_table(table.extract())
                if len(matrix) < 2 or max(len(row) for row in matrix) < 2:
                    continue
                bbox = round_bbox(tuple(float(v) for v in table.bbox))
                found.append((matrix, bbox, "pymupdf.find_tables"))
        except Exception:
            found = []

        if found:
            return found[:MAX_TABLES_PER_PAGE]
        line_heavy = kind == "table" or vector_item_count(page) >= 40
        if not line_heavy:
            return found
        fallback = self._pdfplumber_fallback(path, page_index, password)
        return fallback[:MAX_TABLES_PER_PAGE]

    def _pdfplumber_fallback(
        self, path: Path, page_index: int, password: str | None
    ) -> list[tuple[list[list[str]], tuple[float, float, float, float], str]]:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self._pdfplumber_run, path, page_index, password)
            try:
                return future.result(timeout=PDFPLUMBER_TIMEOUT_SEC)
            except FuturesTimeout:
                return []

    def _pdfplumber_run(
        self, path: Path, page_index: int, password: str | None
    ) -> list[tuple[list[list[str]], tuple[float, float, float, float], str]]:
        try:
            import pdfplumber
        except ImportError:
            return []
        results: list[tuple[list[list[str]], tuple[float, float, float, float], str]] = []
        try:
            with pdfplumber.open(str(path), password=password or "") as pdf:
                if page_index >= len(pdf.pages):
                    return []
                plumber_page = pdf.pages[page_index]
                found = plumber_page.find_tables()
                tables = list(getattr(found, "tables", found) or [])
                if not tables:
                    extracted = plumber_page.extract_tables() or []
                    for table in extracted:
                        matrix = clean_table(table)
                        if len(matrix) < 2 or max(len(row) for row in matrix) < 2:
                            continue
                        bbox = round_bbox(
                            (0.0, 0.0, float(plumber_page.width or 0), float(plumber_page.height or 0))
                        )
                        results.append((matrix, bbox, "pdfplumber.extract_tables"))
                    return results
                for table in tables:
                    matrix = clean_table(table.extract())
                    if len(matrix) < 2 or max(len(row) for row in matrix) < 2:
                        continue
                    bbox = round_bbox(tuple(float(v) for v in table.bbox))
                    results.append((matrix, bbox, "pdfplumber.find_tables"))
        except Exception:
            return []
        return results
