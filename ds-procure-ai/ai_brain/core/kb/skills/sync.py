"""Deploy-sync the procurement skills pack into a LangGraph BaseStore."""

from __future__ import annotations

import threading
from typing import Any

from ai_brain.core.kb.skills import (
    SKILLS_NAMESPACE,
    SKILLS_PACK_VERSION,
    STORE_PREFIX,
    iter_skill_files,
    skill_store_key,
)

_LOCK = threading.Lock()
_FALLBACK_STORE: Any | None = None
_SYNCED_IDS: set[int] = set()


def _file_value(content: str) -> dict[str, Any]:
    from deepagents.backends.utils import create_file_data

    return dict(create_file_data(content))


def sync_skills_pack(store: Any) -> dict[str, Any]:
    """Write SKILL.md files + VERSION into `store` (idempotent put)."""
    missing = [name for name, path in iter_skill_files() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"missing SKILL.md for: {', '.join(missing)}")

    written: list[str] = []
    for name, path in iter_skill_files():
        key = skill_store_key(name)
        store.put(SKILLS_NAMESPACE, key, _file_value(path.read_text(encoding="utf-8")))
        written.append(key)

    version_key = f"{STORE_PREFIX}/VERSION"
    store.put(SKILLS_NAMESPACE, version_key, _file_value(SKILLS_PACK_VERSION))
    written.append(version_key)
    return {
        "version": SKILLS_PACK_VERSION,
        "namespace": list(SKILLS_NAMESPACE),
        "files": written,
    }


def ensure_skills_store(store: Any | None = None) -> Any:
    """Return a BaseStore that StoreBackend can `search`, with the skills pack loaded.

    Vendor extraction compiles `StoreBackend` for `/skills/` but kb_build often
    runs outside the Nexus graph (background thread, `build_procura_ai()` with
    no `store=`). LangGraph `get_store()` then returns None and SkillsMiddleware
    crashes with `'NoneType' object has no attribute 'search'`.
    """
    resolved = store if store is not None else _lookup_store()
    if resolved is None:
        resolved = _fallback_store()
    _sync_once(resolved)
    return resolved


def _lookup_store() -> Any | None:
    try:
        from langgraph.config import get_store

        found = get_store()
        if found is not None:
            return found
    except Exception:
        pass
    try:
        from ai_brain.server.runtime import runtime

        found = getattr(runtime, "store", None)
        if found is not None:
            return found
    except Exception:
        pass
    return None


def _fallback_store() -> Any:
    global _FALLBACK_STORE
    from langgraph.store.memory import InMemoryStore

    with _LOCK:
        if _FALLBACK_STORE is None:
            _FALLBACK_STORE = InMemoryStore()
        return _FALLBACK_STORE


def _sync_once(store: Any) -> None:
    ident = id(store)
    with _LOCK:
        if ident in _SYNCED_IDS:
            return
        sync_skills_pack(store)
        _SYNCED_IDS.add(ident)
