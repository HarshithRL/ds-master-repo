"""Load markdown system prompts from disk and normalize message content."""

from __future__ import annotations

from pathlib import Path

_PROMPTS_DIR = (
    Path(__file__).resolve().parents[1] / "context_window" / "prompts"
)


def read_prompt(name: str | Path) -> str:
    """Read a markdown prompt file and return its stripped text.

    ``name`` may be a bare filename (resolved under ``context_window/prompts``),
    a relative path, or an absolute path.
    """
    path = Path(name)
    if not path.is_absolute():
        candidate = _PROMPTS_DIR / path
        path = candidate if candidate.exists() else path
    if not path.suffix:
        path = path.with_suffix(".md")
    if not path.exists():
        raise FileNotFoundError(f"prompt not found: {path}")
    return path.read_text(encoding="utf-8").strip()
