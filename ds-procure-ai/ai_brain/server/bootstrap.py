"""Ensure repo root is on ``sys.path`` so ``ai_brain`` and ``shared`` import."""

from __future__ import annotations

import sys
from pathlib import Path


def ensure_repo_root() -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    brain_dir = Path(__file__).resolve().parents[1]
    if str(brain_dir) in sys.path:
        sys.path.remove(str(brain_dir))
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    _install_windows_selector_loop()
    _patch_starlette_router()
    return repo_root


def _install_windows_selector_loop() -> None:
    """psycopg async cannot run on Windows ProactorEventLoop."""
    if sys.platform != "win32":
        return
    import asyncio

    policy_cls = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
    if policy_cls is None:
        return
    if isinstance(asyncio.get_event_loop_policy(), policy_cls):
        return
    asyncio.set_event_loop_policy(policy_cls())


def _patch_starlette_router() -> None:
    """FastAPI 0.115 still passes on_startup/on_shutdown; Starlette 1.6 dropped them."""
    from starlette.routing import Router

    if getattr(Router.__init__, "_ai_brain_patched", False):
        return

    original = Router.__init__

    def patched(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        kwargs.pop("on_startup", None)
        kwargs.pop("on_shutdown", None)
        return original(self, *args, **kwargs)

    patched._ai_brain_patched = True  # type: ignore[attr-defined]
    Router.__init__ = patched  # type: ignore[method-assign]
