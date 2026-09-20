"""kb_build execution modes.

`thread` (default) keeps the original in-process daemon thread. `job` submits a
Databricks Job run so the build survives app restarts and does not compete with
interactive chat for the single ai_brain process. Both record their state in
`kb_build_job`, so a stuck build is detectable either way.

Select with MATE_KB_BUILD_MODE=thread|job.
"""

from __future__ import annotations

import contextvars
import os
import threading
import time
from typing import Any

from ai_brain.core.kb.extract import job_store
from shared.logger_global import get_logger

log = get_logger(__name__, service="ai_brain")

MODE_THREAD = "thread"
MODE_JOB = "job"

HEARTBEAT_INTERVAL_S = 30.0


def build_mode() -> str:
    mode = (os.getenv("MATE_KB_BUILD_MODE", MODE_THREAD) or MODE_THREAD).strip().lower()
    return mode if mode in {MODE_THREAD, MODE_JOB} else MODE_THREAD


def _job_id_env() -> str:
    return (os.getenv("MATE_KB_BUILD_JOB_ID", "") or "").strip()


def start_heartbeat(job_id: str) -> threading.Event:
    """Tick `heartbeat_at` until stopped, so a dead run is distinguishable."""
    stop = threading.Event()

    def _beat() -> None:
        while not stop.wait(HEARTBEAT_INTERVAL_S):
            job_store.heartbeat(job_id)

    # Threads start with an empty context, so without this copy the beat loses
    # the visitor's OBO token and every UC write is denied.
    ctx = contextvars.copy_context()
    threading.Thread(
        target=ctx.run, args=(_beat,), daemon=True, name=f"kb-heartbeat-{job_id[:8]}"
    ).start()
    return stop


def submit_databricks_job(project_id: str, job_id: str) -> str:
    """Trigger the kb_build Job. Returns the Databricks run id."""
    databricks_job_id = _job_id_env()
    if not databricks_job_id:
        raise RuntimeError(
            "MATE_KB_BUILD_MODE=job requires MATE_KB_BUILD_JOB_ID "
            "(the Databricks job id created by resources/ds_procure_ai_kb_build.job.yml)"
        )
    from shared.databricks_runtime import workspace_client

    # Serverless tasks do not inherit the app's env, so the model tier travels
    # as a parameter — otherwise the job would silently use a different model.
    from ai_brain.core.config.llm import get_extract_model_kind

    run = workspace_client().jobs.run_now(
        job_id=int(databricks_job_id),
        job_parameters={
            "project_id": project_id,
            "kb_job_id": job_id,
            "extract_model_kind": get_extract_model_kind(),
        },
    )
    run_id = str(getattr(run, "run_id", "") or "")
    log.info(
        "kb_build job submitted project_id={} kb_job_id={} run_id={}",
        project_id,
        job_id,
        run_id,
    )
    return run_id


def wait_for_run(run_id: str, *, timeout_s: float, poll_s: float = 15.0) -> dict[str, Any]:
    """Poll a Databricks run to completion. Used by callers that need the result."""
    from shared.databricks_runtime import workspace_client

    client = workspace_client()
    deadline = time.monotonic() + timeout_s
    while True:
        run = client.jobs.get_run(run_id=int(run_id))
        state = getattr(run, "state", None)
        life_cycle = str(getattr(getattr(state, "life_cycle_state", None), "value", "") or "")
        result = str(getattr(getattr(state, "result_state", None), "value", "") or "")
        if life_cycle in {"TERMINATED", "SKIPPED", "INTERNAL_ERROR"}:
            return {
                "life_cycle_state": life_cycle,
                "result_state": result,
                "message": str(getattr(state, "state_message", "") or ""),
            }
        if time.monotonic() >= deadline:
            return {
                "life_cycle_state": life_cycle or "UNKNOWN",
                "result_state": "TIMEOUT",
                "message": f"run {run_id} still {life_cycle} after {timeout_s:.0f}s",
            }
        time.sleep(poll_s)
