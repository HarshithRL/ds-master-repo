from __future__ import annotations

import zipfile
from pathlib import Path

from .exceptions import ArtifactNotFound, CorruptArtifact, UnsupportedArtifact
from .models import ArtifactType

OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
PDF_MAGIC = b"%PDF"
ZIP_MAGIC = b"PK"

EXTENSION_MAP = {
    ".pdf": ArtifactType.PDF,
    ".pptx": ArtifactType.PPT,
    ".ppt": ArtifactType.PPT,
    ".xlsx": ArtifactType.EXCEL,
    ".xlsm": ArtifactType.EXCEL,
    ".xls": ArtifactType.EXCEL,
    ".docx": ArtifactType.WORD,
    ".dotx": ArtifactType.WORD,
    ".doc": ArtifactType.WORD,
}

LEGACY_OLE_HINT = {
    ArtifactType.WORD: "legacy .doc (OLE)",
    ArtifactType.PPT: "legacy .ppt (OLE)",
    ArtifactType.EXCEL: "legacy .xls (OLE)",
}


class ArtifactClassifier:
    """Detect artifact type from extension and file signatures."""

    def classify(
        self,
        source: str | Path | bytes,
        filename: str | None = None,
    ) -> ArtifactType:
        name = filename or (Path(source).name if isinstance(source, (str, Path)) else "")
        ext_type = self._from_extension(name)

        header = self._header(source)
        magic_type = self._from_magic(source, header)

        if magic_type and ext_type and magic_type != ext_type:
            # Trust content over a mismatched extension.
            return magic_type
        if magic_type:
            return magic_type
        if ext_type:
            return ext_type

        raise UnsupportedArtifact(
            f"Unable to classify artifact{f' ({name})' if name else ''}."
        )

    def is_legacy(self, source: str | Path | bytes, filename: str | None = None) -> bool:
        name = filename or (Path(source).name if isinstance(source, (str, Path)) else "")
        ext = Path(name).suffix.lower()
        if ext in {".doc", ".ppt", ".xls"}:
            return True
        header = self._header(source)
        return header.startswith(OLE_MAGIC)

    @staticmethod
    def _from_extension(name: str) -> ArtifactType | None:
        if not name:
            return None
        return EXTENSION_MAP.get(Path(name).suffix.lower())

    def _from_magic(self, source: str | Path | bytes, header: bytes) -> ArtifactType | None:
        if header.startswith(PDF_MAGIC):
            return ArtifactType.PDF
        if header.startswith(OLE_MAGIC):
            # OLE container: rely on extension if present.
            return None
        if header.startswith(ZIP_MAGIC):
            return self._from_office_zip(source)
        return None

    def _from_office_zip(self, source: str | Path | bytes) -> ArtifactType | None:
        try:
            if isinstance(source, bytes):
                from io import BytesIO

                zf = zipfile.ZipFile(BytesIO(source))
            else:
                path = Path(source)
                if not path.is_file():
                    raise ArtifactNotFound(f"File not found: {path}")
                zf = zipfile.ZipFile(path)
        except zipfile.BadZipFile as exc:
            raise CorruptArtifact("File has a ZIP signature but is not a valid package.") from exc

        with zf:
            names = set(zf.namelist())
        if "word/document.xml" in names:
            return ArtifactType.WORD
        if "ppt/presentation.xml" in names:
            return ArtifactType.PPT
        if "xl/workbook.xml" in names:
            return ArtifactType.EXCEL
        return None

    def _header(self, source: str | Path | bytes, size: int = 8) -> bytes:
        if isinstance(source, bytes):
            return source[:size]
        path = Path(source)
        if not path.is_file():
            raise ArtifactNotFound(f"File not found: {path}")
        with path.open("rb") as handle:
            return handle.read(size)
