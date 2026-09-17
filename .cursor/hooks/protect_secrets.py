#!/usr/bin/env python
"""beforeReadFile / beforeTabFileRead: keep secrets out of the model."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ALLOW = {"permission": "allow"}
ALLOWED_ENV_EXAMPLES = {
    ".env.example",
    ".env.studio.example",
}
SECRET_NAMES = {
    ".env",
    ".databrickscfg",
    "credentials.json",
    "serviceprincipal.json",
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
}
SECRET_SUFFIXES = {".pem", ".p12", ".pfx", ".key"}


def is_secret(file_path: str) -> bool:
    if not file_path:
        return False
    name = Path(file_path).name.lower()
    if name in ALLOWED_ENV_EXAMPLES:
        return False
    if name in SECRET_NAMES:
        return True
    if name.startswith(".env."):
        return True
    return Path(name).suffix.lower() in SECRET_SUFFIXES


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.stdout.write(json.dumps(ALLOW) + "\n")
        return

    file_path = str(payload.get("file_path") or payload.get("path") or "")
    if is_secret(file_path):
        sys.stdout.write(
            json.dumps(
                {
                    "permission": "deny",
                    "user_message": (
                        f"Blocked reading secret file: {Path(file_path).name}"
                    ),
                }
            )
            + "\n"
        )
        return

    sys.stdout.write(json.dumps(ALLOW) + "\n")


if __name__ == "__main__":
    main()
