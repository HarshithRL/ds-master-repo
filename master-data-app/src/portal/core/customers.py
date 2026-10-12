"""Customer lookup and the data behind the Existing Customer card."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from portal.core.utils import (
    active_rows,
    clean,
    column_text,
    lowercase_columns,
    normalize_customer_id,
)

CustomerRecord = dict[str, str]

# =============================================================================
# LOOKUP
# =============================================================================


def get_customer(
    customer_id: str,
    db: dict[str, pd.DataFrame],
) -> CustomerRecord | None:
    customers = active_rows(db["customers"])
    match = customers[
        customers["customer_id"].apply(normalize_customer_id)
        == normalize_customer_id(customer_id)
    ]

    if match.empty:
        return None

    return {
        str(column): clean(value) for column, value in match.iloc[0].to_dict().items()
    }


def customer_company_code(customer: CustomerRecord | None) -> str:
    """Company Code the customer belongs to (company_code column)."""
    return clean((customer or {}).get("company_code"))


def search_customers(
    query: str,
    db: dict[str, pd.DataFrame],
    limit: int = 8,
) -> list[CustomerRecord]:
    """
    Customers matching a SAP ID (exact, or starting with the digits), a name
    or a VAT number (contains, case-insensitive). An exact ID match comes first.
    """
    query = clean(query)
    if not query:
        return []

    customers = active_rows(db["customers"])
    ids = customers["customer_id"].apply(normalize_customer_id)
    needle = query.casefold()

    exact = ids == normalize_customer_id(query)
    partial = (
        ids.str.startswith(normalize_customer_id(query))
        | column_text(customers, "name_1").str.casefold().str.contains(needle, regex=False)
        | column_text(customers, "vat_registration_number").str.casefold().str.contains(
            needle.replace(" ", ""), regex=False
        )
    )

    matches = pd.concat([customers[exact], customers[partial & ~exact]]).head(limit)

    return [
        {str(column): clean(value) for column, value in row.items()}
        for row in matches.to_dict("records")
    ]


def customer_display_name(customer: dict[str, str] | None) -> str:
    if not customer:
        return ""

    return (
        clean(customer.get("name_1", ""))
        or clean(customer.get("customer_name", ""))
        or clean(customer.get("name", ""))
    )


# =============================================================================
# COUNTRY-SPECIFIC TAX LABELS
# =============================================================================


def tax_number_labels(
    reference_library: dict[str, pd.DataFrame],
    country: str,
) -> dict[str, str]:
    """{tax_number_N: label} configured in Tax_Details for the country."""
    tax_details = reference_library.get("tax_details")

    if tax_details is None or tax_details.empty or not country:
        return {}

    tax_details = lowercase_columns(tax_details)

    if "cust_country" not in tax_details.columns:
        return {}

    matching = tax_details[
        column_text(tax_details, "cust_country").str.upper().eq(country)
    ]

    if matching.empty:
        return {}

    labels: dict[str, str] = {}

    for number in range(1, 7):
        key = f"tax_number_{number}"
        configured_label = clean(matching.iloc[0].get(key))

        if configured_label:
            labels[key] = configured_label

    return labels


# =============================================================================
# EXISTING CUSTOMER CARD
# =============================================================================


@dataclass(frozen=True)
class OverviewItem:
    label: str
    value: str
    tooltip: str = ""


@dataclass(frozen=True)
class OverviewSection:
    title: str
    items: list[OverviewItem]


def build_customer_overview(
    customer: dict[str, str],
    reference_library: dict[str, pd.DataFrame],
) -> list[OverviewSection]:
    """
    Group the General_Data_Fields marked display=Y into the card sections.

    Fields that do not belong to a named group end up in
    Additional Information, so every displayed field is shown.
    """
    fields = lowercase_columns(active_rows(reference_library["general_data_fields"]))

    if "display" in fields.columns:
        fields = fields[column_text(fields, "display").str.upper().eq("Y")]

    configured: dict[str, dict] = {}

    for record in fields.to_dict("records"):
        key = clean(record.get("field_key")).lower()

        if key:
            configured[key] = record

    def value(key: str) -> str:
        source = clean(configured.get(key, {}).get("customer_source_field"))

        if source and clean(customer.get(source)):
            return clean(customer.get(source))

        return clean(customer.get(key))

    def label(key: str, fallback: str) -> str:
        return clean(configured.get(key, {}).get("label")) or fallback

    used: set[str] = set()

    def configured_items(keys: list[tuple[str, str]]) -> list[OverviewItem]:
        items = []
        for key, fallback in keys:
            if key in configured:
                items.append(OverviewItem(label(key, fallback), value(key)))
                used.add(key)
        return items

    # Customer identity
    identity = configured_items(
        [
            ("customer_id", "Customer ID"),
            ("name_1", "Customer Name"),
            ("company_code", "Company Code"),
            ("customer_classification", "Customer Classification"),
        ]
    )

    # Tax information: VAT always, then the country's tax numbers
    country = (value("country") or clean(customer.get("country_key"))).upper()
    tax_labels = tax_number_labels(reference_library, country)

    taxes = [
        OverviewItem(
            label("vat_registration_number", "VAT Registration No."),
            value("vat_registration_number"),
        )
    ]
    used.add("vat_registration_number")

    for number in range(1, 7):
        key = f"tax_number_{number}"
        used.add(key)

        if key in tax_labels:
            taxes.append(
                OverviewItem(tax_labels[key], value(key), f"SAP Tax Number {number}")
            )

    # Address and contact
    address_parts = []

    for key in ["street", "postal_code", "city", "region", "country"]:
        if key in configured and value(key):
            address_parts.append(value(key))
        used.add(key)

    address = []

    if address_parts:
        address.append(OverviewItem("Registered Address", ", ".join(address_parts)))

    address += configured_items(
        [
            ("telephone", "Telephone"),
            ("email_address", "Email Address"),
        ]
    )

    # Additional information, including every remaining configured field
    additional = configured_items(
        [
            ("language", "Language"),
            ("created_on", "Created On"),
        ]
    )

    for key in configured:
        if key not in used:
            additional.append(OverviewItem(label(key, key), value(key)))

    sections = [
        OverviewSection("Customer Identity", identity),
        OverviewSection("Tax Information", taxes),
        OverviewSection("Address & Contact", address),
        OverviewSection("Additional Information", additional),
    ]

    return [section for section in sections if section.items]
