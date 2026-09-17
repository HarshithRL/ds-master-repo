#!/usr/bin/env python
"""beforeShellExecution: block production deploys and pushes to main."""
from __future__ import annotations

import json
import re
import sys

ALLOW = {"permission": "allow"}


def decide(command: str) -> dict:
    text = command.strip()
    if not text:
        return ALLOW

    if re.search(r"\bgit\s+push\b", text, re.I) and re.search(
        r"(?:^|[\s:])(main|master)(?:\s|$)", text, re.I
    ):
        return {
            "permission": "deny",
            "user_message": "Push to main/master is blocked by the procurement-agent hook.",
            "agent_message": (
                "Do not push to main or master. Use feature/procurement_agent "
                "(or another feature branch) and open a PR."
            ),
        }

    if re.search(r"\bgit\s+push\b", text, re.I) and re.search(
        r"(?:^|\s)(--force|--force-with-lease|-f)(?:\s|$)", text, re.I
    ):
        return {
            "permission": "ask",
            "user_message": "Force-push requires your review.",
            "agent_message": "This is a git force-push. Wait for the user to approve it.",
        }

    if re.search(r"\bdatabricks\s+bundle\s+deploy\b", text, re.I):
        if re.search(r"--target(?:\s+|=)(P|PRD|prd|production)\b", text):
            return {
                "permission": "deny",
                "user_message": "Production Databricks deploy is blocked.",
                "agent_message": (
                    "databricks bundle deploy to target P/PRD is blocked. "
                    "Use target D or T unless the user explicitly requests production."
                ),
            }
        if re.search(r"--target(?:\s+|=)(A|ACC|acc|acceptance)\b", text):
            return {
                "permission": "ask",
                "user_message": "Acceptance Databricks deploy requires review.",
                "agent_message": "This deploys to ACC. Wait for the user to approve it.",
            }
        if not re.search(r"--target(?:\s+|=)", text):
            return {
                "permission": "ask",
                "user_message": "Databricks bundle deploy with no target requires review.",
                "agent_message": "Specify --target D or T for local/test deploys.",
            }

    if re.search(r"\bDROP\s+(TABLE|SCHEMA|DATABASE|CATALOG)\b", text, re.I):
        return {
            "permission": "deny",
            "user_message": "DROP statements are blocked by the procurement-agent hook.",
            "agent_message": "Do not DROP Unity Catalog objects unless the user explicitly requests it.",
        }

    return ALLOW


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.stdout.write(json.dumps(ALLOW) + "\n")
        return

    command = str(payload.get("command") or "")
    sys.stdout.write(json.dumps(decide(command)) + "\n")


if __name__ == "__main__":
    main()
