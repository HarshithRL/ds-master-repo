"""Databricks WorkspaceClient auth: Apps OAuth M2M / OBO vs local CLI profile.

Databricks Apps injects ``DATABRICKS_HOST``, ``DATABRICKS_CLIENT_ID``,
``DATABRICKS_CLIENT_SECRET``, and ``DATABRICKS_APP_NAME``. A leftover
``DATABRICKS_CONFIG_PROFILE`` makes the SDK look for ``~/.databrickscfg``,
which does not exist in the app container.
"""

from __future__ import annotations

import os
from typing import Mapping, MutableMapping

from databricks.sdk import WorkspaceClient

DEFAULT_PROFILE = "adb-7181820732839861"

_APP_NAME = "DATABRICKS_APP_NAME"
_CLIENT_ID = "DATABRICKS_CLIENT_ID"
_CLIENT_SECRET = "DATABRICKS_CLIENT_SECRET"
_HOST = "DATABRICKS_HOST"
_PROFILE = "DATABRICKS_CONFIG_PROFILE"


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
