"""Databricks Job entrypoint for kb_build.

Runs one project's knowledge-base build in its own compute, outside the app
process, so a restart or an interactive-chat spike cannot kill it. Invoked by
resources/ds_procure_ai_kb_build.job.yml with --project-id / --kb-job-id.
"""

from __future__ import annotations

import argparse
import os
import sys
import traceback
from pathlib import Path

def _repo_root() -> Path:
    """Locate the repo root. Databricks serverless exec()s this file, so
    `__file__` is undefined there and the path must be recovered another way."""
    candidates: list[Path] = []
    try:
        candidates.append(Path(__file__).resolve().parents[1])
    except NameError:
        pass
    if sys.argv and sys.argv[0]:
        argv0 = Path(sys.argv[0]).resolve()
        candidates.extend(p for p in (argv0.parent.parent, argv0.parent) if p)
    cwd = Path.cwd().resolve()
    candidates.append(cwd)
    candidates.extend(cwd.parents)
    for candidate in candidates:
        if (candidate / "shared" / "logger_global").is_dir():
            return candidate
    return cwd


sys.path.insert(0, str(_repo_root()))

from shared.logger_global import get_logger, setup_logging  # noqa: E402

setup_logging(service="kb_build_job")
log = get_logger(__name__, service="kb_build_job")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run kb_build for one project")
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--kb-job-id", default="")
    parser.add_argument("--extract-model-kind", default="")
    parser.add_argument("--write-xlsx", action="store_true")
    args = parser.parse_args()

    project_id = args.project_id.strip()
    kb_job_id = args.kb_job_id.strip()
    if not project_id:
        log.error("kb_build job called without --project-id")
        return 2

    # Serverless does not inherit the app's env; mirror the tier the app chose.
    model_kind = args.extract_model_kind.strip().lower()
    if model_kind in ("fast", "thinking"):
        os.environ["MATE_EXTRACT_MODEL_KIND"] = model_kind
        log.info("kb_build job extract model kind={}", model_kind)

    from ai_brain.core.kb.extract import dispatch, job_store
    from ai_brain.core.kb.extract.runner import run_kb_build

    if not kb_job_id:
        kb_job_id = job_store.create_job(project_id, mode=dispatch.MODE_JOB)
    job_store.mark_running(kb_job_id, project_id)
    stop_heartbeat = dispatch.start_heartbeat(kb_job_id)

    log.info("kb_build job start project_id={} kb_job_id={}", project_id, kb_job_id)
    try:
        run_kb_build(project_id, write_xlsx=args.write_xlsx)
    except Exception as exc:
        detail = "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        )[-4000:]
        log.exception("kb_build job failed project_id={}", project_id)
        job_store.finish(
            kb_job_id,
            project_id,
            status="failed",
            message=f"Knowledge base build failed: {type(exc).__name__}: {exc}"[:500],
            error=detail,
        )
        return 1
    finally:
        stop_heartbeat.set()

    # run_kb_build already wrote the real terminal status (ready/needs_review/
    # staged) via pack_store; reflect whatever it decided into the job row.
    from ai_brain.core.procurement_ai.packs import store as pack_store

    kb = pack_store.read_status(project_id).get("kb") or {}
    job_store.finish(
        kb_job_id,
        project_id,
        status=str(kb.get("status") or "ready"),
        message=kb.get("message"),
        error=kb.get("error"),
    )
    log.info("kb_build job done project_id={} status={}", project_id, kb.get("status"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
