from __future__ import annotations

import time
import uuid

from flask import Blueprint, jsonify, request
from pydantic import BaseModel, Field, field_validator

from shared.logger_global import bind_context, get_logger, log_client_event, reset_context

logs_bp = Blueprint("logs", __name__)
log = get_logger(__name__)

_MAX_BODY_BYTES = 8 * 1024
_MAX_EVENTS = 20
_RATE_LIMIT_WINDOW_SEC = 60
_RATE_LIMIT_MAX = 120

_rate_buckets: dict[str, list[float]] = {}


class ClientLogEvent(BaseModel):
    level: str = "info"
    message: str
    module: str = "frontend"
    request_id: str | None = None
    project_id: str | None = None
    workflow: str | None = None
    stack: str | None = None
    context: dict | None = None

    @field_validator("level")
    @classmethod
    def normalize_level(cls, value: str) -> str:
        return value.lower().strip()


class ClientLogBatch(BaseModel):
    events: list[ClientLogEvent] = Field(default_factory=list)

    @field_validator("events")
    @classmethod
    def cap_events(cls, value: list[ClientLogEvent]) -> list[ClientLogEvent]:
        if len(value) > _MAX_EVENTS:
            raise ValueError(f"At most {_MAX_EVENTS} events per batch")
        return value


def _rate_limited(client_ip: str) -> bool:
    now = time.time()
    bucket = _rate_buckets.setdefault(client_ip, [])
    cutoff = now - _RATE_LIMIT_WINDOW_SEC
    _rate_buckets[client_ip] = [ts for ts in bucket if ts >= cutoff]
    if len(_rate_buckets[client_ip]) >= _RATE_LIMIT_MAX:
        return True
    _rate_buckets[client_ip].append(now)
    return False


@logs_bp.route("/api/logs", methods=["POST"])
def ingest_client_logs():
    if request.content_length and request.content_length > _MAX_BODY_BYTES:
        return "", 204

    client_ip = request.remote_addr or "unknown"
    if _rate_limited(client_ip):
        return "", 204

    raw = request.get_json(silent=True)
    if raw is None:
        return "", 204

    try:
        if isinstance(raw, dict) and "events" in raw:
            batch = ClientLogBatch.model_validate(raw)
            events = batch.events
        elif isinstance(raw, dict):
            events = [ClientLogEvent.model_validate(raw)]
        else:
            return "", 204
    except Exception as exc:  # noqa: BLE001
        log.warning("client log ingest rejected: {}", exc)
        return "", 204

    bind_context(workflow="client.log_ingest", request_id=request.headers.get("X-Request-Id"))
    try:
        for event in events:
            log_client_event(
                level=event.level,
                message=event.message[:2000],
                module=event.module[:200],
                request_id=event.request_id,
                project_id=event.project_id,
                workflow=event.workflow,
                stack=event.stack[:4000] if event.stack else None,
                context=event.context,
            )
    finally:
        reset_context()

    return "", 204
