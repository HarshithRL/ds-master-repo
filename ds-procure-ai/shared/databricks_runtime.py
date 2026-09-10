"""Databricks WorkspaceClient auth: Apps OAuth M2M / OBO vs local CLI profile.

Databricks Apps injects ``DATABRICKS_HOST``, ``DATABRICKS_CLIENT_ID``,
``DATABRICKS_CLIENT_SECRET``, and ``DATABRICKS_APP_NAME``. A leftover
``DATABRICKS_CONFIG_PROFILE`` makes the SDK look for ``~/.databrickscfg``,
which does not exist in the app container.
"""

from __future__ import annotations

import base64
import contextvars
import hashlib
import json
import os
from typing import Any, Mapping, MutableMapping

from databricks.sdk import WorkspaceClient

DEFAULT_PROFILE = "adb-7181820732839861"

_APP_NAME = "DATABRICKS_APP_NAME"
_CLIENT_ID = "DATABRICKS_CLIENT_ID"
_CLIENT_SECRET = "DATABRICKS_CLIENT_SECRET"
_HOST = "DATABRICKS_HOST"
_PROFILE = "DATABRICKS_CONFIG_PROFILE"

ACCESS_TOKEN_HEADER = "x-forwarded-access-token"
FORWARDED_IDENTITY_HEADERS = (
    ACCESS_TOKEN_HEADER,
    "x-forwarded-email",
    "x-forwarded-preferred-username",
    "x-forwarded-user",
)

# Visitor OBO token — never put this in log context dicts.
_obo_token: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "mate_obo_token", default=None
)
_obo_host: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "mate_obo_host", default=None
)


def is_databricks_app(environ: Mapping[str, str] | None = None) -> bool:
    env = os.environ if environ is None else environ
    if (env.get(_APP_NAME) or "").strip():
        return True
    return bool((env.get(_CLIENT_ID) or "").strip() and (env.get(_CLIENT_SECRET) or "").strip())


def cli_profile(environ: Mapping[str, str] | None = None) -> str:
    env = os.environ if environ is None else environ
    return (env.get(_PROFILE) or "").strip() or DEFAULT_PROFILE


def prepare_app_environ(environ: MutableMapping[str, str]) -> MutableMapping[str, str]:
    """Drop CLI profile auth when running as a Databricks App."""
    if is_databricks_app(environ):
        environ.pop(_PROFILE, None)
    return environ


def workspace_client() -> WorkspaceClient:
    """App service principal in Databricks Apps; CLI profile locally."""
    if is_databricks_app():
        host = (os.getenv(_HOST) or "").strip()
        client_id = (os.getenv(_CLIENT_ID) or "").strip()
        client_secret = (os.getenv(_CLIENT_SECRET) or "").strip()
        if host and client_id and client_secret:
            return WorkspaceClient(
                host=host,
                client_id=client_id,
                client_secret=client_secret,
                auth_type="oauth-m2m",
            )
        return WorkspaceClient()
    return WorkspaceClient(profile=cli_profile())


def obo_workspace_client(*, host: str, token: str) -> WorkspaceClient:
    """On-behalf-of user client from ``x-forwarded-access-token``.

    ``auth_type=pat`` is required so injected Apps M2M env vars do not win
    over the user token (same Bearer header, different identity).
    """
    return WorkspaceClient(host=host, token=token, auth_type="pat")


def _lowered_headers(headers: Any) -> dict[str, str]:
    if headers is None:
        return {}
    items = getattr(headers, "items", None)
    if not callable(items):
        return {}
    out: dict[str, str] = {}
    for key, value in items():
        if value is None:
            continue
        text = str(value).strip()
        if text:
            out[str(key).lower()] = text
    return out


def bind_obo_from_headers(headers: Any) -> None:
    """Bind visitor OBO from Apps ``X-Forwarded-*`` headers for this task."""
    lowered = _lowered_headers(headers)
    token = lowered.get(ACCESS_TOKEN_HEADER) or ""
    host = (os.getenv(_HOST) or "").strip() or None
    _obo_token.set(token or None)
    _obo_host.set(host)


def clear_obo() -> None:
    _obo_token.set(None)
    _obo_host.set(None)


def obo_is_bound() -> bool:
    return bool((_obo_token.get() or "").strip())


def obo_access_token() -> str | None:
    """Return the bound visitor OBO token, or None. Never log the return value."""
    token = (_obo_token.get() or "").strip()
    return token or None


def obo_token_scopes() -> list[str]:
    """Scope names on the bound visitor JWT. Never returns the token."""
    token = (_obo_token.get() or "").strip()
    if not token or token.count(".") < 2:
        return []
    try:
        payload = token.split(".")[1]
        pad = "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload + pad))
        raw = data.get("scope") or data.get("scp") or ""
        if isinstance(raw, str):
            return [part for s in raw.replace(",", " ").split() if (part := s.strip())]
        return [str(item) for item in raw]
    except Exception:
        return []


def obo_bind_key() -> str:
    """Stable non-secret id for the bound visitor token (safe to store on a connection)."""
    token = (_obo_token.get() or "").strip()
    if not token:
        return ""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _config_host(client: WorkspaceClient) -> str:
    raw = getattr(getattr(client, "config", None), "host", None) or ""
    return str(raw).strip()


def request_workspace_client() -> WorkspaceClient:
    """Visitor OBO client when the access token is bound; else app SP / CLI."""
    token = (_obo_token.get() or "").strip()
    if not token:
        return workspace_client()
    host = (_obo_host.get() or os.getenv(_HOST) or "").strip()
    if not host:
        host = _config_host(workspace_client())
    if not host:
        return workspace_client()
    return obo_workspace_client(host=host, token=token)


class _RequestScopedConfig:
    """Live WorkspaceClient.config so cached ChatDatabricks/embeddings re-auth."""

    def authenticate(self) -> Any:
        return request_workspace_client().config.authenticate()

    def __getattr__(self, name: str) -> Any:
        return getattr(request_workspace_client().config, name)


class RequestScopedWorkspaceClient(WorkspaceClient):
    """Delegates SDK calls to ``request_workspace_client()`` (OBO when bound).

    Subclasses ``WorkspaceClient`` so pydantic ``is_instance_of`` on
    ``ChatDatabricks.workspace_client`` accepts this proxy. ``config.authenticate``
    is resolved per HTTP call so a process-cached agent cannot freeze the first
    visitor's token.
    """

    def __init__(self) -> None:
        # Skip WorkspaceClient.__init__; every attribute is delegated live.
        return

    @property
    def config(self) -> _RequestScopedConfig:
        return _RequestScopedConfig()

    def __getattribute__(self, name: str) -> Any:
        if name in {
            "config",
            "__class__",
            "__dict__",
            "__module__",
            "__doc__",
            "__weakref__",
            "__repr__",
            "__str__",
            "__hash__",
            "__getattribute__",
            "__init__",
            "__new__",
        }:
            return object.__getattribute__(self, name)
        return getattr(request_workspace_client(), name)
