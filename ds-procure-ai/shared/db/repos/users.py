"""User upsert and module grant helpers."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.db.connection import session_scope
from shared.db.models import AppUser, HubModule, UserModule, identity_user_payload, utc_now_iso
from shared.logger_global import get_logger

log = get_logger(__name__)


def upsert_user_from_identity(identity_payload: dict[str, Any]) -> None:
    user = identity_payload.get("user") if isinstance(identity_payload, dict) else None
    fields = identity_user_payload(user if isinstance(user, dict) else None)
    workspace_id = fields["workspace_id"]
    if not workspace_id:
        log.debug("skip user upsert: missing workspace_id")
        return

    with session_scope() as session:
        _upsert_user(session, fields)
        _grant_enabled_modules(session, workspace_id)


def _upsert_user(session: Session, fields: dict[str, str | None]) -> AppUser:
    workspace_id = fields["workspace_id"]
    assert workspace_id

    now = utc_now_iso()
    existing = session.get(AppUser, workspace_id)
    if existing is None:
        user = AppUser(
            workspace_id=workspace_id,
            user_name=fields.get("user_name"),
            display_name=fields.get("display_name"),
            email=fields.get("email"),
            created_at=now,
            updated_at=now,
        )
        session.add(user)
        log.info("created app_user workspace_id={}", workspace_id)
        return user

    existing.user_name = fields.get("user_name")
    existing.display_name = fields.get("display_name")
    existing.email = fields.get("email")
    existing.updated_at = now
    log.debug("updated app_user workspace_id={}", workspace_id)
    return existing


def _grant_enabled_modules(session: Session, workspace_id: str) -> None:
    enabled_modules = session.scalars(
        select(HubModule.id).where(HubModule.enabled == 1).order_by(HubModule.sort_order)
    ).all()
    if not enabled_modules:
        return

    existing = {
        row.module_id
        for row in session.scalars(
            select(UserModule).where(UserModule.workspace_id == workspace_id)
        ).all()
    }

    now = utc_now_iso()
    granted = 0
    for module_id in enabled_modules:
        if module_id in existing:
            continue
        session.add(
            UserModule(
                workspace_id=workspace_id,
                module_id=module_id,
                granted_at=now,
            )
        )
        granted += 1

    if granted:
        log.info(
            "granted {} hub module(s) to workspace_id={}",
            granted,
            workspace_id,
        )


def get_user(workspace_id: str) -> AppUser | None:
    with session_scope() as session:
        user = session.get(AppUser, workspace_id)
        if user is None:
            return None
        session.expunge(user)
        return user
