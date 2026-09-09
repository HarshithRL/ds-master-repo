"""Project chat sessions. Conversation thread is the session id. Files stay on the project."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from shared.db.connection import session_scope
from shared.db.models import ChatMessage, ChatSession, utc_now_iso

DEFAULT_TITLE = "New chat"
TITLE_LIMIT = 48


def _clip_title(text: str) -> str:
    collapsed = " ".join((text or "").split())
    if not collapsed:
        return DEFAULT_TITLE
    if len(collapsed) <= TITLE_LIMIT:
        return collapsed
    return collapsed[: TITLE_LIMIT - 1].rstrip() + "…"


def _session_payload(row: ChatSession, *, message_count: int | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": row.id,
        "project_id": row.project_id,
        "title": row.title or DEFAULT_TITLE,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }
    if message_count is not None:
        payload["message_count"] = message_count
    return payload


def _message_payload(row: ChatMessage) -> dict[str, str]:
    return {"role": row.role, "text": row.text or ""}


def list_sessions(project_id: str) -> list[dict[str, Any]]:
    pid = (project_id or "").strip()
    if not pid:
        return []
    with session_scope() as session:
        rows = session.scalars(
            select(ChatSession)
            .where(ChatSession.project_id == pid)
            .order_by(ChatSession.updated_at.desc(), ChatSession.created_at.desc())
        ).all()
        return [_session_payload(row) for row in rows]


def create_session(project_id: str, title: str = DEFAULT_TITLE) -> dict[str, Any]:
    pid = (project_id or "").strip()
    now = utc_now_iso()
    row = ChatSession(
        id=str(uuid.uuid4()),
        project_id=pid,
        title=_clip_title(title) if title and title != DEFAULT_TITLE else DEFAULT_TITLE,
        created_at=now,
        updated_at=now,
    )
    with session_scope() as session:
        session.add(row)
        session.flush()
        return _session_payload(row, message_count=0)


def get_session(project_id: str, session_id: str) -> dict[str, Any] | None:
    pid = (project_id or "").strip()
    sid = (session_id or "").strip()
    if not pid or not sid:
        return None
    with session_scope() as session:
        row = session.get(ChatSession, sid)
        if row is None or row.project_id != pid:
            return None
        messages = session.scalars(
            select(ChatMessage)
            .where(ChatMessage.session_id == sid)
            .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
        ).all()
        payload = _session_payload(row, message_count=len(messages))
        payload["messages"] = [_message_payload(item) for item in messages]
        return payload


def ensure_session(project_id: str, session_id: str | None) -> dict[str, Any] | None:
    pid = (project_id or "").strip()
    sid = (session_id or "").strip()
    if not pid:
        return None
    if not sid:
        return create_session(pid)
    found = get_session(pid, sid)
    if found is None:
        return None
    return {key: found[key] for key in ("id", "project_id", "title", "created_at", "updated_at")}


def append_message(project_id: str, session_id: str, role: str, text: str) -> None:
    pid = (project_id or "").strip()
    sid = (session_id or "").strip()
    body = (text or "").strip()
    kind = (role or "").strip() or "ai"
    if not pid or not sid or not body:
        return
    now = utc_now_iso()
    with session_scope() as session:
        row = session.get(ChatSession, sid)
        if row is None or row.project_id != pid:
            return
        session.add(
            ChatMessage(
                id=str(uuid.uuid4()),
                session_id=sid,
                role=kind,
                text=body,
                created_at=now,
            )
        )
        if kind == "user" and (not row.title or row.title == DEFAULT_TITLE):
            row.title = _clip_title(body)
        row.updated_at = now
