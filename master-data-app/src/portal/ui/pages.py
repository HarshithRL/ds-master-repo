"""
Right-panel request flows.

- render_waiting_sections: before a Sales Organization is chosen
- render_standard_request: Create / Extend, every rule-driven field
- render_change_request: Change, only the fields the requester picks
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
import streamlit as st

from portal.constants import (
    CREDIT_MANAGEMENT,
    PREREQUISITE_TEXT,
    RULE_SECTIONS,
    SECTION_KEYS,
    SECTIONS,
)
from portal.core.credit import get_credit_fields, get_credit_mapping, plan_credit_form
from portal.core.payload import (
    build_change_original_defaults,
    build_change_payload,
    build_original_defaults,
    build_request_payload,
    request_information,
)
from portal.core.rules import (
    copy_computed_values,
    get_original_defaults,
    split_rule_sections,
)
from portal.core.validation import (
    build_change_section_statuses,
    build_section_statuses,
    collect_change_errors,
    collect_validation_errors,
)
from portal.ui.actions import handle_submit, render_action_buttons, render_last_request_reference
from portal.ui.change_request import credit_change_fields, render_change_section, rule_change_fields
from portal.ui.credit import render_credit_management
from portal.ui.general_data import (
    render_attachments,
    render_bank_details_attachment,
    render_general_data_requests,
)
from portal.ui.sections import render_partner_functions, render_section
from portal.ui.theme import SECTION_CONTAINER_PREFIX, apply_section_statuses
from portal.ui.widgets import render_section_comment


@dataclass(frozen=True)
class RequestContext:
    """Everything the right panel needs once the request scope is known."""

    request_type: str
    customer_id: str
    customer: dict[str, str]
    company_code: str
    sales_org: str
    request_comment: str
    fields: pd.DataFrame
    rules: dict[str, pd.DataFrame]
    credit_rules: dict[str, pd.DataFrame]
    assignment_rules: dict[str, pd.DataFrame]
    reference_library: dict[str, pd.DataFrame]

    @property
    def rule_context(self) -> dict[str, str]:
        """Values readonly rule fields can show."""
        return {
            "customer_id": self.customer_id,
            "company_code": self.company_code,
            "sales_organization": self.sales_org,
        }

    @property
    def request_info(self) -> dict[str, str]:
        return request_information(
            request_type=self.request_type,
            customer_id=self.customer_id,
            company_code=self.company_code,
            sales_org=self.sales_org,
        )


def create_section_expanders(panel) -> dict[str, Any]:
    """
    The five collapsed section expanders, keyed like SECTION_KEYS.

    Each sits in a keyed container (class st-key-section__<key>) so
    apply_section_statuses can colour exactly that section.
    """
    return {
        key: panel.container(key=f"{SECTION_CONTAINER_PREFIX}{key}").expander(title, expanded=False)
        for key, title in SECTIONS
    }


def render_waiting_sections(panel) -> None:
    for expander in create_section_expanders(panel).values():
        with expander:
            st.caption(PREREQUISITE_TEXT)

    apply_section_statuses({key: "neutral" for key in SECTION_KEYS})


@dataclass
class GeneralDataInput:
    values: dict[str, dict[str, str]]
    duplicates: list[str]
    bank_attachments: list[dict[str, Any]]
    bank_attachment_errors: list[str]
    attachments: list[dict[str, Any]]
    attachment_errors: list[str]
    comment: str

    def status_args(self) -> dict[str, Any]:
        return {
            "general_data_values": self.values,
            "general_data_duplicates": self.duplicates,
            "bank_attachments": self.bank_attachments,
            "attachments": self.attachments,
            "bank_attachment_errors": self.bank_attachment_errors,
            "attachment_errors": self.attachment_errors,
        }

    def error_args(self) -> dict[str, Any]:
        return {
            "general_data_values": self.values,
            "general_data_duplicates": self.duplicates,
            "attachment_errors": self.attachment_errors,
            "bank_attachment_errors": self.bank_attachment_errors,
        }


def _render_general_data(ctx: RequestContext) -> GeneralDataInput:
    values, duplicates, bank_required = render_general_data_requests(
        customer=ctx.customer,
        reference_library=ctx.reference_library,
    )
    bank_attachments, bank_errors = render_bank_details_attachment(bank_required)
    attachments, attachment_errors = render_attachments()

    return GeneralDataInput(
        values=values,
        duplicates=duplicates,
        bank_attachments=bank_attachments,
        bank_attachment_errors=bank_errors,
        attachments=attachments,
        attachment_errors=attachment_errors,
        comment=render_section_comment("general_data"),
    )


# =============================================================================
# CREATE / EXTEND
# =============================================================================


def render_standard_request(panel, ctx: RequestContext) -> None:
    expanders = create_section_expanders(panel)
    sections = split_rule_sections(ctx.fields)
    values: dict[str, dict[str, str]] = {}
    comments = {"request_information": ctx.request_comment}

    with expanders["general_data"]:
        general = _render_general_data(ctx)
    comments["general_data"] = general.comment

    for section_key in RULE_SECTIONS:
        render = render_partner_functions if section_key == "partner_functions" else render_section

        with expanders[section_key]:
            values[section_key] = render(
                section_fields=sections[section_key],
                company_code=ctx.company_code,
                sales_org=ctx.sales_org,
                rules=ctx.rules,
                context=ctx.rule_context,
            )
            comments[section_key] = render_section_comment(section_key)

    with expanders["credit_management"]:
        values["credit_management"], credit_defaults, credit_fields, credit_mapping = (
            render_credit_management(
                company_code=ctx.company_code,
                sales_org=ctx.sales_org,
                customer=ctx.customer,
                credit_rules=ctx.credit_rules,
            )
        )
        comments["credit_management"] = render_section_comment("credit_management")

    # Computed Company Code fields copy their Sales & Distribution source
    copy_computed_values(
        sections["company_code"],
        values["company_code"],
        values["sales_distribution"],
    )

    original_defaults = build_original_defaults(
        get_original_defaults(
            fields=ctx.fields,
            company_code=ctx.company_code,
            sales_org=ctx.sales_org,
            rules=ctx.rules,
            context=ctx.rule_context,
        ),
        credit_defaults,
    )

    payload = build_request_payload(
        request_info=ctx.request_info,
        customer=ctx.customer,
        general_data_values=general.values,
        section_values=values,
        section_comments=comments,
        attachments=general.bank_attachments + general.attachments,
        credit_mapping=credit_mapping,
    )

    apply_section_statuses(
        build_section_statuses(
            **general.status_args(),
            company_fields=sections["company_code"],
            company_values=values["company_code"],
            sales_fields=sections["sales_distribution"],
            sales_values=values["sales_distribution"],
            partner_fields=sections["partner_functions"],
            partner_values=values["partner_functions"],
            credit_fields=credit_fields,
            credit_values=values["credit_management"],
        )
    )

    with panel.container():
        submit_clicked = render_action_buttons("request")

    if submit_clicked:
        handle_submit(
            validate=lambda: collect_validation_errors(
                fields=ctx.fields,
                company_values=values["company_code"],
                sales_values=values["sales_distribution"],
                partner_values=values["partner_functions"],
                credit_fields=credit_fields,
                credit_values=values["credit_management"],
                **general.error_args(),
            ),
            payload=payload,
            original_defaults=original_defaults,
            assignment_rules=ctx.assignment_rules,
        )

    render_last_request_reference()


# =============================================================================
# CHANGE
# =============================================================================


def render_change_request(panel, ctx: RequestContext) -> None:
    expanders = create_section_expanders(panel)
    sections = split_rule_sections(ctx.fields)
    comments = {"request_information": ctx.request_comment}
    entries_by_section = {}

    with expanders["general_data"]:
        general = _render_general_data(ctx)
    comments["general_data"] = general.comment

    for section_key, section_title in RULE_SECTIONS.items():
        with expanders[section_key]:
            entries_by_section[section_key] = render_change_section(
                section_key=section_key,
                section_title=section_title,
                fields=rule_change_fields(
                    sections[section_key],
                    company_code=ctx.company_code,
                    sales_org=ctx.sales_org,
                    rules=ctx.rules,
                    include_partner_names=section_key == "partner_functions",
                ),
                customer=ctx.customer,
            )
            comments[section_key] = render_section_comment(section_key)

    credit_mapping = get_credit_mapping(
        company_code=ctx.company_code,
        credit_rules=ctx.credit_rules,
    )
    credit_plan = plan_credit_form(
        fields=get_credit_fields(ctx.credit_rules),
        customer=ctx.customer,
        mapping=credit_mapping,
    )

    with expanders["credit_management"]:
        entries_by_section["credit_management"] = render_change_section(
            section_key="credit_management",
            section_title=CREDIT_MANAGEMENT,
            fields=credit_change_fields(credit_plan.field_map),
            customer=ctx.customer,
        )
        comments["credit_management"] = render_section_comment("credit_management")

    entries = [entry for section in entries_by_section.values() for entry in section]

    payload = build_change_payload(
        request_info=ctx.request_info,
        customer=ctx.customer,
        general_data_values=general.values,
        entries=entries,
        section_comments=comments,
        attachments=general.bank_attachments + general.attachments,
        credit_mapping=credit_mapping,
    )

    apply_section_statuses(
        build_change_section_statuses(
            **general.status_args(),
            entries_by_section=entries_by_section,
        )
    )

    with panel.container():
        submit_clicked = render_action_buttons("change")

    if submit_clicked:
        handle_submit(
            validate=lambda: collect_change_errors(**general.error_args(), entries=entries),
            payload=payload,
            original_defaults=build_change_original_defaults(entries),
            assignment_rules=ctx.assignment_rules,
        )

    render_last_request_reference()
