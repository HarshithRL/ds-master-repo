"""Procurement skills pack — versioned artifacts for StoreBackend.

Repo layout matches `deepagents-customization.md` §4. Deploy-sync writes
to namespace `("procurement-skills",)` at `/procurement/{skill}/SKILL.md`
(CompositeBackend strips the `/skills/` route prefix).

Adaptation: `evidence` has `model_version` + `prompt_version` only
(W0). There is no `skills_pack_version` column. Callers should pass
`SKILLS_PACK_VERSION` alongside `prompt_version` when upsert lands;
do not ALTER mate.sqlite.
"""

from __future__ import annotations

from pathlib import Path

SKILLS_PACK_VERSION = "1.0.0"
SKILLS_NAMESPACE: tuple[str, ...] = ("procurement-skills",)
SKILL_NAMES: tuple[str, ...] = (
    "swift-csp",
    "rfp-evaluation",
    "pricing-normalization",
    "be-entity-registry",
    "evidence-citation",
    "direct-tg",
)
STORE_PREFIX = "/procurement"

_PACK_DIR = Path(__file__).resolve().parent


def pack_dir() -> Path:
    return _PACK_DIR


def skill_md_path(name: str) -> Path:
    return _PACK_DIR / name / "SKILL.md"


def skill_store_key(name: str) -> str:
    """Key as StoreBackend sees it after `/skills/` is stripped."""
    return f"{STORE_PREFIX}/{name}/SKILL.md"


def iter_skill_files() -> list[tuple[str, Path]]:
    return [(name, skill_md_path(name)) for name in SKILL_NAMES]


def skills_pack_version_for_evidence() -> str:
    """Value to record on evidence when a column exists; until then log/adapt."""
    return SKILLS_PACK_VERSION
