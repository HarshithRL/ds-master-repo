from __future__ import annotations

from ..exceptions import UnsupportedArtifact
from ..models import ArtifactType
from .azure_docintelligence import AzureDocxParser, AzurePdfParser, AzurePptxParser
from .xlsx_parser import XlsxParser

# pdf_parser, pptx_parser, and docx_parser stay on disk. Registry only rebinds.
_PARSERS = {
    ArtifactType.PDF: AzurePdfParser,
    ArtifactType.PPT: AzurePptxParser,
    ArtifactType.EXCEL: XlsxParser,
    ArtifactType.WORD: AzureDocxParser,
}

# Modern Open XML only. Classifier may still label legacy binaries.
PARSEABLE_EXTENSIONS = {
    ArtifactType.PDF: {".pdf"},
    ArtifactType.PPT: {".pptx"},
    ArtifactType.EXCEL: {".xlsx", ".xlsm"},
    ArtifactType.WORD: {".docx", ".dotx"},
}

LEGACY_EXTENSIONS = {".doc", ".ppt", ".xls"}


def get_parser(artifact_type: ArtifactType):
    try:
        return _PARSERS[artifact_type]()
    except KeyError as exc:
        raise UnsupportedArtifact(f"No parser registered for type: {artifact_type}") from exc


def parser_for(artifact_type: ArtifactType | str):
    if isinstance(artifact_type, str):
        try:
            artifact_type = ArtifactType(artifact_type.lower())
        except ValueError as exc:
            raise UnsupportedArtifact(f"Unknown artifact type: {artifact_type}") from exc
    return get_parser(artifact_type)
