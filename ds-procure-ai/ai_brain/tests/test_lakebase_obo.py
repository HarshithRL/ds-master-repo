from __future__ import annotations

from types import SimpleNamespace

from ai_brain.server.lakebase import _mint_token, _resolve_username
from shared.databricks_runtime import bind_obo_from_headers, clear_obo


def test_resolve_username_uses_pguser(monkeypatch):
    monkeypatch.setenv("PGUSER", "app-sp-user")
    clear_obo()
    ws = SimpleNamespace()
    assert _resolve_username(ws) == "app-sp-user"


def test_resolve_username_uses_pguser_even_when_visitor_obo_bound(monkeypatch):
    monkeypatch.setenv("PGUSER", "app-sp-user")
    bind_obo_from_headers({"x-forwarded-access-token": "visitor-obo"})
    try:
        ws = SimpleNamespace(
            current_user=SimpleNamespace(
                me=lambda: SimpleNamespace(user_name="human@etexgroup.com")
            )
        )
        assert _resolve_username(ws) == "app-sp-user"
    finally:
        clear_obo()


def test_resolve_username_falls_back_to_workspace_current_user(monkeypatch):
    monkeypatch.delenv("PGUSER", raising=False)
    ws = SimpleNamespace(
        current_user=SimpleNamespace(
            me=lambda: SimpleNamespace(user_name="a65ce6d4-0267-43b3-a6c4-b24c39a35d05")
        )
    )
    assert _resolve_username(ws) == "a65ce6d4-0267-43b3-a6c4-b24c39a35d05"


def test_mint_token_reads_generate_database_credential():
    cred = SimpleNamespace(token="db-oauth")
    ws = SimpleNamespace(
        postgres=SimpleNamespace(generate_database_credential=lambda endpoint: cred)
    )
    assert _mint_token(ws, "projects/x/endpoints/e") == "db-oauth"
