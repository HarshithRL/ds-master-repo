"""Durable kb_build job records.

Source of truth is the `kb_build_job` table. The legacy `packs/status.json`
volume file is still mirrored on every transition so existing readers
(insights, Studio polling) keep working unchanged while both paths coexist.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shared.db.connection import session_or, session_scope
from shared.db.models import KbBuildJob, utc_now_iso
from shared.logger_global import get_logger

log = get_logger(__name__, service="ai_brain")

# A run whose heartbeat is older than this is treated as dead, not slow.
STALE_HEARTBEAT_S = 900.0

TERMINAL_STATUSES = frozenset({"ready", "needs_review", "staged", "failed"})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def age_seconds(value: str | None) -> float | None:
    moment = _parse_iso(value)
    if moment is None:
        return None
    return (_now() - moment).total_seconds()


def _mirror_status_file(
    project_id: str, *, status: str, message: str | None, error: str | None
) -> None:
    """Keep packs/status.json in sync so legacy readers see the same state."""
    try:
        from ai_brain.core.procurement_ai.packs.store import write_kb_job

        write_kb_job(project_id, status=status, message=message, error=error)
    except Exception:
        log.exception("kb job status mirror failed project_id={}", project_id)


def create_job(project_id: str, *, mode: str, run_id: str | None = None) -> str:
    """Record a queued build and return its job id."""
    job_id = uuid.uuid4().hex
    now = utc_now_iso()
    try:
        with session_scope() as session:
            session.add(
                KbBuildJob(
                    id=job_id,
                    project_id=project_id,
                    status="queued",
                    mode=mode,
                    run_id=run_id,
                    message="Queued for knowledge base build…",
                    attempt=1,
                    created_at=now,
                    updated_at=now,
                )
            )
    except Exception:
        # Never block a build because bookkeeping failed.
        log.exception("kb job create failed project_id={}", project_id)
    _mirror_status_file(
        project_id,
        status="building",
        message="Queued for knowledge base build…",
        error=None,
    )
    return job_id


def _update(job_id: str, **fields: Any) -> None:
    try:
        with session_scope() as session:
            row = session.get(KbBuildJob, job_id)
            if row is None:
                return
            for key, value in fields.items():
                setattr(row, key, value)
            row.updated_at = utc_now_iso()
    except Exception:
        log.exception("kb job update failed job_id={}", job_id)


def mark_running(job_id: str, project_id: str, *, run_id: str | None = None) -> None:
    now = utc_now_iso()
    fields: dict[str, Any] = {
        "status": "running",
        "message": "Extracting vendor evidence from uploaded files…",
        "started_at": now,
        "heartbeat_at": now,
    }
    if run_id:
        fields["run_id"] = run_id
    _update(job_id, **fields)
    _mirror_status_file(
        project_id,
        status="building",
        message="Extracting vendor evidence from uploaded files…",
        error=None,
    )


def heartbeat(job_id: str) -> None:
    """Prove the run is alive; absence of this is how we detect a dead build."""
    _update(job_id, heartbeat_at=utc_now_iso())


def finish(
    job_id: str,
    project_id: str,
    *,
    status: str,
    message: str | None = None,
    error: str | None = None,
) -> None:
    _update(
        job_id,
        status=status,
        message=message,
        error=error,
        finished_at=utc_now_iso(),
        heartbeat_at=utc_now_iso(),
    )
    _mirror_status_file(project_id, status=status, message=message, error=error)


def latest_job(project_id: str) -> dict[str, Any] | None:
    try:
        with session_scope() as session:
            row = session.scalars(
                select(KbBuildJob)
                .where(KbBuildJob.project_id == project_id)
                .order_by(KbBuildJob.created_at.desc())
                .limit(1)
            ).first()
            if row is None:
                return None
            return {
                "id": row.id,
                "project_id": row.project_id,
                "status": row.status,
                "mode": row.mode,
                "run_id": row.run_id,
                "message": row.message,
                "error": row.error,
                "attempt": row.attempt,
                "heartbeat_at": row.heartbeat_at,
                "started_at": row.started_at,
                "finished_at": row.finished_at,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
    except Exception:
        log.exception("kb job read failed project_id={}", project_id)
        return None


def latest_status_map(
    project_ids: list[str], *, session: Session | None = None
) -> dict[str, str]:
    """Newest run state per project, in one query for the whole list.

    A non-terminal run with a dead heartbeat reports "failed", not "building",
    so a list row cannot spin forever on a run that died.
    """
    ids = [pid for pid in project_ids if pid]
    if not ids:
        return {}
    ranked = (
        select(
            KbBuildJob.project_id,
            KbBuildJob.status,
            KbBuildJob.heartbeat_at,
            KbBuildJob.created_at,
            func.row_number()
            .over(
                partition_by=KbBuildJob.project_id,
                order_by=KbBuildJob.created_at.desc(),
            )
            .label("rn"),
        )
        .where(KbBuildJob.project_id.in_(ids))
        .subquery()
    )
    try:
        with session_or(session) as active:
            rows = active.execute(
                select(
                    ranked.c.project_id,
                    ranked.c.status,
                    ranked.c.heartbeat_at,
                    ranked.c.created_at,
                ).where(ranked.c.rn == 1)
            ).all()
    except Exception:
        log.exception("kb job bulk read failed")
        return {}

    limit = stale_seconds()
    out: dict[str, str] = {}
    for project_id, status, heartbeat_at, created_at in rows:
        if status in TERMINAL_STATUSES:
            out[project_id] = status
            continue
        age = age_seconds(heartbeat_at or created_at)
        out[project_id] = "failed" if age is not None and age > limit else "building"
    return out


def stale_seconds() -> float:
    raw = (os.getenv("MATE_KB_BUILD_STALE_S", "") or "").strip()
    try:
        return float(raw) if raw else STALE_HEARTBEAT_S
    except ValueError:
        return STALE_HEARTBEAT_S


def is_stalled(job: dict[str, Any] | None) -> bool:
    """A non-terminal run with no recent heartbeat is dead, not slow."""
    if not job or job.get("status") in TERMINAL_STATUSES:
        return False
    age = age_seconds(job.get("heartbeat_at") or job.get("created_at"))
    return age is not None and age > stale_seconds()


def reap_stalled(project_id: str) -> dict[str, Any] | None:
    """Flip a dead run to failed so the UI stops showing it as in-progress."""
    job = latest_job(project_id)
    if not is_stalled(job):
        return None
    assert job is not None
    age = age_seconds(job.get("heartbeat_at") or job.get("created_at")) or 0.0
    detail = (
        f"kb_build run {job['id']} stopped reporting {age:.0f}s ago "
        f"(mode={job.get('mode')}, run_id={job.get('run_id')}). "
        "The process was very likely restarted mid-build."
    )
    log.error("kb_build stalled project_id={} job_id={}", project_id, job["id"])
    finish(
        job["id"],
        project_id,
        status="failed",
        message="Knowledge base build stopped unexpectedly.",
        error=detail,
    )
    return latest_job(project_id)
