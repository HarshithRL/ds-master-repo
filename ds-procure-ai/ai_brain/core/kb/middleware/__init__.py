"""KB agent middleware helpers."""

from ai_brain.core.kb.middleware.strip_tool_content_ids import (
    StripToolContentIdsMiddleware,
    strip_content_block_ids,
)

__all__ = [
    "StripToolContentIdsMiddleware",
    "strip_content_block_ids",
]
