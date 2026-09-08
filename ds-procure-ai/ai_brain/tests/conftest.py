"""Pytest path + in-memory STM/LTM backends for ai_brain tests."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BRAIN_CHECKPOINT_BACKEND", "memory")
os.environ.setdefault("BRAIN_STORE_BACKEND", "memory")
os.environ.setdefault("MLFLOW_EXPERIMENT_NAME", "ai_brain_tests")
os.environ.setdefault("MLFLOW_ENABLE_ASYNC_LOGGING", "false")

import pytest


@pytest.fixture(scope="session")
def event_loop_policy() -> asyncio.AbstractEventLoopPolicy:
    """psycopg async cannot use Windows ProactorEventLoop."""
    if sys.platform == "win32":
        return asyncio.WindowsSelectorEventLoopPolicy()
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture(autouse=True)
def _reset_memory_settings_cache():
    from ai_brain.core.config.memory import _load_yaml, get_memory_settings

    get_memory_settings.cache_clear()
    _load_yaml.cache_clear()
    yield
    get_memory_settings.cache_clear()
    _load_yaml.cache_clear()
