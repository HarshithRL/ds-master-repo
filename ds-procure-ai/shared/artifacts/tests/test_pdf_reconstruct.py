from __future__ import annotations

from shared.artifacts.parsers.pdf_geometry import contained_in, covered_by_any
from shared.artifacts.parsers.pdf_headings import lines_to_blocks
from shared.artifacts.parsers.pdf_layout import LayoutLine
from shared.artifacts.parsers.pdf_reconstruct.columns import split_text_columns
from shared.artifacts.parsers.pdf_reconstruct.dashboard import cluster_tiles, tile_text
from shared.artifacts.parsers.pdf_reconstruct.grid import rebuild_table_from_lines


def _line(text: str, x0: float, y0: float, x1: float, y1: float, size: float = 10.0) -> LayoutLine:
    return LayoutLine(text=text, bbox=(x0, y0, x1, y1), font_size=size, bold=False, page=1)


def test_dashboard_merges_credit_limit_tile():
    lines = [
        _line("Credit Limit", 50, 50, 180, 64),
        _line("€1,750,000", 50, 66, 180, 82, 14),
        _line("International Score", 240, 50, 400, 64),
        _line("B", 240, 66, 280, 82, 14),
    ]
    clusters = cluster_tiles(lines)
    texts = [tile_text(group) for group in clusters]
    assert any("Credit Limit" in text and "1,750,000" in text for text in texts)
    assert any("International Score" in text and "B" in text for text in texts)
    assert not any(text.strip() == "B" for text in texts)


def test_columns_do_not_weave_phone_and_registration():
    lines = [
        _line("Company", 50, 40, 180, 54, 12),
        _line("Etex NV", 70, 60, 200, 74),
        _line("Registration Number", 55, 80, 230, 94),
        _line("BE 123", 90, 96, 200, 110),
        _line("Contact", 320, 40, 460, 54, 12),
        _line("+32 27 08 43 00", 330, 60, 480, 74),
        _line("info@etex.com", 340, 80, 480, 94),
    ]
    split = split_text_columns(lines, 595.0)
    assert split is not None
    left, right, _split_x = split
    _, left_blocks = lines_to_blocks(left, "mixed", 1, 0, 595.0, 842.0, "letter")
    _, right_blocks = lines_to_blocks(right, "mixed", 1, 20, 595.0, 842.0, "letter")
    woven = [
        block.text
        for block in [*left_blocks, *right_blocks]
        if "+32" in block.text and "Registration" in block.text
    ]
    assert not woven
    assert any("+32 27 08 43 00" in block.text for block in right_blocks)


def test_grid_rebuilds_aligned_cells():
    lines: list[LayoutLine] = []
    headers = ["Account", "Balance", "Status"]
    for col, header in enumerate(headers):
        lines.append(_line(header, 40 + col * 120, 40, 140 + col * 120, 54))
    for row in range(4):
        lines.append(_line(f"A{row}", 40, 70 + row * 16, 140, 84 + row * 16))
        lines.append(_line(f"{row}00", 160, 70 + row * 16, 260, 84 + row * 16))
        lines.append(_line("Open", 280, 70 + row * 16, 380, 84 + row * 16))
    rebuilt = rebuild_table_from_lines(lines)
    assert rebuilt is not None
    matrix, bbox = rebuilt
    assert len(matrix) >= 4
    assert max(len(row) for row in matrix) >= 3
    assert bbox[2] > bbox[0]


def test_grid_keeps_year_columns():
    years = ["2024", "2023", "2022", "2021", "2020"]
    lines = [_line("Year to Date", 40, 40, 140, 54)]
    for index, year in enumerate(years):
        lines.append(_line(year, 160 + index * 80, 40, 230 + index * 80, 54))
    lines.append(_line("Turnover", 40, 70, 140, 84))
    amounts = [
        "€99,377,231.6",
        "€92,364,140",
        "€75,261,345",
        "€64,299,329",
        "€60,858,911",
    ]
    for index, amount in enumerate(amounts):
        lines.append(_line(amount, 160 + index * 80, 70, 230 + index * 80, 84))
    lines.append(_line("Investments", 40, 100, 140, 114))
    lines.append(_line("€815", 160 + 3 * 80, 100, 230 + 3 * 80, 114))
    rebuilt = rebuild_table_from_lines(lines)
    assert rebuilt is not None
    matrix, bbox = rebuilt
    flat = " ".join(cell for row in matrix for cell in row)
    digits = "".join(ch for ch in flat if ch.isdigit())
    assert "99377231" in digits
    present = {cell.strip() for row in matrix for cell in row}
    assert present.issuperset(years)
    assert bbox[2] > bbox[0]


def test_table_line_containment():
    table = (40.0, 40.0, 400.0, 300.0)
    cell = (50.0, 50.0, 90.0, 64.0)
    outside = (420.0, 50.0, 500.0, 64.0)
    assert contained_in(cell, table)
    assert covered_by_any(cell, [table])
    assert not covered_by_any(outside, [table])
