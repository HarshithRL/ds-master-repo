from __future__ import annotations

from .base import PdfReconstructor, ReconstructPage
from .chart import ChartReconstructor
from .cover import CoverReconstructor
from .dashboard import DashboardReconstructor, cluster_tiles, tile_text
from .grid import GridReconstructor, rebuild_table_from_lines
from .letter import LetterReconstructor
from .scanned import ScannedReconstructor

_KIND_TO_NAME = {
    "digital": "letter",
    "mixed": "letter",
    "dashboard": "dashboard",
    "table": "grid",
    "design": "cover",
    "chart": "chart",
    "scanned": "scanned",
}

_REGISTRY = {
    "letter": LetterReconstructor(),
    "dashboard": DashboardReconstructor(),
    "grid": GridReconstructor(),
    "cover": CoverReconstructor(),
    "chart": ChartReconstructor(),
    "scanned": ScannedReconstructor(),
}


def reconstructor_for(kind: str) -> PdfReconstructor:
    name = _KIND_TO_NAME.get(kind, "letter")
    return _REGISTRY[name]


__all__ = [
    "PdfReconstructor",
    "ReconstructPage",
    "reconstructor_for",
    "cluster_tiles",
    "tile_text",
    "rebuild_table_from_lines",
]
