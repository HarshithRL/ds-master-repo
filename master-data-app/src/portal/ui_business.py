from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from .data import (
    find_default,
    get_credit_fields,
    get_credit_initial_value,
    get_credit_mapping,
    get_field_options,
)
from .ui_common import apply_required_widget_state
from .utils import as_int, clean, format_option, is_yes


def render_credit_management(
    *,
    company_code: str,
    sales_org: str,
    customer: dict[str, str],
    credit_rules: dict[str, pd.DataFrame],
) -> tuple[dict[str, str], dict[str, str], pd.DataFrame, dict[str, str] | None,]:
    fields = get_credit_fields(credit_rules)
    mapping = get_credit_mapping(
        company_code=company_code,
        credit_rules=credit_rules,
    )

    if mapping is None:
        st.warning(
            "No active Credit Management mapping is configured for "
            f"Company Code {company_code}."
        )
    else:
        st.caption(
            "Credit mapping: "
            f"{mapping.get('company_name', '')} · Company Code {company_code}"
        )

    values: dict[str, str] = {}
    defaults: dict[str, str] = {}

    source_defaults = {
        clean(row.get("field_key")): get_credit_initial_value(
            field=row,
            customer=customer,
            mapping=mapping,
        )
        for row in fields.to_dict("records")
    }

    credit_controller_initial = clean(source_defaults.get("credit_controller"))
    credit_analyst_initial = clean(source_defaults.get("credit_analyst"))
    same_credit_owner = bool(
        credit_controller_initial
        and credit_analyst_initial
        and credit_controller_initial.casefold() == credit_analyst_initial.casefold()
    )

    display_fields = fields.copy()
    if same_credit_owner:
        display_fields = fields[
            ~fields["field_key"].astype(str).str.strip().eq("credit_analyst")
        ].copy()

    field_map = {
        clean(row.get("field_key")): row
        for row in display_fields.to_dict("records")
        if clean(row.get("field_key"))
    }
    rendered_keys: set[str] = set()

    def render_credit_field(
        field_key: str,
        *,
        placeholder: str | None = None,
    ) -> None:
        field = field_map.get(field_key)
        if not field:
            return

        label = clean(field.get("label")) or field_key
        required = is_yes(field.get("required"))
        editable = is_yes(field.get("editable"))
        input_type = clean(field.get("input_type")).lower() or "text"
        notes = clean(field.get("notes"))
        initial_value = get_credit_initial_value(
            field=field,
            customer=customer,
            mapping=mapping,
        )

        defaults[field_key] = initial_value
        display_label = f"{label} *" if required else label
        widget_key = f"credit__{field_key}"

        value = st.text_input(
            display_label,
            value=initial_value,
            disabled=True if input_type == "readonly" else not editable,
            key=widget_key,
            help=notes or None,
            placeholder=placeholder,
        )

        apply_required_widget_state(
            widget_key=widget_key,
            value=value,
            required=required,
        )

        values[field_key] = clean(value)
        rendered_keys.add(field_key)

    st.markdown("##### Collection Contact")
    st.caption(
        "Person or department responsible for collection-related enquiries "
        "and outstanding invoices."
    )

    contact_name_col, contact_email_col, contact_phone_col = st.columns(
        [1, 1.25, 0.85], gap="small"
    )
    with contact_name_col:
        render_credit_field("collection_contact_name", placeholder="Enter name")
    with contact_email_col:
        render_credit_field("collection_contact_email", placeholder="Enter email")
    with contact_phone_col:
        render_credit_field("collection_contact_phone", placeholder="Enter phone")

    st.divider()
    st.markdown("##### Requested Credit Limit")
    credit_limit_col, currency_col, _ = st.columns([1, 1, 1], gap="small")
    with credit_limit_col:
        render_credit_field("credit_limit", placeholder="Enter amount")
    with currency_col:
        render_credit_field("credit_currency", placeholder="Enter currency")

    st.divider()
    st.markdown("##### Credit Responsibility")
    controller_col, specialist_col, analyst_col = st.columns([1, 1, 1], gap="small")
    with controller_col:
        render_credit_field("credit_controller")
    with specialist_col:
        render_credit_field("collection_specialist")
    if "credit_analyst" in field_map and not same_credit_owner:
        with analyst_col:
            render_credit_field("credit_analyst")

    accounting_col, accounting_phone_col, accounting_email_col = st.columns(
        [1, 1, 1], gap="small"
    )
    with accounting_col:
        render_credit_field("accounting_clerk")
    with accounting_phone_col:
        render_credit_field("accounting_clerk_phone")
    with accounting_email_col:
        render_credit_field("accounting_clerk_email")

    st.divider()
    st.markdown("##### Credit & Dunning Configuration")
    dunning_procedure_col, dunning_clerk_col, risk_class_col = st.columns(
        [1, 1, 1], gap="small"
    )
    with dunning_procedure_col:
        render_credit_field("dunning_procedure")
    with dunning_clerk_col:
        render_credit_field("dunning_clerk")
    with risk_class_col:
        render_credit_field("risk_class")

    check_rule_col, mig_rule_col, _ = st.columns([1, 1, 1], gap="small")
    with check_rule_col:
        render_credit_field("check_rule")
    with mig_rule_col:
        render_credit_field("mig_rule")

    remaining_fields: list[tuple[str, dict[str, Any]]] = []
    for field_key, field in field_map.items():
        if field_key not in rendered_keys:
            remaining_fields.append((field_key, field))

    if remaining_fields:
        st.divider()
        st.markdown("##### Additional Credit Information")
        additional_columns = st.columns(3, gap="small")
        for index, (field_key, _field) in enumerate(remaining_fields):
            with additional_columns[index % 3]:
                render_credit_field(field_key)

    if same_credit_owner:
        values["credit_analyst"] = clean(
            values.get("credit_controller") or credit_controller_initial
        )
        defaults["credit_analyst"] = credit_analyst_initial

    values["collection_contact"] = clean(values.get("collection_contact_name"))

    return values, defaults, display_fields, mapping


def render_rule_field(
    *,
    field: dict[str, Any],
    company_code: str,
    sales_org: str,
    rules: dict[str, pd.DataFrame],
    context: dict[str, str],
) -> str:
    field_key = clean(field.get("field_key"))
    label = clean(field.get("label")) or field_key

    partner_label_overrides = {
        "partner_yf_email": "Invoice Email Address (YF)",
        "partner_cp_email": "Contact Person Email (CP)",
        "partner_yl_email": "Logistics Contact Email (YL)",
        "partner_yb_employee_id": "Sales Rep Employee ID (YB)",
        "partner_yz_employee_id": "Customer Service Employee ID (YZ)",
        "bill_to_party_mode": "Bill-to Party (BP)",
        "payer_mode": "Payer (PY)",
        "ship_to_party_mode": "Ship-to Party (SH)",
    }
    label = partner_label_overrides.get(field_key, label)

    required = is_yes(field.get("required"))
    hidden = is_yes(field.get("hidden"))
    editable = is_yes(field.get("editable"))
    input_type = clean(field.get("input_type")).lower() or "text"
    notes = clean(field.get("notes"))
    max_length = as_int(field.get("max_length"))
    label_with_required = f"{label} *" if required else label

    if input_type == "readonly":
        value = clean(context.get(field_key))
        if not hidden:
            widget_key = f"form__{field_key}"
            st.text_input(
                label_with_required,
                value=value,
                disabled=True,
                key=widget_key,
                help=notes or None,
            )
            apply_required_widget_state(
                widget_key=widget_key,
                value=value,
                required=required,
            )
        return value

    if input_type == "computed":
        copy_from = clean(field.get("copy_from_field"))
        value = clean(st.session_state.get(f"form__{copy_from}", ""))
        if not hidden:
            widget_key = f"computed_display__{field_key}"
            st.text_input(
                label_with_required,
                value=value,
                disabled=True,
                key=widget_key,
                help=notes or None,
            )
            apply_required_widget_state(
                widget_key=widget_key,
                value=value,
                required=required,
            )
        return value

    option_rows = get_field_options(
        field_key=field_key,
        company_code=company_code,
        sales_org=sales_org,
        rules=rules,
    )
    default_value = find_default(field, option_rows)
    widget_key = f"form__{field_key}"

    if hidden:
        return default_value

    if input_type == "select":
        option_values = [option["value"] for option in option_rows if option["value"]]
        descriptions = {
            option["value"]: option["description"] for option in option_rows
        }

        if not option_values:
            value = st.text_input(
                label_with_required,
                value=default_value,
                key=widget_key,
                disabled=not editable,
                max_chars=max_length,
                help=notes or None,
            )
            apply_required_widget_state(
                widget_key=widget_key,
                value=value,
                required=required,
            )
            return clean(value)

        options = list(dict.fromkeys(option_values))
        if not required:
            options = [""] + options

        current_value = clean(st.session_state.get(widget_key, default_value))
        if current_value and current_value not in options:
            options.insert(0, current_value)

        if current_value in options:
            index = options.index(current_value)
        elif default_value in options:
            index = options.index(default_value)
        else:
            index = 0

        value = st.selectbox(
            label_with_required,
            options=options,
            index=index,
            key=widget_key,
            disabled=not editable,
            format_func=lambda code: (
                ""
                if code == ""
                else (
                    clean(context.get("customer_id"))
                    if (
                        field_key
                        in {
                            "bill_to_party_mode",
                            "payer_mode",
                            "ship_to_party_mode",
                        }
                        and code == "SAME_AS_CUSTOMER"
                        and clean(context.get("customer_id"))
                    )
                    else format_option(
                        code,
                        descriptions.get(code, ""),
                    )
                )
            ),
            help=notes or None,
        )
        apply_required_widget_state(
            widget_key=widget_key,
            value=value,
            required=required,
        )
        return clean(value)

    if input_type == "textarea":
        value = st.text_area(
            label_with_required,
            value=default_value,
            key=widget_key,
            disabled=not editable,
            height=110,
            max_chars=max_length,
            help=notes or None,
        )
        apply_required_widget_state(
            widget_key=widget_key,
            value=value,
            required=required,
        )
        return clean(value)

    value = st.text_input(
        label_with_required,
        value=default_value,
        key=widget_key,
        disabled=not editable,
        max_chars=max_length,
        help=notes or None,
    )
    apply_required_widget_state(
        widget_key=widget_key,
        value=value,
        required=required,
    )
    return clean(value)


def render_section(
    *,
    section_name: str,
    section_fields: pd.DataFrame,
    company_code: str,
    sales_org: str,
    rules: dict[str, pd.DataFrame],
    context: dict[str, str],
) -> dict[str, str]:
    values: dict[str, str] = {}

    if section_fields.empty:
        st.info("No active fields are configured for this section.")
        return values

    columns = st.columns(3, gap="small")
    visible_index = 0

    for _, row in section_fields.iterrows():
        field = row.to_dict()
        field_key = clean(field.get("field_key"))

        if is_yes(field.get("hidden")):
            values[field_key] = clean(
                render_rule_field(
                    field=field,
                    company_code=company_code,
                    sales_org=sales_org,
                    rules=rules,
                    context=context,
                )
            )
            continue

        with columns[visible_index % 3]:
            values[field_key] = clean(
                render_rule_field(
                    field=field,
                    company_code=company_code,
                    sales_org=sales_org,
                    rules=rules,
                    context=context,
                )
            )
        visible_index += 1

    return values


def render_partner_functions(
    *,
    section_fields: pd.DataFrame,
    company_code: str,
    sales_org: str,
    rules: dict[str, pd.DataFrame],
    context: dict[str, str],
) -> dict[str, str]:
    st.caption(
        "Invoice Email Address (YF), Contact Person (CP) and Logistics Contact (YL) "
        "use email addresses. Enter the contact name as well for CP and YL. "
        "Sales Rep (YB) and Customer Service Employee (YZ) use existing Salesforce employee IDs."
    )

    values: dict[str, str] = {}

    if section_fields.empty:
        st.info("No active Partner Functions are configured for this combination.")
        return values

    field_map = {
        clean(row.get("field_key")): row
        for row in section_fields.to_dict("records")
        if clean(row.get("field_key"))
    }

    def render_key(field_key: str) -> str:
        field = field_map.get(field_key)
        if not field:
            return ""

        value = clean(
            render_rule_field(
                field=field,
                company_code=company_code,
                sales_org=sales_org,
                rules=rules,
                context=context,
            )
        )
        values[field_key] = value
        return value

    st.markdown("##### Contact Partner Functions")
    st.caption(
        "Enter the contact details for invoicing, sales orders and logistics. "
        "Sales Rep (YB) and Customer Service Employee (YZ) use existing "
        "Salesforce employee IDs."
    )

    st.markdown("**Invoice Contact (YF)**")
    invoice_contact_col, _ = st.columns([2, 1], gap="small")
    with invoice_contact_col:
        render_key("partner_yf_email")

    st.divider()
    st.markdown("**Sales Order Contact (CP)**")
    st.caption("Person responsible for sales order-related communication.")

    cp_first_name_col, cp_last_name_col, cp_email_col = st.columns(
        [1, 1, 1.25], gap="small"
    )
    with cp_first_name_col:
        cp_first_name = clean(
            st.text_input(
                "First Name",
                key="form__partner_cp_first_name",
                max_chars=60,
                placeholder="Enter first name",
            )
        )
    with cp_last_name_col:
        cp_last_name = clean(
            st.text_input(
                "Surname",
                key="form__partner_cp_last_name",
                max_chars=60,
                placeholder="Enter surname",
            )
        )
    with cp_email_col:
        render_key("partner_cp_email")

    values["partner_cp_first_name"] = cp_first_name
    values["partner_cp_last_name"] = cp_last_name
    values["partner_cp_name"] = clean(
        " ".join(part for part in [cp_first_name, cp_last_name] if part)
    )

    st.divider()
    st.markdown("**Logistics Contact (YL)**")
    st.caption("Person responsible for delivery and logistics-related communication.")

    yl_first_name_col, yl_last_name_col, yl_email_col = st.columns(
        [1, 1, 1.25], gap="small"
    )
    with yl_first_name_col:
        yl_first_name = clean(
            st.text_input(
                "First Name",
                key="form__partner_yl_first_name",
                max_chars=60,
                placeholder="Enter first name",
            )
        )
    with yl_last_name_col:
        yl_last_name = clean(
            st.text_input(
                "Surname",
                key="form__partner_yl_last_name",
                max_chars=60,
                placeholder="Enter surname",
            )
        )
    with yl_email_col:
        render_key("partner_yl_email")

    values["partner_yl_first_name"] = yl_first_name
    values["partner_yl_last_name"] = yl_last_name
    values["partner_yl_name"] = clean(
        " ".join(part for part in [yl_first_name, yl_last_name] if part)
    )

    st.divider()
    st.markdown("**Internal Responsibility**")
    sales_rep_col, customer_service_col, _ = st.columns([1, 1, 1], gap="small")
    with sales_rep_col:
        render_key("partner_yb_employee_id")
    with customer_service_col:
        render_key("partner_yz_employee_id")

    st.divider()
    st.markdown("**Bill-to, Payer and Ship-to Party**")
    st.caption(
        "The current customer ID is shown by default. "
        "If another partner is required, select an existing partner and enter its ID, "
        "or select a new partner and enter the full address to be created."
    )

    party_groups = [
        (
            "Bill-to Party (BP)",
            "bill_to_party_mode",
            "bill_to_party_id",
            "bill_to_party_address",
        ),
        (
            "Payer (PY)",
            "payer_mode",
            "payer_id",
            "payer_address",
        ),
        (
            "Ship-to Party (SH)",
            "ship_to_party_mode",
            "ship_to_party_id",
            "ship_to_party_address",
        ),
    ]

    party_columns = st.columns(3)
    for column, (title, mode_key, id_key, address_key) in zip(
        party_columns, party_groups
    ):
        with column:
            st.markdown(f"##### {title}")
            mode = render_key(mode_key)

            if mode == "EXISTING_ID":
                render_key(id_key)
                values[address_key] = ""
            elif mode == "NEW_ADDRESS":
                render_key(address_key)
                values[id_key] = ""
            else:
                values[id_key] = ""
                values[address_key] = ""

    return values
