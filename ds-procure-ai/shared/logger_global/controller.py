"""Single owner of loguru configuration for the Mate platform."""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

from loguru import logger

from shared.logger_global.context import bind_context, get_context_dict, reset_context
from shared.logger_global.formatters import PRETTY_FORMAT
from shared.logger_global.intercept import setup_stdlib_intercept

_configured = False
_service = "unknown"

_REDACT_KEY = re.compile(
    r"(password|token|secret|authorization|credential)",
    re.IGNORECASE,
)


def _env(name: str, default: str) -> str:
    return os.getenv(name, default).strip() or default


def _redact_value(key: str, value: Any) -> Any:
    if isinstance(key, str) and _REDACT_KEY.search(key):
        return "***REDACTED***"
    if isinstance(value, str) and _REDACT_KEY.search(value):
        return "***REDACTED***"
    if isinstance(value, dict):
        return {k: _redact_value(str(k), v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_value(key, item) for item in value]
    return value


def _patch_record(record: dict[str, Any]) -> None:
    extra = record["extra"]
    extra.setdefault("service", _service)
    extra.setdefault("module", extra.get("module") or "-")
    extra.setdefault("request_id", "-")
    extra.setdefault("workflow", "-")
    extra.setdefault("project_id", "-")

    for key, value in get_context_dict().items():
        extra[key] = value

    for key in list(extra.keys()):
        extra[key] = _redact_value(key, extra[key])

    message = record["message"]
    if isinstance(message, str):
        record["message"] = _redact_value("message", message)


def setup_logging(*, service: str) -> None:
    global _configured, _service
    if _configured:
        return

    _service = service
    log_level = _env("MATE_LOG_LEVEL", "DEBUG").upper()
    log_format = _env("MATE_LOG_FORMAT", "pretty").lower()
    log_dir = Path(_env("MATE_LOG_DIR", "logs"))
    mate_env = _env("MATE_ENV", "dev").lower()
    diagnose = mate_env != "prod"

    log_dir.mkdir(parents=True, exist_ok=True)
    retention = "30 days" if mate_env == "prod" else "7 days"

    logger.remove()
    logger.configure(patcher=_patch_record)

    if log_format == "json":
        logger.add(
            sys.stderr,
            level=log_level,
            serialize=True,
            diagnose=diagnose,
            enqueue=True,
        )
    else:
        logger.add(
            sys.stderr,
            level=log_level,
            format=PRETTY_FORMAT,
            colorize=True,
            diagnose=diagnose,
            enqueue=True,
        )

    logger.add(
        log_dir / f"{service}.log",
        level=log_level,
        rotation="10 MB",
        retention=retention,
        serialize=True,
        diagnose=diagnose,
        enqueue=True,
    )
    logger.add(
        log_dir / f"{service}.error.log",
        level="ERROR",
        rotation="10 MB",
        retention=retention,
        serialize=True,
        diagnose=diagnose,
        enqueue=True,
    )

    stdlib_level_name = _env("MATE_STDLIB_LOG_LEVEL", "WARNING").upper()
    stdlib_level = getattr(logging, stdlib_level_name, logging.WARNING)
    setup_stdlib_intercept(level=stdlib_level)

    _configured = True
    logger.bind(module="logger_global.controller").info(
        "logging initialized service={} level={} format={} env={}",
        service,
        log_level,
        log_format,
        mate_env,
    )


def get_logger(module: str, *, service: str | None = None):
    svc = service or _service
    return logger.bind(module=module, service=svc)


def log_client_event(
    *,
    level: str,
    message: str,
    module: str,
    request_id: str | None = None,
    project_id: str | None = None,
    workflow: str | None = None,
    stack: str | None = None,
    context: dict[str, Any] | None = None,
) -> None:
    bound = logger.bind(module=module, service="frontend")
    if request_id:
        bound = bound.bind(request_id=request_id)
    if project_id:
        bound = bound.bind(project_id=project_id)
    if workflow:
        bound = bound.bind(workflow=workflow)

    payload: dict[str, Any] = {}
    if stack:
        payload["stack"] = stack
    if context:
        payload["context"] = _redact_value("context", context)

    level_name = level.upper()
    if level_name == "ERROR":
        bound.error("{msg} | extra={extra}", msg=message, extra=json.dumps(payload))
    elif level_name == "WARN" or level_name == "WARNING":
        bound.warning("{msg} | extra={extra}", msg=message, extra=json.dumps(payload))
    else:
        bound.info("{msg} | extra={extra}", msg=message, extra=json.dumps(payload))


__all__ = [
    "bind_context",
    "get_logger",
    "log_client_event",
    "logger",
    "reset_context",
    "setup_logging",
]
