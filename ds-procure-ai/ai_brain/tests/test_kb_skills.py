"""Skills pack files, version string, and deploy-sync into an in-memory store."""

from __future__ import annotations

from langgraph.store.memory import InMemoryStore

from ai_brain.core.kb.skills import (
    SKILL_NAMES,
    SKILLS_NAMESPACE,
    SKILLS_PACK_VERSION,
    iter_skill_files,
    skill_store_key,
    skills_pack_version_for_evidence,
)
from ai_brain.core.kb.skills.sync import sync_skills_pack


def test_skills_pack_version_defined():
    assert isinstance(SKILLS_PACK_VERSION, str) and SKILLS_PACK_VERSION.strip()
    assert skills_pack_version_for_evidence() == SKILLS_PACK_VERSION


def test_skill_md_files_exist():
    assert SKILL_NAMES == (
        "swift-csp",
        "rfp-evaluation",
        "pricing-normalization",
        "be-entity-registry",
        "evidence-citation",
        "direct-tg",
        "comparison-matrix",
    )
    for name, path in iter_skill_files():
        assert path.is_file(), name
        text = path.read_text(encoding="utf-8")
        assert text.startswith("---\n")
        assert f"name: {name}" in text
        assert "description:" in text


def test_sync_skills_pack_to_memory_store():
    store = InMemoryStore()
    result = sync_skills_pack(store)
    assert result["version"] == SKILLS_PACK_VERSION
    assert result["namespace"] == list(SKILLS_NAMESPACE)
    assert len(result["files"]) == len(SKILL_NAMES) + 1
    for name in SKILL_NAMES:
        item = store.get(SKILLS_NAMESPACE, skill_store_key(name))
        assert item is not None, name
        assert "SKILL.md" in skill_store_key(name)
        content = item.value["content"]
        assert f"name: {name}" in content
    version_item = store.get(SKILLS_NAMESPACE, "/procurement/VERSION")
    assert version_item.value["content"] == SKILLS_PACK_VERSION


def test_ensure_skills_store_can_list_without_langgraph_store():
    from deepagents.backends import StoreBackend

    from ai_brain.core.kb.skills.sync import ensure_skills_store

    store = ensure_skills_store()
    assert store is not None
    backend = StoreBackend(
        namespace=lambda _rt: ("procurement-skills",),
        store=store,
    )
    listed = backend.ls("/procurement/")
    assert listed.error is None
    entries = listed.entries or []
    blob = " ".join(str(item.get("path", "")) for item in entries)
    assert "swift-csp" in blob
