"""Workbench settings."""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _flag(name: str, default: str) -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "y"}


# True: show the sample requests in data/demo_requests.json plus requests
# submitted from the AXIOM portal running in demo mode; ticket and status
# changes are saved in DEMO_STATE_FILE. False: read and write the Databricks
# request tables (services/request_store.py). Set WORKBENCH_DEMO_MODE=false
# in app.yaml to use Databricks.
DEMO_MODE = _flag("WORKBENCH_DEMO_MODE", "false")

DEMO_REQUESTS_FILE = BASE_DIR / "data" / "demo_requests.json"
DEMO_STATE_FILE = BASE_DIR / "demo_workbench_state.json"

# The portal's local request log (sibling project folder by default)
PORTAL_DEMO_REQUESTS_FILE = Path(
    os.environ.get(
        "PORTAL_DEMO_REQUESTS_FILE",
        str(BASE_DIR.parent / "axiom-demo" / "demo_requests.jsonl"),
    )
)
