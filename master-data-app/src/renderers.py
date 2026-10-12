from __future__ import annotations

from typing import Any
import base64

import pandas as pd
import streamlit as st

from config import MAX_ATTACHMENT_SIZE_BYTES, MAX_ATTACHMENTS_TOTAL_BYTES
from helpers import clean, is_yes, active_rows, as_int, format_option

from data_access import (
    get_field_options,
    find_default,
    get_credit_fields,
    get_credit_mapping,
    get_credit_initial_value,
    get_requestable_general_data_fields,
    get_display_general_data_fields,
)

# =============================================================================
# HEADER
# =============================================================================


def render_header() -> None:
    """Dark branded header bar at the top of the page."""
    st.markdown(
        """
        <div class="etex-header">
            <h1>Customer Request Portal</h1>
            <p>Customer master data request</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


# =============================================================================
# CUSTOMER INFO TABLE (label-value HTML table)
# =============================================================================


def render_customer_info_table(
    customer: dict[str, str],
    reference_library: dict[str, pd.DataFrame],
) -> None:
    """Render configured customer information as a clean HTML table."""
    import html as html_mod

    display_fields = get_display_general_data_fields(
        reference_library=reference_library,
    )

    rows_html: list[str] = []

    for _, config in display_fields.iterrows():
        field_key = clean(config.get("field_key"))

        label = clean(config.get("label")) or field_key

        source_field = clean(config.get("customer_source_field")) or field_key

        value = clean(customer.get(source_field, ""))

        display_value = html_mod.escape(value) if value else "—"

        rows_html.append(
            f"<tr>"
            f"<td>{html_mod.escape(label)}</td>"
            f"<td>{display_value}</td>"
            f"</tr>"
        )

    if not rows_html:
        st.info("No customer display fields configured.")
        return

    st.markdown("**Existing Customer Information**")

    st.markdown(
        '<table class="customer-info-table">' + "".join(rows_html) + "</table>",
        unsafe_allow_html=True,
    )


# =============================================================================
# SECTION STATUS HELPERS
# =============================================================================


def check_section_complete(
    section_fields: pd.DataFrame,
    values: dict[str, str],
) -> bool:
    """Return True if every required visible field has a value."""
    for _, row in section_fields.iterrows():
        field = row.to_dict()
        if not is_yes(field.get("required")):
            continue
        if is_yes(field.get("hidden")):
            continue
        field_key = clean(field.get("field_key"))
        if not clean(values.get(field_key, "")):
            return False
    return True


def section_card_open(
    status: str,
) -> None:
    """Legacy hook kept for compatibility; layout is handled in CSS."""
    _ = status
    return None


def section_card_close() -> None:
    """Legacy hook kept for compatibility; layout is handled in CSS."""
    return None


# =============================================================================
# DYNAMIC FORM RENDERER
# =============================================================================


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
            st.text_input(
                label_with_required,
                value=value,
                disabled=True,
                key=f"form__{field_key}",
                help=notes or None,
            )

        return value

    if input_type == "computed":
        copy_from = clean(field.get("copy_from_field"))

        value = clean(
            st.session_state.get(
                f"form__{copy_from}",
                "",
            )
        )

        if not hidden:
            st.text_input(
                label_with_required,
                value=value,
                disabled=True,
                key=f"computed_display__{field_key}",
                help=notes or None,
            )

        return value

    option_rows = get_field_options(
        field_key=field_key,
        company_code=company_code,
        sales_org=sales_org,
        rules=rules,
    )

    default_value = find_default(
        field,
        option_rows,
    )

    widget_key = f"form__{field_key}"

    if hidden:
        return default_value

    if input_type == "select":
        values = [option["value"] for option in option_rows if option["value"]]

        descriptions = {
            option["value"]: option["description"] for option in option_rows
        }

        if not values:
            return st.text_input(
                label_with_required,
                value=default_value,
                key=widget_key,
                disabled=not editable,
                max_chars=max_length,
                help=notes or None,
            )

        options = list(dict.fromkeys(values))

        if not required:
            options = [""] + options

        current_value = clean(
            st.session_state.get(
                widget_key,
                default_value,
            )
        )

        if current_value and current_value not in options:
            options.insert(
                0,
                current_value,
            )

        if current_value in options:
            index = options.index(current_value)
        elif default_value in options:
            index = options.index(default_value)
        else:
            index = 0

        return st.selectbox(
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
                        descriptions.get(
                            code,
                            "",
                        ),
                    )
                )
            ),
            help=notes or None,
        )

    if input_type == "textarea":
        return st.text_area(
            label_with_required,
            value=default_value,
            key=widget_key,
            disabled=not editable,
            height=110,
            max_chars=max_length,
            help=notes or None,
        )

    return st.text_input(
        label_with_required,
        value=default_value,
        key=widget_key,
        disabled=not editable,
        max_chars=max_length,
        help=notes or None,
    )


def render_section(
    *,
    section_name: str,
    section_fields: pd.DataFrame,
    company_code: str,
    sales_org: str,
    rules: dict[str, pd.DataFrame],
    context: dict[str, str],
) -> dict[str, str]:
    st.subheader(section_name)

    values: dict[str, str] = {}

    if section_fields.empty:
        st.info("No active fields are configured for this section.")
        return values

    columns = st.columns(3)
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
    st.subheader("Partner Functions")
    st.caption(
        "Financial Contact (YF), Contact Person (CP) and Logistics Contact (YL) "
        "use email addresses. Enter the contact name as well for CP and YL. "
        "Sales Rep (YB) and CC Person (YZ) use existing Salesforce employee IDs."
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

    st.markdown("**Contact partner functions**")

    email_cols = st.columns(3)
    for column, field_key in zip(
        email_cols,
        [
            "partner_yf_email",
            "partner_cp_email",
            "partner_yl_email",
        ],
    ):
        with column:
            render_key(field_key)

    name_cols = st.columns(2)

    with name_cols[0]:
        values["partner_cp_name"] = clean(
            st.text_input(
                "Contact Person Name (CP)",
                key="form__partner_cp_name",
                max_chars=120,
            )
        )

    with name_cols[1]:
        values["partner_yl_name"] = clean(
            st.text_input(
                "Logistics Contact Name (YL)",
                key="form__partner_yl_name",
                max_chars=120,
            )
        )

    employee_cols = st.columns(2)
    for column, field_key in zip(
        employee_cols,
        [
            "partner_yb_employee_id",
            "partner_yz_employee_id",
        ],
    ):
        with column:
            render_key(field_key)

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

    for column, (title, mode_key, id_key, address_key,) in zip(
        party_columns,
        party_groups,
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


def render_section_comment(
    section_key: str,
) -> str:
    st.markdown("**Comments / additional instructions**")

    return clean(
        st.text_area(
            "Comments / additional instructions",
            key=(f"section_comment__" f"{section_key}"),
            height=70,
            label_visibility="collapsed",
            placeholder=("Optional comments for Master Data..."),
        )
    )


def get_country_tax_labels(
    country: str,
    reference_library: dict[str, pd.DataFrame],
) -> dict[str, str]:
    tax_df = reference_library.get(
        "tax_details",
        pd.DataFrame(),
    ).copy()

    if tax_df.empty:
        return {}

    tax_df.columns = [str(col).strip() for col in tax_df.columns]

    if "cust_country" not in tax_df.columns:
        return {}

    country = clean(country).upper()

    if not country:
        return {}

    matches = tax_df[
        tax_df["cust_country"].astype(str).str.strip().str.upper().eq(country)
    ]

    if matches.empty:
        return {}

    row = matches.iloc[0]

    result: dict[str, str] = {}

    for number in range(1, 7):
        field_key = f"tax_number_{number}"

        if field_key not in row.index:
            continue

        label = clean(row.get(field_key))

        if label:
            result[field_key] = label

    return result


def render_general_data_requests(
    *,
    customer: dict[str, str],
    reference_library: dict[str, pd.DataFrame],
) -> tuple[dict[str, dict[str, str]], list[str],]:
    st.subheader("General Data Request")

    st.caption(
        "Add only the General Data fields you need. "
        "Select a field, review its current value, "
        "then enter the requested new value."
    )

    # -------------------------------------------------------------------------
    # LOAD GENERAL DATA FIELD CONFIGURATION
    # -------------------------------------------------------------------------

    field_library = get_requestable_general_data_fields(
        country=clean(
            customer.get(
                "country",
                "",
            )
        ),
        reference_library=reference_library,
    )

    field_records: dict[str, dict[str, Any],] = {
        clean(row.get("field_key")): row
        for row in field_library.to_dict("records")
        if clean(row.get("field_key"))
    }

    field_keys = list(field_records.keys())

    tax_field_keys = {f"tax_number_{number}" for number in range(1, 7)}

    # -------------------------------------------------------------------------
    # ROW COUNT
    # -------------------------------------------------------------------------

    count_key = "general_data__row_count"

    if count_key not in st.session_state:
        st.session_state[count_key] = 0

    controls = st.columns([1, 1, 4])

    with controls[0]:
        if st.button(
            "＋ Add field",
            key=("general_data__add"),
            use_container_width=True,
        ):
            st.session_state[count_key] = min(
                int(st.session_state[count_key]) + 1,
                20,
            )

    with controls[1]:
        if st.button(
            "− Remove last",
            key=("general_data__remove"),
            use_container_width=True,
            disabled=(int(st.session_state[count_key]) <= 0),
        ):
            last_index = int(st.session_state[count_key]) - 1

            for key in list(st.session_state.keys()):
                if (
                    key == ("general_data__field__" f"{last_index}")
                    or key.startswith("general_data__value__" f"{last_index}__")
                    or key.startswith("general_data__current__" f"{last_index}__")
                ):
                    del st.session_state[key]

            st.session_state[count_key] = max(
                last_index,
                0,
            )

    row_count = int(st.session_state[count_key])

    if row_count == 0:
        st.info("No General Data changes added.")

    # -------------------------------------------------------------------------
    # RENDER REQUEST ROWS
    # -------------------------------------------------------------------------

    results: dict[
        str,
        dict[str, str],
    ] = {}

    selected_keys: list[str] = []

    for index in range(row_count):
        columns = st.columns([1.25, 1, 1.5])

        with columns[0]:
            selected_key = st.selectbox(
                "General Data field",
                options=([""] + field_keys),
                key=("general_data__field__" f"{index}"),
                format_func=lambda key: (
                    "Select field..."
                    if not key
                    else (clean(field_records[key].get("label")) or key)
                ),
            )

        if not selected_key:
            with columns[1]:
                st.text_input(
                    "Current value",
                    value="",
                    disabled=True,
                    key=("general_data__empty_current__" f"{index}"),
                )

            with columns[2]:
                st.text_input(
                    "Requested value",
                    value="",
                    disabled=True,
                    key=("general_data__empty_value__" f"{index}"),
                )

            continue

        selected_keys.append(selected_key)

        config = field_records[selected_key]

        label = clean(config.get("label")) or selected_key

        source_field = clean(config.get("customer_source_field"))

        # First use configured customer_source_field.
        current_value = (
            clean(
                customer.get(
                    source_field,
                    "",
                )
            )
            if source_field
            else ""
        )

        # For tax fields we can also use the same field_key
        # directly if the customer data contains tax_number_1,
        # tax_number_2, etc.
        if not current_value and selected_key in tax_field_keys:
            current_value = clean(customer.get(selected_key, ""))

        with columns[1]:
            st.text_input(
                "Current value",
                value=(current_value or "—"),
                disabled=True,
                key=("general_data__current__" f"{index}__" f"{selected_key}"),
            )

        max_length = as_int(config.get("max_length"))

        input_type = clean(config.get("input_type")).lower() or "text"

        with columns[2]:
            if input_type == "textarea":
                requested_value = st.text_area(
                    "Requested value",
                    key=("general_data__value__" f"{index}__" f"{selected_key}"),
                    max_chars=(max_length),
                    height=90,
                )
            else:
                requested_value = st.text_input(
                    "Requested value",
                    key=("general_data__value__" f"{index}__" f"{selected_key}"),
                    max_chars=(max_length),
                )

        results[selected_key] = {
            "field_key": selected_key,
            "label": label,
            "sap_field": clean(config.get("sap_field")),
            "current_value": current_value,
            "requested_value": clean(requested_value),
        }

    # -------------------------------------------------------------------------
    # DUPLICATE VALIDATION
    # -------------------------------------------------------------------------

    duplicate_labels: list[str] = []

    seen_fields: set[str] = set()

    for field_key in selected_keys:
        if field_key in seen_fields:
            duplicate_labels.append(
                clean(field_records[field_key].get("label")) or field_key
            )

        seen_fields.add(field_key)

    return (
        results,
        duplicate_labels,
    )


def render_attachments() -> tuple[
    list[dict[str, Any]],
    list[str],
]:
    st.markdown("**Attachments**")

    uploaded_files = st.file_uploader(
        "Supporting documents or images",
        type=[
            "pdf",
            "png",
            "jpg",
            "jpeg",
            "doc",
            "docx",
            "xls",
            "xlsx",
            "csv",
            "txt",
        ],
        accept_multiple_files=True,
        key=("general_data__attachments"),
        help=(
            "Examples: bank-account confirmation, "
            "signed documents or supporting images. "
            "Maximum 3 MB per file and 5 MB total."
        ),
    )

    attachments: list[dict[str, Any]] = []

    errors: list[str] = []
    total_size = 0

    for uploaded_file in uploaded_files or []:
        file_bytes = uploaded_file.getvalue()

        file_size = len(file_bytes)

        total_size += file_size

        if file_size > MAX_ATTACHMENT_SIZE_BYTES:
            errors.append(f"{uploaded_file.name} " "is larger than 3 MB.")
            continue

        attachments.append(
            {
                "name": clean(uploaded_file.name),
                "mime_type": clean(uploaded_file.type),
                "size_bytes": file_size,
                "content_base64": base64.b64encode(file_bytes).decode("ascii"),
            }
        )

    if total_size > MAX_ATTACHMENTS_TOTAL_BYTES:
        errors.append("The total attachment size " "is larger than 5 MB.")

    if uploaded_files:
        st.caption(
            "Attached: " + ", ".join(clean(file.name) for file in uploaded_files)
        )

    return (
        attachments,
        errors,
    )


# =============================================================================
# REVIEW RENDERERS
# =============================================================================


def render_review_field_grid(
    *,
    section_key: str,
    section_title: str,
    section_fields: pd.DataFrame,
    values: dict[str, str],
    comment: str = "",
    only_nonempty: bool = False,
    customer_id: str = "",
) -> None:
    st.markdown(f"### {section_title}")

    review_rows: list[tuple[str, str, str]] = []

    for _, row in section_fields.iterrows():
        field = row.to_dict()

        if is_yes(field.get("hidden")):
            continue

        field_key = clean(field.get("field_key"))

        if not field_key:
            continue

        label = clean(field.get("label")) or field_key

        if section_key == "partner_functions":
            partner_review_labels = {
                "partner_yf_email": "Financial Contact Email (YF)",
                "partner_cp_email": "Contact Person Email (CP)",
                "partner_yl_email": "Logistics Contact Email (YL)",
                "partner_yb_employee_id": "Sales Rep Employee ID (YB)",
                "partner_yz_employee_id": "CC Person Employee ID (YZ)",
                "bill_to_party_mode": "Bill-to Party (BP)",
                "payer_mode": "Payer (PY)",
                "ship_to_party_mode": "Ship-to Party (SH)",
            }
            label = partner_review_labels.get(
                field_key,
                label,
            )

        value = clean(
            values.get(
                field_key,
                "",
            )
        )

        if (
            section_key == "partner_functions"
            and field_key
            in {
                "bill_to_party_mode",
                "payer_mode",
                "ship_to_party_mode",
            }
            and value == "SAME_AS_CUSTOMER"
            and clean(customer_id)
        ):
            value = clean(customer_id)

        if only_nonempty and not value:
            continue

        review_rows.append(
            (
                field_key,
                label,
                value,
            )
        )

    if section_key == "partner_functions":
        for extra_key, extra_label in [
            (
                "partner_cp_name",
                "Contact Person Name (CP)",
            ),
            (
                "partner_yl_name",
                "Logistics Contact Name (YL)",
            ),
        ]:
            extra_value = clean(
                values.get(
                    extra_key,
                    "",
                )
            )

            if only_nonempty and not extra_value:
                continue

            review_rows.append(
                (
                    extra_key,
                    extra_label,
                    extra_value,
                )
            )

    if not review_rows:
        st.caption("No values entered in this section.")
    else:
        columns = st.columns(3)

        for index, (
            field_key,
            label,
            value,
        ) in enumerate(review_rows):
            with columns[index % 3]:
                st.text_input(
                    label,
                    value=(value or "\u2014"),
                    disabled=True,
                    key=("review__" f"{section_key}__" f"{field_key}"),
                )

    if clean(comment):
        st.text_area(
            "Comments / additional instructions",
            value=clean(comment),
            disabled=True,
            height=75,
            key=("review__comment__" f"{section_key}"),
        )


def render_review_general_data(
    general_data_values: dict[
        str,
        dict[str, str],
    ],
    *,
    comment: str = "",
) -> None:
    st.markdown("### General Data")

    if not general_data_values:
        st.caption("No General Data changes requested.")
    else:
        for index, item in enumerate(general_data_values.values()):
            if not isinstance(
                item,
                dict,
            ):
                continue

            label = (
                clean(item.get("label"))
                or clean(item.get("field_key"))
                or "General Data field"
            )

            columns = st.columns([1.2, 1, 1.2])

            with columns[0]:
                st.text_input(
                    "Field",
                    value=label,
                    disabled=True,
                    key=("review__general_field__" f"{index}"),
                )

            with columns[1]:
                st.text_input(
                    "Current value",
                    value=(clean(item.get("current_value")) or "\u2014"),
                    disabled=True,
                    key=("review__general_current__" f"{index}"),
                )

            with columns[2]:
                st.text_input(
                    "Requested value",
                    value=(clean(item.get("requested_value")) or "\u2014"),
                    disabled=True,
                    key=("review__general_requested__" f"{index}"),
                )

    if clean(comment):
        st.text_area(
            "Comments / additional instructions",
            value=clean(comment),
            disabled=True,
            height=75,
            key="review__comment__general_data",
        )


# =============================================================================
# CREDIT MANAGEMENT RENDERER
# =============================================================================


def render_credit_management(
    *,
    company_code: str,
    sales_org: str,
    customer: dict[str, str],
    credit_rules: dict[str, pd.DataFrame],
) -> tuple[dict[str, str], dict[str, str], pd.DataFrame, dict[str, str] | None,]:
    st.subheader("Credit Management")

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
            f"{mapping.get('company_name', '')} \u00b7 "
            f"Company Code {company_code}"
        )

    values: dict[str, str] = {}
    defaults: dict[str, str] = {}

    columns = st.columns(3)
    visible_index = 0

    for _, row in fields.iterrows():
        field = row.to_dict()

        field_key = clean(field.get("field_key"))

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

        with columns[visible_index % 3]:
            if input_type == "readonly":
                value = st.text_input(
                    display_label,
                    value=initial_value,
                    disabled=True,
                    key=widget_key,
                    help=notes or None,
                )
            else:
                value = st.text_input(
                    display_label,
                    value=initial_value,
                    disabled=not editable,
                    key=widget_key,
                    help=notes or None,
                )

        values[field_key] = clean(value)

        visible_index += 1

    return (
        values,
        defaults,
        fields,
        mapping,
    )


# =============================================================================
# DEFAULTS
# =============================================================================


def get_original_defaults(
    *,
    fields: pd.DataFrame,
    company_code: str,
    sales_org: str,
    rules: dict[str, pd.DataFrame],
    context: dict[str, str],
) -> dict[str, dict[str, str]]:
    result: dict[
        str,
        dict[str, str],
    ] = {}

    for _, row in fields.iterrows():
        field = row.to_dict()

        section = clean(field.get("section"))

        field_key = clean(field.get("field_key"))

        input_type = clean(field.get("input_type")).lower()

        if section not in result:
            result[section] = {}

        if input_type == "readonly":
            value = clean(context.get(field_key))
        elif input_type == "computed":
            value = ""
        else:
            options = get_field_options(
                field_key=field_key,
                company_code=company_code,
                sales_org=sales_org,
                rules=rules,
            )

            value = find_default(
                field,
                options,
            )

        result[section][field_key] = value

    return result
