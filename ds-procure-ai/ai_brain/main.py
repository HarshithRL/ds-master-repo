"""Smoke client for the AI Brain AgentServer (health, Mate /invoke, /invocations stream)."""

from __future__ import annotations

import argparse
import json
import os

import requests

DEFAULT_BASE_URL = os.getenv("BRAIN_BASE_URL", "http://127.0.0.1:8004")
TIMEOUT = float(os.getenv("BRAIN_SMOKE_TIMEOUT", "120"))


def check_health(base_url: str) -> None:
    for path in ("/health", "/ready"):
        response = requests.get(f"{base_url}{path}", timeout=10)
        print(f"GET {path} -> {response.status_code} {response.text.strip()}")


def call_invoke(base_url: str, request_text: str, flags: dict[str, bool]) -> dict:
    response = requests.post(
        f"{base_url}/invoke",
        json={
            "request": request_text,
            "procurement": flags,
            "thread_id": os.getenv("BRAIN_THREAD_ID", ""),
        },
        timeout=TIMEOUT,
    )
    print(f"POST /invoke -> {response.status_code}")
    response.raise_for_status()
    body = response.json()
    print(json.dumps(body, indent=2)[:2000])
    return body


def call_invocations_stream(base_url: str, request_text: str, flags: dict[str, bool]) -> None:
    """AgentServer Responses endpoint: SSE of response.output_text.delta / output_item.done."""
    payload = {
        "input": [{"role": "user", "content": request_text, "type": "message"}],
        "custom_inputs": {
            "request": request_text,
            "procurement": flags,
            "thread_id": os.getenv("BRAIN_THREAD_ID", ""),
        },
        "stream": True,
    }
    with requests.post(
        f"{base_url}/invocations",
        json=payload,
        stream=True,
        timeout=TIMEOUT,
        headers={"Accept": "text/event-stream"},
    ) as response:
        print(f"POST /invocations (stream) -> {response.status_code}")
        response.raise_for_status()
        for line in response.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            data = line[len("data: ") :]
            if data == "[DONE]":
                print("[DONE]")
                break
            event = json.loads(data)
            kind = event.get("type")
            if kind == "response.output_text.delta":
                print(event.get("delta", ""), end="", flush=True)
            elif kind == "response.output_item.done":
                item = event.get("item") or {}
                text = ""
                for chunk in item.get("content") or []:
                    text += chunk.get("text", "")
                print(f"\n[item.done] {text[:400]}")
                if event.get("custom_outputs", {}).get("interrupted"):
                    print(f"[interrupted] {event['custom_outputs'].get('interrupts')}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument(
        "--request",
        default="Hey How can you help me with procurement?",
    )
    parser.add_argument("--mainagent", action="store_true")
    parser.add_argument("--deepagent", action="store_true")
    parser.add_argument(
        "--mode",
        choices=("invoke", "stream", "all"),
        default="all",
    )
    args = parser.parse_args()

    flags = {"mainagent": args.mainagent, "deepagent": args.deepagent}
    if not any(flags.values()):
        flags["deepagent"] = True

    check_health(args.base_url)
    if args.mode in ("invoke", "all"):
        call_invoke(args.base_url, args.request, flags)
    if args.mode in ("stream", "all"):
        call_invocations_stream(args.base_url, args.request, flags)


if __name__ == "__main__":
    main()
