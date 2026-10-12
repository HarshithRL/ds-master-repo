from __future__ import annotations

import streamlit as st

from theme import apply_section_statuses, apply_theme

from portal.data import (
    get_customer_from_databricks,
    get_field_options,
    get_form_fields,
    get_original_defaults,
    load_assignment_rules,
    load_credit_rules,
    load_form_rules,
    load_reference_library,
)

from portal.notifications import submit_to_master_data

from portal.ui_business import (
    render_credit_management,
    render_partner_functions,
    render_section,
)

from portal.ui_common import (
    render_customer_information,
    render_section_comment,
)

from portal.ui_general import (
    render_attachments,
    render_bank_details_attachment,
    render_general_data_requests,
)

from portal.ui_layout import (
    render_header,
    render_request_details,
)

from portal.utils import (
    clean,
    format_option,
    reset_form_state,
)

from portal.validation import (
    build_section_statuses,
    collect_validation_errors,
    general_data_status,
)

from portal.ui_sidebar import render_sidebar


# =========================================================================
# PAGE
# =========================================================================

st.set_page_config(
    page_title="AXIOM | Master Data Management",
    page_icon="assets/axiom_icon.png",
    layout="wide",
)

apply_theme()


# =========================================================================
# LOAD CONFIGURATION
# =========================================================================

try:
    reference_library = load_reference_library()
    rules = load_form_rules()
    credit_rules = load_credit_rules()
    assignment_rules = load_assignment_rules()

except Exception as exc:
    st.error("The app could not load its configuration files.")
    st.exception(exc)
    st.stop()


# =========================================================================
# HEADER / CUSTOMER SEARCH
# =========================================================================

loaded_customer_id = clean(
    st.session_state.get(
        "loaded_customer_id",
        "",
    )
)

customer_id_input, load_customer_clicked = render_sidebar(
    loaded_customer_id=loaded_customer_id,
)

render_header(
    loaded_customer_id=loaded_customer_id,
    header_customer=None,
)


# =========================================================================
# CUSTOMER SEARCH
# =========================================================================

if load_customer_clicked:

    lookup_value = clean(customer_id_input)

    if not lookup_value:
        st.warning("Enter a SAP Customer ID.")

    else:
        try:
            with st.spinner(
                "Searching customer in Databricks..."
            ):
                customer_match = get_customer_from_databricks(
                    lookup_value,
                    reference_library,
                )

        except Exception as exc:
            st.error(
                "Databricks customer search failed."
            )
            st.exception(exc)
            st.stop()

        if customer_match is None:

            st.session_state.pop(
                "loaded_customer_id",
                None,
            )

            st.error(
                f"Customer {lookup_value} was not found in Databricks."
            )

        else:

            new_customer_id = clean(
                customer_match.get(
                    "customer_id",
                    lookup_value,
                )
            )

            st.session_state[
                "loaded_customer_id"
            ] = new_customer_id

            reset_form_state()

            st.rerun()


# =========================================================================
# CUSTOMER REQUIRED BEFORE FORM
# =========================================================================

loaded_customer_id = clean(
    st.session_state.get(
        "loaded_customer_id",
        "",
    )
)

if not loaded_customer_id:
    st.stop()


customer = get_customer_from_databricks(
    loaded_customer_id,
    reference_library,
)

if customer is None:

    st.error(
        "The selected customer no longer exists in Databricks."
    )

    st.stop()


# =========================================================================
# MAIN TWO-PANEL LAYOUT
# =========================================================================

left_panel, right_panel = st.columns(
    [1, 1.35],
    gap="large",
    vertical_alignment="top",
)


# =========================================================================
# LEFT SIDE
# =========================================================================

with left_panel:

    render_customer_information(
        customer,
        reference_library,
    )

    st.markdown(
        '<div style="height: 16px;"></div>',
        unsafe_allow_html=True,
    )

    request_tab = st.container(
        border=True,
    )

    with request_tab:

        (
            request_type,
            company_code,
            selected_sales_org,
            request_information_comment,
        ) = render_request_details(
            loaded_customer_id=loaded_customer_id,
            reference_library=reference_library,
        )


# =========================================================================
# SALES ORGANIZATION REQUIRED
# =========================================================================

if not selected_sales_org:

    if request_type != "Change Customer":

        general_tab = right_panel.expander(
            "General Data",
            expanded=False,
        )

        company_tab = right_panel.expander(
            "Company Code",
            expanded=False,
        )

        sales_tab = right_panel.expander(
            "Sales & Distribution",
            expanded=False,
        )

        partner_tab = right_panel.expander(
            "Partner Functions",
            expanded=False,
        )

        credit_tab = right_panel.expander(
            "Credit Management",
            expanded=False,
        )

        with general_tab:

            general_data_values = {}
            general_data_duplicates = []
            bank_attachments = []
            attachments = []
            bank_attachment_errors = []
            attachment_errors = []

            st.markdown(
                '<div class="prerequisite-note">'
                "Choose a Sales Organization in Request Details "
                "to configure this section."
                "</div>",
                unsafe_allow_html=True,
            )

        prerequisite_text = (
            "Choose a Sales Organization in Request Details "
            "to configure this section."
        )

        for waiting_tab in (
            company_tab,
            sales_tab,
            partner_tab,
            credit_tab,
        ):

            with waiting_tab:

                st.markdown(
                    (
                        '<div class="prerequisite-note">'
                        f"{prerequisite_text}"
                        "</div>"
                    ),
                    unsafe_allow_html=True,
                )

        apply_section_statuses(
            {
                "general_data": "neutral",
                "company_code": "neutral",
                "sales_distribution": "neutral",
                "partner_functions": "neutral",
                "credit_management": "neutral",
            }
        )

    st.stop()


# =========================================================================
# LOAD FIELDS FOR SELECTED BUSINESS CONTEXT
# =========================================================================

fields = get_form_fields(
    company_code=company_code,
    sales_org=selected_sales_org,
    rules=rules,
)

context = {
    "customer_id": loaded_customer_id,
    "company_code": company_code,
    "sales_organization": selected_sales_org,
}


# =========================================================================
# CHANGE CUSTOMER
# =========================================================================

if request_type == "Change Customer":

    selected_change_field = None
    selected_field_key = ""
    selected_field_label = ""
    selected_field_section = ""
    selected_input_type = ""
    requested_change_value = ""
    change_comment = ""

    with right_panel.container(
        border=True,
    ):

        st.markdown(
            "### Change Request"
        )

        # -----------------------------------------------------------------
        # AVAILABLE CHANGE FIELDS
        # -----------------------------------------------------------------

        change_fields = fields.copy()

        # Hidden fields are not directly requestable.
        change_fields = change_fields[
            ~change_fields[
                "hidden"
            ]
            .astype(str)
            .str.strip()
            .str.upper()
            .isin(
                {
                    "Y",
                    "YES",
                    "TRUE",
                    "1",
                    "X",
                }
            )
        ].copy()

        # Computed fields should be changed through
        # their source field instead.
        change_fields = change_fields[
            ~change_fields[
                "input_type"
            ]
            .astype(str)
            .str.strip()
            .str.lower()
            .eq("computed")
        ].copy()

        field_records = (
            change_fields.to_dict(
                "records"
            )
        )

        # -----------------------------------------------------------------
        # FIELD TO CHANGE
        # -----------------------------------------------------------------

        selected_change_field = st.selectbox(
            "Field to Change *",
            options=[
                None,
                *field_records,
            ],
            format_func=lambda field: (
                ""
                if field is None
                else (
                    f"{clean(field.get('label'))} "
                    f"({clean(field.get('section'))})"
                )
            ),
            key="change__field",
        )

        # -----------------------------------------------------------------
        # SELECTED FIELD
        # -----------------------------------------------------------------

        if selected_change_field:

            selected_field_key = clean(
                selected_change_field.get(
                    "field_key"
                )
            )

            selected_field_label = clean(
                selected_change_field.get(
                    "label"
                )
            )

            selected_field_section = clean(
                selected_change_field.get(
                    "section"
                )
            )

            selected_input_type = clean(
                selected_change_field.get(
                    "input_type"
                )
            ).lower()

            max_length = (
                selected_change_field.get(
                    "max_length"
                )
            )

            try:
                max_length = int(
                    float(
                        max_length
                    )
                )

            except (
                TypeError,
                ValueError,
            ):
                max_length = None

            st.caption(
                f"Section: {selected_field_section}"
            )

            # -------------------------------------------------------------
            # OPTIONS FOR SELECTED BUSINESS CONTEXT
            # -------------------------------------------------------------

            option_rows = get_field_options(
                field_key=selected_field_key,
                company_code=company_code,
                sales_org=selected_sales_org,
                rules=rules,
            )

            value_widget_key = (
                "change__requested_value__"
                f"{selected_field_key}"
            )

            # -------------------------------------------------------------
            # SELECT
            # -------------------------------------------------------------

            if selected_input_type in {
                "select",
                "dropdown",
                "selectbox",
            }:

                option_values = [
                    clean(
                        option.get(
                            "value"
                        )
                    )
                    for option in option_rows
                    if clean(
                        option.get(
                            "value"
                        )
                    )
                ]

                descriptions = {
                    clean(
                        option.get(
                            "value"
                        )
                    ): clean(
                        option.get(
                            "description"
                        )
                    )
                    for option in option_rows
                    if clean(
                        option.get(
                            "value"
                        )
                    )
                }

                option_values = list(
                    dict.fromkeys(
                        option_values
                    )
                )

                if option_values:

                    requested_change_value = st.selectbox(
                        "Requested Value *",
                        options=[
                            "",
                            *option_values,
                        ],
                        key=value_widget_key,
                        format_func=lambda code: (
                            ""
                            if not code
                            else format_option(
                                code,
                                descriptions.get(
                                    code,
                                    "",
                                ),
                            )
                        ),
                    )

                else:

                    st.warning(
                        "No active values are configured for this "
                        "field, Company Code and Sales Organization."
                    )

                    requested_change_value = st.text_input(
                        "Requested Value *",
                        key=value_widget_key,
                        max_chars=max_length,
                    )

            # -------------------------------------------------------------
            # TEXTAREA
            # -------------------------------------------------------------

            elif selected_input_type in {
                "textarea",
                "text_area",
            }:

                requested_change_value = st.text_area(
                    "Requested Value *",
                    key=value_widget_key,
                    max_chars=max_length,
                )

            # -------------------------------------------------------------
            # READONLY
            # -------------------------------------------------------------

            elif selected_input_type == "readonly":

                st.info(
                    "This field is read-only in the current "
                    "configuration."
                )

            # -------------------------------------------------------------
            # TEXT
            # -------------------------------------------------------------

            else:

                requested_change_value = st.text_input(
                    "Requested Value *",
                    key=value_widget_key,
                    max_chars=max_length,
                )

        # -----------------------------------------------------------------
        # COMMENT
        # -----------------------------------------------------------------

        change_comment = st.text_area(
            "Comment *",
            key="change__comment",
            placeholder=(
                "Explain what should be changed and, "
                "if relevant, why the change is required."
            ),
            height=110,
        )


    # =========================================================================
    # CHANGE CUSTOMER PAYLOAD
    # =========================================================================

    change_payload = {
        "request_information": {
            "request_type": request_type,
            "customer_id": loaded_customer_id,
            "company_code": company_code,
            "sales_org": selected_sales_org,
        },
        "existing_customer": customer,
        "change_request": {
            "section": selected_field_section,
            "field_key": selected_field_key,
            "field_label": selected_field_label,
            "requested_value": clean(
                requested_change_value
            ),
            "comment": clean(
                change_comment
            ),
        },
        "section_comments": {
            "request_information": (
                request_information_comment
            ),
            "change_customer": clean(
                change_comment
            ),
        },
        "attachments": [],
    }


    # =========================================================================
    # CHANGE CUSTOMER ACTIONS
    # =========================================================================

    action_container = right_panel.container()

    with action_container:

        save_col, submit_col = st.columns(
            [1, 2],
            gap="small",
        )

        with save_col:

            st.button(
                "Save Draft",
                use_container_width=True,
                key="change__save_draft",
                disabled=True,
                help=(
                    "Save Draft functionality "
                    "is coming soon."
                ),
            )

        with submit_col:

            submit_change_clicked = st.button(
                "Submit to Master Data",
                use_container_width=True,
                key="change__submit",
                type="primary",
            )


    # =========================================================================
    # CHANGE CUSTOMER SUBMIT
    # =========================================================================

    if submit_change_clicked:

        change_errors = []

        if not selected_change_field:

            change_errors.append(
                "Select the field that should be changed."
            )

        elif selected_input_type == "readonly":

            change_errors.append(
                "The selected field is read-only and "
                "cannot be changed."
            )

        elif not clean(
            requested_change_value
        ):

            change_errors.append(
                "Enter or select the requested value."
            )

        if not clean(
            change_comment
        ):

            change_errors.append(
                "Enter a comment explaining the requested change."
            )

        if change_errors:

            for message in change_errors:
                st.error(
                    message
                )

        else:

            # For Change Customer there is no existing
            # full-form default comparison.
            change_original_defaults = {
                "Change Customer": {
                    selected_field_key: ""
                }
            }

            try:

                with st.spinner(
                    "Sending request notification..."
                ):

                    submission = submit_to_master_data(
                        payload=change_payload,
                        original_defaults=change_original_defaults,
                        assignment_rules=assignment_rules,
                    )

                request_id = submission[
                    "request_id"
                ]

                st.session_state[
                    "last_submitted_request_id"
                ] = request_id

                st.success(
                    f"Request reference {request_id} "
                    f"was created and assigned to "
                    f"{submission['assigned_to']}."
                )

                if submission["teams_sent"]:

                    st.caption(
                        "Notification flow triggered: "
                        "the assignee can receive a Teams message "
                        "and the requester can receive an Outlook "
                        "confirmation."
                    )

                else:

                    st.warning(
                        "The request reference was created, "
                        "but the notification flow URL is not configured."
                    )

            except Exception as exc:

                st.error(
                    "The notification could not be sent."
                )

                st.exception(
                    exc
                )


    if st.session_state.get(
        "last_submitted_request_id"
    ):

        st.caption(
            "Last request reference: "
            + st.session_state[
                "last_submitted_request_id"
            ]
        )


# =========================================================================
# CREATE / EXTEND CUSTOMER
# =========================================================================

else:

    # =========================================================================
    # STANDARD REQUEST SECTIONS
    # =========================================================================

    general_tab = right_panel.expander(
        "General Data",
        expanded=False,
    )

    company_tab = right_panel.expander(
        "Company Code",
        expanded=False,
    )

    sales_tab = right_panel.expander(
        "Sales & Distribution",
        expanded=False,
    )

    partner_tab = right_panel.expander(
        "Partner Functions",
        expanded=False,
    )

    credit_tab = right_panel.expander(
        "Credit Management",
        expanded=False,
    )


    # =========================================================================
    # GENERAL DATA
    # =========================================================================

    with general_tab:

        (
            general_data_values,
            general_data_duplicates,
            bank_details_required,
        ) = render_general_data_requests(
            customer=customer,
            reference_library=reference_library,
        )

        (
            bank_attachments,
            bank_attachment_errors,
        ) = render_bank_details_attachment(
            bank_details_required
        )

        (
            attachments,
            attachment_errors,
        ) = render_attachments()

        general_data_comment = render_section_comment(
            "general_data"
        )


    # =========================================================================
    # BUSINESS FIELD GROUPS
    # =========================================================================

    company_fields = fields[
        fields[
            "section"
        ]
        .astype(str)
        .str.strip()
        .eq(
            "Company Code"
        )
    ]

    sales_fields = fields[
        fields[
            "section"
        ]
        .astype(str)
        .str.strip()
        .eq(
            "Sales & Distribution"
        )
    ]

    partner_fields = fields[
        fields[
            "section"
        ]
        .astype(str)
        .str.strip()
        .eq(
            "Partner Functions"
        )
    ]


    # =========================================================================
    # COMPANY CODE
    # =========================================================================

    with company_tab:

        company_values = render_section(
            section_name="Company Code",
            section_fields=company_fields,
            company_code=company_code,
            sales_org=selected_sales_org,
            rules=rules,
            context=context,
        )

        company_comment = render_section_comment(
            "company_code"
        )


    # =========================================================================
    # SALES & DISTRIBUTION
    # =========================================================================

    with sales_tab:

        sales_values = render_section(
            section_name="Sales & Distribution",
            section_fields=sales_fields,
            company_code=company_code,
            sales_org=selected_sales_org,
            rules=rules,
            context=context,
        )

        sales_comment = render_section_comment(
            "sales_distribution"
        )


    # =========================================================================
    # PARTNER FUNCTIONS
    # =========================================================================

    with partner_tab:

        partner_values = render_partner_functions(
            section_fields=partner_fields,
            company_code=company_code,
            sales_org=selected_sales_org,
            rules=rules,
            context=context,
        )

        partner_comment = render_section_comment(
            "partner_functions"
        )


    # =========================================================================
    # CREDIT MANAGEMENT
    # =========================================================================

    with credit_tab:

        (
            credit_values,
            credit_defaults,
            credit_fields,
            credit_mapping,
        ) = render_credit_management(
            company_code=company_code,
            sales_org=selected_sales_org,
            customer=customer,
            credit_rules=credit_rules,
        )

        credit_comment = render_section_comment(
            "credit_management"
        )


    # =========================================================================
    # COMPUTED COMPANY CODE VALUES
    # =========================================================================

    for _, row in company_fields.iterrows():

        field = row.to_dict()

        if (
            clean(
                field.get(
                    "input_type"
                )
            ).lower()
            != "computed"
        ):
            continue

        field_key = clean(
            field.get(
                "field_key"
            )
        )

        copy_from = clean(
            field.get(
                "copy_from_field"
            )
        )

        company_values[
            field_key
        ] = clean(
            sales_values.get(
                copy_from
            )
        )


    # =========================================================================
    # ORIGINAL DEFAULTS
    # =========================================================================

    original_defaults = get_original_defaults(
        fields=fields,
        company_code=company_code,
        sales_org=selected_sales_org,
        rules=rules,
        context=context,
    )

    company_defaults = original_defaults.get(
        "Company Code",
        {},
    )

    sales_defaults = original_defaults.get(
        "Sales & Distribution",
        {},
    )

    for _, row in company_fields.iterrows():

        field = row.to_dict()

        if (
            clean(
                field.get(
                    "input_type"
                )
            ).lower()
            != "computed"
        ):
            continue

        field_key = clean(
            field.get(
                "field_key"
            )
        )

        copy_from = clean(
            field.get(
                "copy_from_field"
            )
        )

        company_defaults[
            field_key
        ] = clean(
            sales_defaults.get(
                copy_from
            )
        )

    original_defaults[
        "Credit Management"
    ] = credit_defaults


    # =========================================================================
    # SECTION COMMENTS
    # =========================================================================

    section_comments = {
        "request_information": (
            request_information_comment
        ),
        "general_data": (
            general_data_comment
        ),
        "company_code": (
            company_comment
        ),
        "sales_distribution": (
            sales_comment
        ),
        "partner_functions": (
            partner_comment
        ),
        "credit_management": (
            credit_comment
        ),
    }


    # =========================================================================
    # REQUEST PAYLOAD
    # =========================================================================

    payload = {
        "request_information": {
            "request_type": request_type,
            "customer_id": loaded_customer_id,
            "company_code": company_code,
            "sales_org": selected_sales_org,
        },
        "general_data": general_data_values,
        "existing_customer": customer,
        "company_code": company_values,
        "sales_distribution": sales_values,
        "partner_functions": partner_values,
        "credit_management": credit_values,
        "section_comments": section_comments,
        "attachments": (
            bank_attachments
            + attachments
        ),
        "credit_management_context": {
            "company_code": company_code,
            "ps4": (
                credit_mapping.get(
                    "ps4",
                    "",
                )
                if credit_mapping
                else ""
            ),
            "mapping_id": (
                credit_mapping.get(
                    "mapping_id",
                    "",
                )
                if credit_mapping
                else ""
            ),
            "company_name": (
                credit_mapping.get(
                    "company_name",
                    "",
                )
                if credit_mapping
                else ""
            ),
        },
    }


    # =========================================================================
    # LIVE SECTION STATUS
    # =========================================================================

    section_statuses = build_section_statuses(
        general_data_values=general_data_values,
        general_data_duplicates=general_data_duplicates,
        bank_attachments=bank_attachments,
        attachments=attachments,
        bank_attachment_errors=bank_attachment_errors,
        attachment_errors=attachment_errors,
        company_fields=company_fields,
        company_values=company_values,
        sales_fields=sales_fields,
        sales_values=sales_values,
        partner_fields=partner_fields,
        partner_values=partner_values,
        credit_fields=credit_fields,
        credit_values=credit_values,
        submit_attempted=bool(
            st.session_state.get(
                "_submit_attempted",
                False,
            )
        ),
    )

    apply_section_statuses(
        section_statuses
    )


    # =========================================================================
    # SAVE DRAFT / SUBMIT
    # =========================================================================

    action_container = right_panel.container()

    with action_container:

        save_col, submit_col = st.columns(
            [1, 2],
            gap="small",
        )

        with save_col:

            st.button(
                "Save Draft",
                use_container_width=True,
                key="request__save_draft",
                disabled=True,
                help=(
                    "Save Draft functionality "
                    "is coming soon."
                ),
            )

        with submit_col:

            submit_clicked = st.button(
                "Submit to Master Data",
                use_container_width=True,
                key="request__submit",
                type="primary",
            )


    # =========================================================================
    # STANDARD REQUEST SUBMIT
    # =========================================================================

    if submit_clicked:

        st.session_state[
            "_submit_attempted"
        ] = True

        validation_errors = collect_validation_errors(
            fields=fields,
            company_values=company_values,
            sales_values=sales_values,
            partner_values=partner_values,
            credit_fields=credit_fields,
            credit_values=credit_values,
            general_data_values=general_data_values,
            general_data_duplicates=general_data_duplicates,
            attachment_errors=attachment_errors,
            bank_attachment_errors=bank_attachment_errors,
        )

        if validation_errors:

            for message in validation_errors:

                st.error(
                    message
                )

        else:

            st.session_state[
                "_submit_attempted"
            ] = False

            try:

                with st.spinner(
                    "Sending request notification..."
                ):

                    submission = submit_to_master_data(
                        payload=payload,
                        original_defaults=original_defaults,
                        assignment_rules=assignment_rules,
                    )

                request_id = submission[
                    "request_id"
                ]

                st.session_state[
                    "last_submitted_request_id"
                ] = request_id

                st.success(
                    f"Request reference {request_id} "
                    f"was created and assigned to "
                    f"{submission['assigned_to']}."
                )

                if submission[
                    "teams_sent"
                ]:

                    st.caption(
                        "Notification flow triggered: "
                        "the assignee can receive a Teams message "
                        "and the requester can receive an Outlook "
                        "confirmation."
                    )

                else:

                    st.warning(
                        "The request reference was created, "
                        "but the notification flow URL is not configured."
                    )

            except Exception as exc:

                st.error(
                    "The notification could not be sent."
                )

                st.exception(
                    exc
                )


    if st.session_state.get(
        "last_submitted_request_id"
    ):

        st.caption(
            "Last request reference: "
            + st.session_state[
                "last_submitted_request_id"
            ]
        )