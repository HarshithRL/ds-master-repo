"""Databricks Apps entrypoint: AI Brain on loopback + Flask/gunicorn on DATABRICKS_APP_PORT."""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from shared.databricks_runtime import prepare_app_environ

REPO_ROOT = Path(__file__).resolve().parent
BACKEND = REPO_ROOT / "backend"


def _python() -> str:
    venv_python = REPO_ROOT / ".venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    # Do not Path.resolve() — Apps venv python is a symlink to system python.
    return os.path.abspath(sys.executable)


def _prepare_env() -> dict[str, str]:
    env = os.environ.copy()
    prepare_app_environ(env)
    pythonpath = os.pathsep.join(
        part
        for part in (str(REPO_ROOT), str(BACKEND), env.get("PYTHONPATH", ""))
        if part
    )
    env["PYTHONPATH"] = pythonpath
    env.setdefault("BRAIN_BASE_URL", "http://127.0.0.1:8004")
    env.setdefault("BRAIN_HOST", "127.0.0.1")
    env.setdefault("BRAIN_PORT", "8004")
    env.setdefault("MATE_ENV", "prod")
    return env


def _app_port() -> int:
    return int(os.environ.get("DATABRICKS_APP_PORT", "8000"))


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


def _wait_for_brain(proc: subprocess.Popen, host: str, port: int, timeout_s: float = 90.0) -> None:
    """Fail the app if the brain never binds. Do not leave Flask serving a dead :8004."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        code = proc.poll()
        if code is not None:
            raise SystemExit(code or 1)
        if _port_open(host, port):
            return
        time.sleep(0.5)
    if proc.poll() is None:
        proc.send_signal(signal.SIGTERM)
    raise SystemExit(1)


def _wait_or_exit(proc: subprocess.Popen, timeout_s: float = 12.0) -> None:
    try:
        proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def main() -> int:
    env = _prepare_env()
    python = _python()
    os.chdir(REPO_ROOT)
    brain_host = env.get("BRAIN_HOST", "127.0.0.1")
    brain_port = env.get("BRAIN_PORT", "8004")
    app_port = _app_port()

    brain = subprocess.Popen(
        [
            python,
            "-m",
            "uvicorn",
            "ai_brain.brain_server:app",
            "--host",
            brain_host,
            "--port",
            str(brain_port),
            "--log-level",
            "info",
        ],
        cwd=str(REPO_ROOT),
        env=env,
    )
    _wait_for_brain(brain, brain_host, int(brain_port))
    gunicorn = subprocess.Popen(
        [
            python,
            "-m",
            "gunicorn",
            "app:app",
            "-k",
            "gthread",
            "-w",
            "1",
            "--threads",
            "8",
            "-b",
            f"0.0.0.0:{app_port}",
            "--timeout",
            "120",
            "--access-logfile",
            "-",
            "--error-logfile",
            "-",
            "--pythonpath",
            f"{REPO_ROOT},{BACKEND}",
            "--chdir",
            str(BACKEND),
        ],
        cwd=str(BACKEND),
        env=env,
    )

    shutting_down = False

    def _shutdown(signum: int, _frame) -> None:
        nonlocal shutting_down
        if shutting_down:
            return
        shutting_down = True
        for proc in (gunicorn, brain):
            if proc.poll() is None:
                proc.send_signal(signum)
        for proc in (gunicorn, brain):
            if proc.poll() is None:
                _wait_or_exit(proc)
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    while True:
        gunicorn_code = gunicorn.poll()
        brain_code = brain.poll()
        if gunicorn_code is not None:
            if brain.poll() is None:
                brain.send_signal(signal.SIGTERM)
                _wait_or_exit(brain)
            return gunicorn_code
        if brain_code is not None:
            if gunicorn.poll() is None:
                gunicorn.send_signal(signal.SIGTERM)
                _wait_or_exit(gunicorn)
            return brain_code or 1
        time.sleep(0.4)


if __name__ == "__main__":
    raise SystemExit(main())
