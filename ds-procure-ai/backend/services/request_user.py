"""Resolve the current user's Databricks workspace id from the Flask session."""

from __future__ import annotations

from flask import jsonify

from routes.auth import get_or_resolve_identity


class AuthRequiredError(Exception):
    def __init__(self, message: str = "Authentication required") -> None:
        super().__init__(message)


def get_workspace_id(*, sync_user: bool = False) -> str | None:
    identity = get_or_resolve_identity()
    if sync_user:
        try:
            from shared.db.repos.users import upsert_user_from_identity

            upsert_user_from_identity(identity)
        except Exception:
            pass
    user = identity.get("user") if isinstance(identity, dict) else None
    if not isinstance(user, dict):
        return None
    workspace_id = str(user.get("id") or "").strip()
    return workspace_id or None


def require_workspace_id() -> str:
    workspace_id = get_workspace_id()
    if not workspace_id:
        raise AuthRequiredError()
    return workspace_id


def auth_error_response(exc: AuthRequiredError):
    return jsonify({"error": "unauthorized", "detail": str(exc)}), 401
