"""Credit Management rules from credit_management_rules.xlsx."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from portal.constants import COLLECTION_CONTACT_KEYS, CREDIT_MANAGEMENT
from portal.core.utils import (
    active_rows,
    clean,
    column_text,
    flagged_rows,
    is_yes,
    sort_by_display_order,
)

FieldRecord = dict[str, Any]

COLLECTION_CONTACT_NOTE = (
    "Individual or department to contact regarding outstanding invoices, "
    "payment issues and collection-related enquiries"
)

# =============================================================================
# FIELDS AND MAPPING
# =============================================================================


def get_credit_fields(
    credit_rules: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """
    Visible, active credit fields sorted by display_order.

    A legacy single "collection_contact" row is replaced by separate
    name / email / phone fields unless the workbook already defines them.
    """
    fields = active_rows(credit_rules["fields"])

    if "visible" in fields.columns:
        fields = flagged_rows(fields, "visible")

    existing_keys = set(column_text(fields, "field_key"))
    is_legacy_row = column_text(fields, "field_key").eq("collection_contact")
    old_collection = fields[is_legacy_row]
    legacy = old_collection.iloc[0].to_dict() if not old_collection.empty else {}

    try:
        order = float(legacy.get("display_order"))
        if pd.isna(order):
            order = 30.0
    except (ValueError, TypeError):
        order = 30.0

    fields = fields[~is_legacy_row].copy()

    new_fields = []
    for key, label, required, offset in [
        ("collection_contact_name", "Collection Contact Name", "Y", 0.01),
        ("collection_contact_email", "Collection Contact Email", "Y", 0.02),
        ("collection_contact_phone", "Collection Contact Phone", "N", 0.03),
    ]:
        if key in existing_keys:
            continue
        new_fields.append(
            {
                **legacy,
                "section": CREDIT_MANAGEMENT,
                "field_key": key,
                "label": label,
                "input_type": "text",
                "required": required,
                "visible": "Y",
                "editable": "Y",
                "value_source": "mapping",
                "mapping_column": key,
                "preserve_existing": "Y",
                "display_order": order + offset,
                "active": "Y",
                "notes": COLLECTION_CONTACT_NOTE if key == "collection_contact_name" else "",
            }
        )

    if new_fields:
        fields = pd.concat([fields, pd.DataFrame(new_fields)], ignore_index=True)

    return sort_by_display_order(fields)


def get_credit_mapping(
    *,
    company_code: str,
    credit_rules: dict[str, pd.DataFrame],
) -> dict[str, str] | None:
    """Credit_Mapping row for the Company Code (column company_code or sp1)."""
    mapping = active_rows(credit_rules["mapping"])

    company_column = (
        "company_code"
        if "company_code" in mapping.columns
        else "sp1"
        if "sp1" in mapping.columns
        else None
    )
    if company_column is None:
        return None

    match = mapping[column_text(mapping, company_column) == clean(company_code)]
    if match.empty:
        return None

    return {
        str(column): clean(value) for column, value in match.iloc[0].to_dict().items()
    }


def get_credit_initial_value(
    *,
    field: FieldRecord,
    customer: dict[str, str],
    mapping: dict[str, str] | None,
) -> str:
    """Starting value of a credit field from the customer and the mapping."""
    field_key = clean(field.get("field_key"))
    existing_value = clean(customer.get(field_key))
    mapped = mapping or {}
    value_source = clean(field.get("value_source")).lower()

    # Typed by the requester: the field starts empty
    if value_source == "manual":
        return ""

    if field_key in COLLECTION_CONTACT_KEYS:
        explicit_value = existing_value or clean(mapped.get(field_key))
        if explicit_value:
            return explicit_value

        # Older data keeps one collection_contact value: a name or an email
        legacy_value = clean(customer.get("collection_contact")) or clean(
            mapped.get("collection_contact")
        )
        if (
            field_key == "collection_contact_name"
            and legacy_value
            and "@" not in legacy_value
        ):
            return legacy_value
        if field_key == "collection_contact_email" and "@" in legacy_value:
            return legacy_value
        return ""

    if is_yes(field.get("preserve_existing")) and existing_value:
        return existing_value

    if value_source == "existing":
        return existing_value

    if value_source == "mapping":
        # "collection_specialist|credit_controller": the first filled column wins
        mapping_columns = clean(field.get("mapping_column")) or field_key
        for mapping_column in mapping_columns.split("|"):
            mapped_value = clean(mapped.get(clean(mapping_column)))
            if mapped_value:
                return mapped_value
        if existing_value:
            return existing_value

    return ""


# =============================================================================
# FORM PLAN
# =============================================================================


@dataclass(frozen=True)
class CreditFormPlan:
    """What the Credit Management section shows for one customer."""

    display_fields: pd.DataFrame
    field_map: dict[str, FieldRecord]
    same_credit_owner: bool
    credit_controller_initial: str
    credit_analyst_initial: str


def plan_credit_form(
    *,
    fields: pd.DataFrame,
    customer: dict[str, str],
    mapping: dict[str, str] | None,
) -> CreditFormPlan:
    """
    Hide Credit Analyst when it is the same person as the Credit Controller;
    the analyst value then follows the controller (see finalize_credit_values).
    """
    initial = {
        clean(row.get("field_key")): get_credit_initial_value(
            field=row,
            customer=customer,
            mapping=mapping,
        )
        for row in fields.to_dict("records")
    }

    controller = clean(initial.get("credit_controller"))
    analyst = clean(initial.get("credit_analyst"))
    same_owner = bool(controller and analyst and controller.casefold() == analyst.casefold())

    display_fields = fields.copy()
    if same_owner:
        display_fields = fields[
            ~column_text(fields, "field_key").eq("credit_analyst")
        ].copy()

    field_map = {
        clean(row.get("field_key")): row
        for row in display_fields.to_dict("records")
        if clean(row.get("field_key"))
    }

    return CreditFormPlan(
        display_fields=display_fields,
        field_map=field_map,
        same_credit_owner=same_owner,
        credit_controller_initial=controller,
        credit_analyst_initial=analyst,
    )


def finalize_credit_values(
    plan: CreditFormPlan,
    values: dict[str, str],
    defaults: dict[str, str],
) -> None:
    """Add the derived credit values to the entered ones (in place)."""
    if plan.same_credit_owner:
        values["credit_analyst"] = clean(
            values.get("credit_controller") or plan.credit_controller_initial
        )
        defaults["credit_analyst"] = plan.credit_analyst_initial

    values["collection_contact"] = clean(values.get("collection_contact_name"))
