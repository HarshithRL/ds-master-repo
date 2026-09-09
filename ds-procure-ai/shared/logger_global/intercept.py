"""Route stdlib logging through loguru."""

from __future__ import annotations

import logging

from loguru import logger

_INTERCEPTED = (
    "uvicorn",
    "uvicorn.error",
    "uvicorn.access",
    "werkzeug",
    "langchain",
    "langchain_core",
    "httpx",
    "httpcore",
)


class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame is not None and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def setup_stdlib_intercept(*, level: int = logging.WARNING) -> None:
    logging.root.handlers = [InterceptHandler()]
    logging.root.setLevel(level)

    for name in _INTERCEPTED:
        lib_logger = logging.getLogger(name)
        lib_logger.handlers = [InterceptHandler()]
        lib_logger.propagate = False
        lib_logger.setLevel(level)
