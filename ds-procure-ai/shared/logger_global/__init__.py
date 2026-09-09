"""Mate global logging — import from here, never configure loguru directly."""

from __future__ import annotations

from shared.logger_global.controller import (
    bind_context,
    get_logger,
    log_client_event,
    logger,
    reset_context,
    setup_logging,
)

__all__ = [
    "bind_context",
    "get_logger",
    "log_client_event",
    "logger",
    "reset_context",
    "setup_logging",
]
