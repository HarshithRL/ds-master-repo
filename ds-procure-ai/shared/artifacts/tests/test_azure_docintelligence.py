from types import SimpleNamespace

import pytest

from shared.artifacts.exceptions import ArtifactParseError
from shared.artifacts.models import ArtifactType, BlockType
from shared.artifacts.parsers.azure_docintelligence import document_from_layout
from shared.artifacts.parsers.registry import get_parser


def test_registry_pdf_ppt_word_use_azure_excel_stays():
    assert get_parser(ArtifactType.PDF).__class__.__name__ == "AzurePdfParser"
    assert get_parser(ArtifactType.PPT).__class__.__name__ == "AzurePptxParser"
    assert get_parser(ArtifactType.WORD).__class__.__name__ == "AzureDocxParser"
    assert get_parser(ArtifactType.EXCEL).__class__.__name__ == "XlsxParser"


def test_layout_maps_heading_table_and_skips_table_paragraph(tmp_path):
    path = tmp_path / "bid.pdf"
    path.write_bytes(b"%PDF-1.4 fake")
    paragraph = SimpleNamespace(
        content="Commercial offer",
        role="sectionHeading",
        spans=[SimpleNamespace(offset=0, length=16)],
        bounding_regions=[SimpleNamespace(page_number=1, polygon=[SimpleNamespace(x=1, y=1), SimpleNamespace(x=2, y=1), SimpleNamespace(x=2, y=2), SimpleNamespace(x=1, y=2)])],
    )
    table_paragraph = SimpleNamespace(
        content="Vendor | Price",
        role=None,
        spans=[SimpleNamespace(offset=20, length=14)],
        bounding_regions=[SimpleNamespace(page_number=1, polygon=[SimpleNamespace(x=1, y=3), SimpleNamespace(x=3, y=1.2)])],
    )
    table = SimpleNamespace(
        row_count=1,
        column_count=2,
        spans=[SimpleNamespace(offset=20, length=14)],
        cells=[
            SimpleNamespace(row_index=0, column_index=0, content="Vendor"),
            SimpleNamespace(row_index=0, column_index=1, content="Price"),
        ],
        bounding_regions=[SimpleNamespace(page_number=1, polygon=[SimpleNamespace(x=1, y=3), SimpleNamespace(x=4, y=4)])],
    )
    result = SimpleNamespace(
        pages=[SimpleNamespace(page_number=1, width=8.5, height=11, angle=0, lines=[])],
        paragraphs=[paragraph, table_paragraph],
        tables=[table],
        content="Commercial offer Vendor Price",
    )

    document = document_from_layout(path, ArtifactType.PDF, result, options=__import__("shared.artifacts.models", fromlist=["ParseOptions"]).ParseOptions())

    types = [block.type for block in document.blocks]
    assert BlockType.HEADING in types
    assert BlockType.TABLE in types
    assert all(block.text != "Vendor | Price" or block.type == BlockType.TABLE for block in document.blocks)
    table_block = next(block for block in document.blocks if block.type == BlockType.TABLE)
    assert table_block.table == [["Vendor", "Price"]]
    assert table_block.location.page == 1
    assert document.metadata.page_count == 1


def test_missing_azure_env_raises(monkeypatch, tmp_path):
    monkeypatch.delenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", raising=False)
    path = tmp_path / "bid.pdf"
    path.write_bytes(b"x")
    parser = get_parser(ArtifactType.PDF)
    with pytest.raises(ArtifactParseError, match="AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT"):
        parser.parse(path, __import__("shared.artifacts.models", fromlist=["ParseOptions"]).ParseOptions())
