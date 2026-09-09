"""Log line format strings for pretty and JSON sinks."""

from __future__ import annotations

PRETTY_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{extra[service]}</cyan> | "
    "<cyan>{extra[module]}</cyan> | "
    "rid=<yellow>{extra[request_id]}</yellow> | "
    "wf=<yellow>{extra[workflow]}</yellow> | "
    "{message}"
)
