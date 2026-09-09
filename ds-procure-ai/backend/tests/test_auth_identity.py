"""Flask identity cache: refresh SP fallback when Apps sends an OBO token."""

from __future__ import annotations

from app import app
from routes.auth import SESSION_KEY, get_or_resolve_identity


class _Identity:
    def __init__(self, payload: dict):
        self._payload = payload

    def to_public_dict(self) -> dict:
        return self._payload


def test_identity_cache_hit_without_obo(monkeypatch):
    cached = {
        "env": "databricks_app",
        "user": {"auth": "obo_user", "id": "human"},
        "app": {"auth": "oauth_m2m", "id": "sp"},
    }

    def _boom(_request):
        raise AssertionError("should not re-resolve")

    monkeypatch.setattr("routes.auth.resolve_identities", _boom)
    with app.test_request_context("/api/auth"):
        from flask import session

        session[SESSION_KEY] = cached
        assert get_or_resolve_identity()["user"]["id"] == "human"


def test_identity_cache_refreshes_sp_fallback_when_obo_arrives(monkeypatch):
    refreshed = {
        "env": "databricks_app",
        "user": {"auth": "obo_user", "id": "human"},
        "app": {"auth": "oauth_m2m", "id": "sp"},
    }
    monkeypatch.setattr(
        "routes.auth.resolve_identities",
        lambda _request: _Identity(refreshed),
    )
    monkeypatch.setattr("routes.auth.upsert_user_from_identity", lambda _payload: None)

    with app.test_request_context(
        "/api/auth",
        headers={"X-Forwarded-Access-Token": "user-obo-token"},
    ):
        from flask import session

        session[SESSION_KEY] = {
            "env": "databricks_app",
            "user": {"auth": "oauth_m2m", "id": "sp"},
            "app": {"auth": "oauth_m2m", "id": "sp"},
        }
        payload = get_or_resolve_identity()
        assert payload["user"]["auth"] == "obo_user"
        assert payload["user"]["id"] == "human"
        assert session[SESSION_KEY]["user"]["id"] == "human"
