#!/usr/bin/env python
"""sessionStart: inject Mate / procurement-agent working context."""
from __future__ import annotations

import json
import sys

CONTEXT = """\
Procurement agent (Mate) — DS-Master-Repo / feature/procurement_agent

Scope
- Keep code changes inside ds-procure-ai/ unless the user explicitly asks to touch another project.
- Do not edit shared pipelines/ or other top-level DS bundles by default.

Local stack
- Frontend Vite :5173, Flask API :5000, AI Brain :8004
- Start from ds-procure-ai/: .\\start-dev.ps1
- Databricks CLI profile: adb-7181820732839861 (DEV/TEST only)

Safety
- Never commit .env, tokens, mate.sqlite, or credential files.
- Do not deploy Databricks bundle target P / PRD without an explicit user request.
"""


def main() -> None:
    try:
        json.load(sys.stdin)
    except Exception:
        pass
    sys.stdout.write(json.dumps({"additional_context": CONTEXT.strip()}) + "\n")


if __name__ == "__main__":
    main()
