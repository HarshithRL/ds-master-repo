"""Resolve Databricks app + user identities for a Mate web session.

Never persist or return tokens. Rebuild WorkspaceClients per request when needed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from urllib.parse import urlsplit

from databricks.sdk import WorkspaceClient
from databricks.sdk.core import Config

from shared.databricks_runtime import (
    cli_profile,
    is_databricks_app,
    obo_workspace_client,
    workspace_client,
)
from shared.logger_global import get_logger

log = get_logger(__name__)

_SECRET_FRAGMENTS = ("token", "secret", "password", "authorization", "credential")
_FORWARDED_USER_HEADERS = (
    "x-forwarded-email",
    "x-forwarded-user",
    "x-forwarded-preferred-username",
    "x-forwarded-host",
)
_FIRST_CLASS_KEYS = ("kind", "auth", "id", "user_name", "display_name", "email")

ActorKind = Literal["app", "user"]
ActorAuth = Literal["oauth_m2m", "obo_user", "cli_profile"]
RuntimeEnv = Literal["databricks_app", "local"]


class IdentityError(Exception):
    """Failed to resolve Databricks identity for this request."""

    def __init__(self, message: str, status_code: int = 503) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class ActorIdentity:
    kind: ActorKind
    auth: ActorAuth
    id: str | None
    user_name: str | None
    display_name: str | None
    email: str | None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "auth": self.auth,
            "id": self.id,
            "user_name": self.user_name,
            "display_name": self.display_name,
            "email": self.email,
            "meta": dict(self.meta),
        }


@dataclass(frozen=True)
class SessionIdentity:
    env: RuntimeEnv
    workspace_host: str | None
    profile: str | None
    app_name: str | None
    resolved_at: str
    app: ActorIdentity
    user: ActorIdentity

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "env": self.env,
            "workspace_host": self.workspace_host,
            "profile": self.profile,
            "app_name": self.app_name,
            "resolved_at": self.resolved_at,
            "app": self.app.to_public_dict(),
            "user": self.user.to_public_dict(),
        }


def app_workspace_client() -> WorkspaceClient:
    return workspace_client()


def user_workspace_client(request) -> WorkspaceClient:
    if not is_databricks_app():
        return app_workspace_client()

    token = _header(request, "x-forwarded-access-token")
    if not token:
        log.warning("OBO token missing; using app service principal for user identity")
        return app_workspace_client()
    host = _workspace_host(app_workspace_client()) or (os.getenv("DATABRICKS_HOST") or "").strip()
    if not host:
        raise IdentityError("DATABRICKS_HOST is required for on-behalf-of user identity.")
    return obo_workspace_client(host=host, token=token)


def resolve_identities(request) -> SessionIdentity:
    if is_databricks_app():
        log.debug("resolving identity for databricks_app runtime")
        return _resolve_app(request)
    log.debug("resolving identity for local runtime")
    return _resolve_local()


def _resolve_local() -> SessionIdentity:
    client = app_workspace_client()
    try:
        sdk_user = client.current_user.me()
    except Exception as exc:
        raise IdentityError(
            f"Could not read CLI identity for profile {cli_profile()!r}."
        ) from exc

    host = _workspace_host(client)
    actor_kwargs = _actor_fields(sdk_user)
    extras = {
        "workspace_host": host,
        "profile": cli_profile(),
        "source": "cli_profile",
    }
    app = ActorIdentity(
        kind="app",
        auth="cli_profile",
        meta=_actor_meta(sdk_user, extras),
        **actor_kwargs,
    )
    user = ActorIdentity(
        kind="user",
        auth="cli_profile",
        meta=_actor_meta(sdk_user, extras),
        **actor_kwargs,
    )
    return SessionIdentity(
        env="local",
        workspace_host=host,
        profile=cli_profile(),
        app_name=None,
        resolved_at=_now_iso(),
        app=app,
        user=user,
    )


def _resolve_app(request) -> SessionIdentity:
    app_client = app_workspace_client()
    try:
        app_user = app_client.current_user.me()
    except Exception as exc:
        raise IdentityError("Could not read Databricks App service-principal identity.") from exc

    obo_token = _header(request, "x-forwarded-access-token")
    user_client = user_workspace_client(request)
    try:
        human_user = user_client.current_user.me()
    except Exception as exc:
        if obo_token:
            raise IdentityError("Could not read on-behalf-of user identity.", status_code=401) from exc
        log.warning("user identity fallback to app SP: {}", exc)
        human_user = app_user

    host = _workspace_host(app_client)
    app_name = os.getenv("DATABRICKS_APP_NAME") or None
    forwarded = _forwarded_user_headers(request)
    user_auth: ActorAuth = "obo_user" if obo_token else "oauth_m2m"
    user_source = "x_forwarded_obo" if obo_token else "databricks_app_sp_fallback"

    app = ActorIdentity(
        kind="app",
        auth="oauth_m2m",
        meta=_actor_meta(
            app_user,
            {
                "workspace_host": host,
                "DATABRICKS_APP_NAME": app_name,
                "source": "databricks_app_sp",
            },
        ),
        **_actor_fields(app_user),
    )
    user = ActorIdentity(
        kind="user",
        auth=user_auth,
        meta=_actor_meta(
            human_user,
            {
                "workspace_host": host,
                "source": user_source,
                **forwarded,
            },
        ),
        **_actor_fields(human_user),
    )
    return SessionIdentity(
        env="databricks_app",
        workspace_host=host,
        profile=None,
        app_name=app_name,
        resolved_at=_now_iso(),
        app=app,
        user=user,
    )


def _actor_fields(sdk_user) -> dict[str, str | None]:
    return {
        "id": _as_str(getattr(sdk_user, "id", None)),
        "user_name": _as_str(getattr(sdk_user, "user_name", None)),
        "display_name": _as_str(getattr(sdk_user, "display_name", None)),
        "email": _primary_email(sdk_user),
    }


def _actor_meta(sdk_user, extras: dict[str, Any]) -> dict[str, Any]:
    raw: dict[str, Any] = {}
    as_dict = getattr(sdk_user, "as_dict", None)
    if callable(as_dict):
        raw.update(_jsonable(as_dict()) or {})
    else:
        raw.update(_jsonable(_shallow_user(sdk_user)) or {})

    for key, value in extras.items():
        if value is None or value == "":
            continue
        raw[key] = _jsonable(value)

    meta: dict[str, Any] = {}
    for key, value in raw.items():
        if key in _FIRST_CLASS_KEYS:
            continue
        if _is_secret_key(str(key)):
            continue
        if value is None or value == "" or value == []:
            continue
        meta[str(key)] = value
    return meta


def _primary_email(sdk_user) -> str | None:
    emails = getattr(sdk_user, "emails", None) or []
    for item in emails:
        primary = getattr(item, "primary", None)
        if primary is None and isinstance(item, dict):
            primary = item.get("primary")
        if primary:
            value = getattr(item, "value", None)
            if value is None and isinstance(item, dict):
                value = item.get("value")
            email = _as_str(value)
            if email:
                return email
    if emails:
        first = emails[0]
        value = getattr(first, "value", None)
        if value is None and isinstance(first, dict):
            value = first.get("value")
        email = _as_str(value)
        if email:
            return email
    user_name = _as_str(getattr(sdk_user, "user_name", None))
    if user_name and "@" in user_name:
        return user_name
    return None


def _forwarded_user_headers(request) -> dict[str, str]:
    found: dict[str, str] = {}
    for name in _FORWARDED_USER_HEADERS:
        value = _header(request, name)
        if value:
            found[name] = value
    return found


def _header(request, name: str) -> str | None:
    value = request.headers.get(name) or request.headers.get(name.title())
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None


def _workspace_host(client: WorkspaceClient) -> str | None:
    raw = getattr(getattr(client, "config", None), "host", None) or os.getenv("DATABRICKS_HOST")
    if not raw:
        try:
            raw = Config().host
        except Exception:
            return None
    host = str(raw).strip().rstrip("/")
    if not host:
        return None
    if not host.startswith(("http://", "https://")):
        host = "https://" + host
    parts = urlsplit(host)
    if not parts.scheme or not parts.netloc:
        return host
    return f"{parts.scheme}://{parts.netloc}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _is_secret_key(key: str) -> bool:
    lowered = key.lower().replace("-", "_")
    return any(fragment in lowered for fragment in _SECRET_FRAGMENTS)


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, inner in value.items():
            if _is_secret_key(str(key)):
                continue
            cleaned = _jsonable(inner)
            if cleaned is None or cleaned == "" or cleaned == []:
                continue
            out[str(key)] = cleaned
        return out
    if isinstance(value, (list, tuple)):
        compacted = _compact_scim_list(value)
        if compacted is not None:
            return compacted
        return [item for item in (_jsonable(v) for v in value) if item is not None and item != ""]
    as_dict = getattr(value, "as_dict", None)
    if callable(as_dict):
        return _jsonable(as_dict())
    return str(value)


def _compact_scim_list(value: Any) -> list[str] | None:
    if not isinstance(value, (list, tuple)) or not value:
        return None
    labels: list[str] = []
    for item in value:
        label = _scim_label(item)
        if label:
            labels.append(label)
    if labels and len(labels) == len([i for i in value if _scim_label(i)]):
        return labels[:40]
    return None


def _scim_label(item: Any) -> str | None:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return _as_str(
            item.get("display")
            or item.get("value")
            or item.get("displayName")
            or item.get("display_name")
        )
    return _as_str(
        getattr(item, "display", None)
        or getattr(item, "value", None)
        or getattr(item, "display_name", None)
    )


def _shallow_user(sdk_user) -> dict[str, Any]:
    return {
        "id": getattr(sdk_user, "id", None),
        "userName": getattr(sdk_user, "user_name", None),
        "displayName": getattr(sdk_user, "display_name", None),
        "active": getattr(sdk_user, "active", None),
        "externalId": getattr(sdk_user, "external_id", None),
    }
