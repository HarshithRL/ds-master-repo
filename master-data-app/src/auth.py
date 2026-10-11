from __future__ import annotations

import os

import streamlit as st

from helpers import clean


def workspace_host() -> str:
    """Normalize DATABRICKS_HOST to always include https://."""
    host = clean(
        os.environ.get(
            "DATABRICKS_HOST",
            "",
        )
    )

    if not host:
        raise RuntimeError("DATABRICKS_HOST is not available in the app environment.")

    if not host.startswith(("http://", "https://")):
        host = "https://" + host

    return host.rstrip("/")


def forwarded_user_token() -> str:
    token = clean(st.context.headers.get("x-forwarded-access-token"))

    if not token:
        raise RuntimeError(
            "No forwarded Databricks user token was received. "
            "In the app, go to Settings \u2192 User authorization and enable "
            "the 'sql' scope, then reopen the app."
        )

    return token


def current_request_user() -> str:
    headers = st.context.headers

    for header_name in (
        "x-forwarded-email",
        "x-forwarded-preferred-username",
        "x-forwarded-user",
    ):
        value = clean(headers.get(header_name))

        if value:
            return value

    return "Databricks App User"


def current_request_email() -> str:
    headers = st.context.headers

    for header_name in (
        "x-forwarded-email",
        "x-forwarded-preferred-username",
    ):
        value = clean(headers.get(header_name))
        if "@" in value:
            return value

    user_value = current_request_user()
    return user_value if "@" in user_value else ""


def current_request_name() -> str:
    email = current_request_email()

    if email:
        local_part = email.split("@", 1)[0]
        return local_part.replace(".", " ").replace("_", " ").title()

    return current_request_user()
