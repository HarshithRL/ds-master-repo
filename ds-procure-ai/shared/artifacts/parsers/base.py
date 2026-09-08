from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ..models import ArtifactDocument, ArtifactType, ParseOptions


class ArtifactParser(Protocol):
    kind: ArtifactType

    def parse(self, path: Path, options: ParseOptions) -> ArtifactDocument:
        ...
