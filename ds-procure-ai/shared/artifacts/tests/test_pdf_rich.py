from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from shared.artifacts import ArtifactHandler, ParseOptions
from shared.artifacts.citations import citation_from_block
from shared.artifacts.models import BlockType, COORD_PDF_POINTS

DEFAULT_FIXTURES = Path(r"D:\Work\Etex\Simple example")

BDO = "Etex - SWIFT Support Independent Assessment_v20260312.pdf"
PWC = "Etex & PwC - SWIFT CSP attestation FY26 - March 2026.pdf"
INETUM = "TF Inetum Proposal Etex CSP Assessment.pdf"
ECOVADIS = "EcoVadis"
GRAYDON = "Graydon"


def _fixture_dir() -> Path:
    return Path(os.environ.get("ARTIFACT_FIXTURES_DIR", str(DEFAULT_FIXTURES)))


def _require(name: str) -> Path:
    path = _fixture_dir() / name
    if not path.is_file():
        pytest.skip(f"missing fixture: {path}")
    return path


def _find_named(fragment: str) -> Path:
    root = _fixture_dir()
    if not root.is_dir():
        pytest.skip(f"missing fixture dir: {root}")
    matches = sorted(root.glob(f"*{fragment}*"))
    pdfs = [path for path in matches if path.suffix.lower() == ".pdf"]
    if not pdfs:
        pytest.skip(f"missing fixture matching {fragment!r} in {root}")
    return pdfs[0]


@pytest.fixture(scope="module")
def handler() -> ArtifactHandler:
    return ArtifactHandler()


def test_bdo_contract_and_page13_table(handler: ArtifactHandler):
    path = _require(BDO)
    doc = handler.parse(path)
    payload = doc.to_dict()

    for key in ("artifact_id", "coord_system", "pages", "blocks", "markdown", "outline"):
        assert key in payload
    assert "action" not in payload
    assert "plain_text" not in payload
    assert "MD_text" not in payload
    assert payload["artifact_id"].startswith("sha256:")
    assert payload["coord_system"] == COORD_PDF_POINTS
    assert payload["metadata"]["page_count"] == 21

    ids = [block.block_id for block in doc.blocks]
    assert all(item.startswith("b_") for item in ids)
    assert len(ids) == len(set(ids))

    filename = path.name
    assert all(filename not in block.text for block in doc.blocks)
    assert not any(block.text.strip().upper().startswith("ETEX GROUP I") for block in doc.blocks)
    assert not any("Printed On" in block.text for block in doc.blocks)
    assert not any(re.search(r"(?i)^page\s+\d+\s+of\s+\d+$", block.text.strip()) for block in doc.blocks)
    assert not any(block.type == BlockType.OCR for block in doc.blocks)

    page1 = [block for block in doc.blocks if block.location.page == 1]
    assert len(page1) <= 6
    assert any(
        block.type == BlockType.HEADING and "Independent Assessment" in block.text
        for block in page1
    )

    tables = [
        block
        for block in doc.blocks
        if block.type == BlockType.TABLE and block.location.page == 13
    ]
    assert tables, "page 13 fee table missing"
    fee = next((block for block in tables if "35.251" in (block.text or "")), None)
    assert fee is not None
    assert fee.location.bbox is not None
    assert fee.location.page_width
    assert fee.location.page_height
    assert any("3.2 Summary" in path_item for path_item in fee.heading_path)

    markdown = payload["markdown"]
    assert "artifact_id:" in markdown
    assert "coord_system:" in markdown
    assert "<!-- loc " in markdown
    assert re.search(r"<!-- loc page=13 block=b_[0-9a-f]+ type=table -->", markdown)
    assert f"*{filename}" not in markdown
    assert "page_count:" not in markdown.split("---", 2)[-1]

    citation = citation_from_block(fee, doc.artifact_id, doc.coord_system)
    assert citation["block_id"] == fee.block_id
    assert citation["page"] == 13
    assert citation["bbox"]


def test_pwc_design_pages_not_empty(handler: ArtifactHandler):
    path = _require(PWC)
    doc = handler.parse(path, options=ParseOptions(max_pages=6))
    design_pages = {page.page for page in doc.pages if page.kind == "design"}
    if not design_pages:
        pytest.skip("no design pages classified in first 6 PwC pages")
    for page_no in design_pages:
        blocks = [block for block in doc.blocks if block.location.page == page_no]
        assert blocks, f"design page {page_no} is empty"
        assert not any(block.type == BlockType.CHART for block in blocks)


def test_inetum_mixed_table_and_visual(handler: ArtifactHandler):
    path = _require(INETUM)
    doc = handler.parse(path)
    assert "mixed" not in {page.kind for page in doc.pages}
    assert any(block.type == BlockType.TABLE for block in doc.blocks)
    assert any(block.type in {BlockType.IMAGE, BlockType.CHART} for block in doc.blocks)


def test_ecovadis_optional_no_invented_scores(handler: ArtifactHandler):
    path = _find_named(ECOVADIS)
    doc = handler.parse(path)
    visuals = [block for block in doc.blocks if block.type in {BlockType.IMAGE, BlockType.CHART}]
    assert visuals
    for block in visuals:
        assert not re.search(r"\b(9\d|/100)\b", block.text)


def test_graydon_optional_table_cap(handler: ArtifactHandler):
    path = _find_named(GRAYDON)
    doc = handler.parse(path)
    by_page: dict[int, int] = {}
    cells = 0
    for block in doc.blocks:
        if block.type != BlockType.TABLE:
            continue
        page = block.location.page or 0
        by_page[page] = by_page.get(page, 0) + 1
        if block.table:
            cells += sum(len(row) for row in block.table)
    assert not by_page or max(by_page.values()) <= 12
    assert cells < 900

    page1 = [block for block in doc.blocks if block.location.page == 1]
    assert page1
    assert len(page1) <= 40
    headings = [block for block in page1 if block.type == BlockType.HEADING]
    assert len(headings) <= 8
    credit = next(
        (
            block
            for block in page1
            if "Credit Limit" in block.text
            and "1750000" in block.text.replace(" ", "").replace(",", "").replace(".", "")
        ),
        None,
    )
    if credit is not None:
        assert credit.type == BlockType.TEXT

    page2_chips = [
        block
        for block in doc.blocks
        if block.location.page == 2
        and block.type in {BlockType.TEXT, BlockType.HEADING}
        and len(block.text.strip()) < 24
    ]
    assert len(page2_chips) <= 12


def test_creditsafe_kpmg_pages(handler: ArtifactHandler):
    path = _find_named("439819279")
    doc = handler.parse(path)

    page1_info = next(page for page in doc.pages if page.page == 1)
    assert page1_info.kind == "dashboard"
    page1 = [block for block in doc.blocks if block.location.page == 1]
    assert len(page1) <= 30
    assert any(
        "Credit Limit" in block.text
        and "1750000" in block.text.replace(" ", "").replace(",", "").replace(".", "")
        for block in page1
    )
    assert any(
        "International Score" in block.text and re.search(r"\bB\b", block.text)
        for block in page1
    )
    assert not any("Printed By" in block.text for block in page1)
    assert not any("Page 1 of 23" in block.text for block in page1)

    page2_tables = [
        block
        for block in doc.blocks
        if block.location.page == 2 and block.type == BlockType.TABLE
    ]
    assert any(
        "99377231" in "".join(ch for ch in (block.text or "") if ch.isdigit())
        for block in page2_tables
    )
    page2_chips = [
        block
        for block in doc.blocks
        if block.location.page == 2
        and block.type in {BlockType.TEXT, BlockType.HEADING}
        and len(block.text.strip()) < 24
    ]
    assert len(page2_chips) <= 12

    page19_headings = [
        block
        for block in doc.blocks
        if block.location.page == 19 and block.type == BlockType.HEADING
    ]
    assert len(page19_headings) < 20
