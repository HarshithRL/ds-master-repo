from __future__ import annotations

import tempfile
from pathlib import Path

from .classifier import ArtifactClassifier, LEGACY_OLE_HINT
from .exceptions import (
    ArtifactNotFound,
    ArtifactParseError,
    CorruptArtifact,
    EncryptedArtifact,
    UnsupportedArtifact,
)
from .models import ArtifactDocument, ArtifactType, ParseOptions, source_name
from .parsers.registry import LEGACY_EXTENSIONS, PARSEABLE_EXTENSIONS, parser_for
from shared.logger_global import get_logger

log = get_logger(__name__)


class ArtifactHandler:
    """Facade for artifact classification and structured parsing.

    Public surface:
        classify(source, filename=None) -> ArtifactType  # pdf | ppt | excel | word
        parse(source, artifact_type=None, ...) -> ArtifactDocument
    """

    SUPPORTED_TYPES = (ArtifactType.PDF, ArtifactType.PPT, ArtifactType.EXCEL, ArtifactType.WORD)

    def __init__(self) -> None:
        self._classifier = ArtifactClassifier()

    def classify(
        self,
        source: str | Path | bytes,
        filename: str | None = None,
    ) -> ArtifactType:
        """Classify an artifact as pdf, ppt, excel, or word.

        Uses file extension first, then magic bytes / Open XML package parts
        when the extension is missing or disagrees with the file body.
        """
        return self._classifier.classify(source, filename=filename)

    def parse(
        self,
        source: str | Path | bytes,
        artifact_type: ArtifactType | str | None = None,
        *,
        filename: str | None = None,
        options: ParseOptions | None = None,
    ) -> ArtifactDocument:
        """Parse a file with the parser that matches its artifact type.

        If artifact_type is omitted, classify() is called first.
        """
        options = options or ParseOptions()
        resolved_type = self._resolve_type(source, artifact_type, filename)
        self._reject_legacy(source, resolved_type, filename)

        path, cleanup = self._as_path(source, filename)
        try:
            if not path.is_file():
                raise ArtifactNotFound(f"File not found: {path}")
            parser = parser_for(resolved_type)
            parser_name = parser.__class__.__name__
            log.info(
                "artifact parse start parser={} type={} file={}",
                parser_name,
                resolved_type.value,
                path.name,
            )
            document = parser.parse(path, options)
            document.parser = parser_name
            document.source = str(source) if not isinstance(source, bytes) else source_name(source, filename)
            log.info(
                "artifact parse done parser={} type={} file={} blocks={} pages={}",
                parser_name,
                resolved_type.value,
                path.name,
                len(document.blocks),
                len(document.pages),
            )
            from ._markdown_convertor import MarkdownConvertor

            document.markdown = MarkdownConvertor().convert(document).rstrip("\n")
            from .chunking import chunk_document

            document.chunks = chunk_document(document)
            return document
        except (ArtifactNotFound, UnsupportedArtifact, EncryptedArtifact, CorruptArtifact, ArtifactParseError):
            raise
        except Exception as exc:
            raise ArtifactParseError(
                f"Unexpected parse failure for {source_name(source, filename)}: {exc}"
            ) from exc
        finally:
            if cleanup:
                path.unlink(missing_ok=True)

    def _resolve_type(
        self,
        source: str | Path | bytes,
        artifact_type: ArtifactType | str | None,
        filename: str | None,
    ) -> ArtifactType:
        if artifact_type is None:
            return self.classify(source, filename=filename)
        if isinstance(artifact_type, ArtifactType):
            return artifact_type
        try:
            return ArtifactType(str(artifact_type).strip().lower())
        except ValueError as exc:
            raise UnsupportedArtifact(
                f"Unknown artifact type '{artifact_type}'. "
                f"Expected one of: {', '.join(t.value for t in self.SUPPORTED_TYPES)}"
            ) from exc

    def _reject_legacy(
        self,
        source: str | Path | bytes,
        artifact_type: ArtifactType,
        filename: str | None,
    ) -> None:
        name = source_name(source, filename)
        ext = Path(name).suffix.lower()
        allowed = PARSEABLE_EXTENSIONS[artifact_type]
        if ext in LEGACY_EXTENSIONS or self._classifier.is_legacy(source, filename=filename):
            hint = LEGACY_OLE_HINT.get(artifact_type, "legacy Office binary")
            raise UnsupportedArtifact(
                f"{name} looks like {hint}. Convert to {sorted(allowed)} before parsing."
            )

    def _as_path(
        self,
        source: str | Path | bytes,
        filename: str | None,
    ) -> tuple[Path, bool]:
        if isinstance(source, bytes):
            suffix = Path(filename or "upload.bin").suffix or ".bin"
            handle = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            handle.write(source)
            handle.close()
            return Path(handle.name), True
        return Path(source), False
