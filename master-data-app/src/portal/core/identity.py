"""Who submitted the request, read from the Databricks Apps proxy headers."""

from __future__ import annotations

from typing import Mapping

import pandas as pd

from portal.config import setting
from portal.core.utils import active_rows, clean

Headers = Mapping[str, str]


def requester_user(headers: Headers | None) -> str:
    """Best-effort user label for audit fields."""
    for header_name in (
        "x-forwarded-email",
        "x-forwarded-preferred-username",
        "x-forwarded-user",
    ):
        value = clean((headers or {}).get(header_name))
        if value:
            return value

    return "Databricks App User"


def requester_email(headers: Headers | None) -> str:
    for header_name in (
        "x-forwarded-email",
        "x-forwarded-preferred-username",
    ):
        value = clean((headers or {}).get(header_name))
        if "@" in value:
            return value

    user_value = requester_user(headers)
    if "@" in user_value:
        return user_value

    # Local runs have no proxy headers; DEMO_REQUESTER_EMAIL names the requester
    return setting("DEMO_REQUESTER_EMAIL")


def requester_name(headers: Headers | None) -> str:
    """Friendly name for notification content."""
    email = requester_email(headers)
    if email:
        local_part = email.split("@", 1)[0]
        return local_part.replace(".", " ").replace("_", " ").title()

    return requester_user(headers)


def master_data_emails(assignment_rules: dict[str, pd.DataFrame]) -> set[str]:
    """
    The Master Data team: active Members in assignment_rules.xlsx (the people
    requests are assigned to), plus emails in WORKBENCH_ADMINS (comma separated).
    """
    members = active_rows(assignment_rules.get("members", pd.DataFrame()))
    emails = {clean(email).casefold() for email in members.get("email", []) if clean(email)}
    emails |= {clean(e).casefold() for e in setting("WORKBENCH_ADMINS").split(",") if clean(e)}
    return emails


def is_master_data_member(email: str, assignment_rules: dict[str, pd.DataFrame]) -> bool:
    return bool(clean(email)) and clean(email).casefold() in master_data_emails(assignment_rules)
