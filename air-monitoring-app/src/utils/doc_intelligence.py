"""
Azure Document Intelligence integration for Air Monitoring V2.
"""
from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential
from utils.config import DOC_INTELLIGENCE_ENDPOINT, DOC_INTELLIGENCE_KEY


def _get_client() -> DocumentAnalysisClient:
    """Get Azure Document Intelligence client."""
    if not DOC_INTELLIGENCE_ENDPOINT or not DOC_INTELLIGENCE_KEY:
        raise ValueError(
            "DOC_INTELLIGENCE_ENDPOINT and DOC_INTELLIGENCE_KEY must be set."
        )
    return DocumentAnalysisClient(
        endpoint=DOC_INTELLIGENCE_ENDPOINT,
        credential=AzureKeyCredential(DOC_INTELLIGENCE_KEY)
    )


def extract_from_pdf(pdf_bytes: bytes) -> dict:
    """
    Extract tables and text from a PDF using Azure Document Intelligence.
    Uses prebuilt-layout model.
    """
    client = _get_client()
    
    poller = client.begin_analyze_document(
        model_id="prebuilt-layout",
        document=pdf_bytes
    )
    result = poller.result()
    
    # Extract tables as grid
    tables = []
    for table in result.tables:
        max_row = max(cell.row_index for cell in table.cells) + 1
        max_col = max(cell.column_index for cell in table.cells) + 1
        grid = [["" for _ in range(max_col)] for _ in range(max_row)]
        for cell in table.cells:
            grid[cell.row_index][cell.column_index] = cell.content
        tables.append({
            "rows": grid,
            "row_count": max_row,
            "col_count": max_col,
            "header": grid[0] if grid else []
        })
    
    # Extract paragraphs
    paragraphs = []
    for paragraph in result.paragraphs:
        paragraphs.append({
            "content": paragraph.content,
            "role": getattr(paragraph, "role", None),
        })
    
    return {
        "tables": tables,
        "paragraphs": paragraphs,
        "pages": len(result.pages),
    }
