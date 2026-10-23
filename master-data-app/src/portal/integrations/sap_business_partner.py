"""
Live customer data from SAP through the Business Partner OData API
(API_BUSINESS_PARTNER, OData v2), read with the app's SAP technical user.

Which API property fills which AXIOM attribute is maintained in
sap_api_mapping.xlsx (Field_Mapping) in the Volume and reaches the app through
the seeded snapshot table; this module only knows how to reach each API entity.
"""

from __future__ import annotations

import re
import threading
import time
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

import pandas as pd
import requests

from portal.config import (
    SAP_API_URL,
    SAP_CA_BUNDLE,
    SAP_CACHE_SECONDS,
    SAP_CLIENT,
    SAP_PASSWORD,
    SAP_TIMEOUT_SECONDS,
    SAP_USER,
    SAP_VERIFY_TLS,
)
from portal.core.customers import CustomerRecord
from portal.core.utils import active_rows, clean


class SapError(RuntimeError):
    """SAP could not be reached or refused the request; the message is shown to the user."""


# Expanded navigation for each entity reached from A_Customer / A_BusinessPartner
CUSTOMER_EXPANDS = {
    "A_CustomerCompany": "to_CustomerCompany",
    "A_CustomerDunning": "to_CustomerCompany/to_CustomerDunning",
    "A_CustomerSalesArea": "to_CustomerSalesArea",
    "A_CustSalesPartnerFunc": "to_CustomerSalesArea/to_PartnerFunction",
}
PARTNER_EXPANDS = {
    "A_BusinessPartnerAddress": "to_BusinessPartnerAddress",
    "A_AddressPhoneNumber": "to_BusinessPartnerAddress/to_PhoneNumber",
    "A_AddressEmailAddress": "to_BusinessPartnerAddress/to_EmailAddress",
    "A_BusinessPartnerBank": "to_BusinessPartnerBank",
    "A_BuPaIdentification": "to_BuPaIdentification",
    "A_BusinessPartnerTaxNumber": "to_BusinessPartnerTax",
}
COMPANY_ENTITIES = {"A_CustomerCompany", "A_CustomerDunning"}
SALES_AREA_ENTITIES = {"A_CustomerSalesArea", "A_CustSalesPartnerFunc"}

# =============================================================================
# HTTP
# =============================================================================


@lru_cache(maxsize=1)
def _session() -> requests.Session:
    if not SAP_API_URL:
        raise SapError("The SAP connection is not configured (SAP_API_URL is empty).")
    if not SAP_USER or not SAP_PASSWORD:
        raise SapError("The SAP user or password is missing (SAP_USER / SAP_PASSWORD).")

    session = requests.Session()
    session.auth = (SAP_USER, SAP_PASSWORD)
    session.headers.update({"Accept": "application/json"})
    session.verify = SAP_CA_BUNDLE or SAP_VERIFY_TLS
    return session


def _quote(value: str) -> str:
    """OData string literal content: a single quote is doubled."""
    return clean(value).replace("'", "''")


def _get(path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
    query = {"$format": "json", **(params or {})}
    if SAP_CLIENT:
        query["sap-client"] = SAP_CLIENT

    try:
        response = _session().get(f"{SAP_API_URL.rstrip('/')}/{path}", params=query, timeout=SAP_TIMEOUT_SECONDS)
    except requests.exceptions.SSLError as exc:
        raise SapError(f"SAP's certificate is not trusted (set SAP_CA_BUNDLE): {exc}") from exc
    except requests.exceptions.RequestException as exc:
        raise SapError(f"SAP cannot be reached from the app ({type(exc).__name__}). Check the network route.") from exc

    if response.status_code == 404:
        return {}
    if response.status_code in (401, 403):
        raise SapError(f"SAP refused the technical user (HTTP {response.status_code}). Check the user, password and its authorisations.")
    if not response.ok:
        raise SapError(f"SAP returned HTTP {response.status_code}: {response.text[:300]}")

    return response.json().get("d", {})


def _results(entity: dict[str, Any], navigation: str) -> list[dict[str, Any]]:
    """Expanded OData v2 lists come as {"results": [...]}."""
    value = entity.get(navigation)
    if isinstance(value, dict):
        return value.get("results", [])
    return value if isinstance(value, list) else []


# =============================================================================
# MAPPING (sap_api_mapping.xlsx, Field_Mapping)
# =============================================================================


def mapping_rows(mapping: pd.DataFrame) -> list[dict[str, str]]:
    """Active Field_Mapping rows that name an API entity and property."""
    return [
        {key: clean(value) for key, value in row.items()}
        for row in active_rows(mapping).to_dict("records")
        if clean(row.get("api_entity")) and clean(row.get("api_property")) and clean(row.get("field_key"))
    ]


def _filters(text: str) -> list[tuple[str, str]]:
    return [
        (name.strip(), value.strip())
        for part in clean(text).split(";")
        if "=" in part
        for name, value in [part.split("=", 1)]
    ]


def _matches(row: dict[str, Any], filters: list[tuple[str, str]]) -> bool:
    return all(str(row.get(name, "")).strip().casefold() == value.casefold() for name, value in filters)


def _format(value: Any, value_format: str) -> str:
    if value_format == "flag":
        return "X" if value is True or clean(value).upper() in {"X", "TRUE"} else ""
    if value_format == "date":
        match = re.search(r"/Date\((-?\d+)", clean(value))
        if match:
            return datetime.fromtimestamp(int(match.group(1)) / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    return clean(value)


# =============================================================================
# CUSTOMER
# =============================================================================

_cache: dict[str, tuple[float, dict[str, Any] | None]] = {}
_cache_lock = threading.Lock()


def fetch_customer(customer_id: str, mapping: pd.DataFrame) -> dict[str, Any] | None:
    """
    Raw SAP data of one customer (A_Customer and its business partner, with
    only the expansions the mapping needs). Cached for SAP_CACHE_SECONDS.
    """
    customer_id = clean(customer_id)
    if not customer_id:
        return None

    with _cache_lock:
        cached = _cache.get(customer_id)
        if cached and time.time() - cached[0] < SAP_CACHE_SECONDS:
            return cached[1]

    entities = {row["api_entity"] for row in mapping_rows(mapping)}
    customer_expand = ",".join(sorted({CUSTOMER_EXPANDS[e] for e in entities if e in CUSTOMER_EXPANDS}))
    partner_expand = ",".join(sorted({PARTNER_EXPANDS[e] for e in entities if e in PARTNER_EXPANDS}))

    customer = _get(f"A_Customer('{_quote(customer_id)}')", {"$expand": customer_expand} if customer_expand else None)
    raw = None

    if customer:
        params = {"$filter": f"Customer eq '{_quote(customer_id)}'", "$top": "1"}
        if partner_expand:
            params["$expand"] = partner_expand
        partners = _get("A_BusinessPartner", params).get("results", [])
        raw = {"A_Customer": customer, "A_BusinessPartner": partners[0] if partners else {}}

    with _cache_lock:
        _cache[customer_id] = (time.time(), raw)
    return raw


def entity_rows(raw: dict[str, Any], entity: str) -> list[dict[str, Any]]:
    customer = raw.get("A_Customer") or {}
    partner = raw.get("A_BusinessPartner") or {}
    companies = _results(customer, "to_CustomerCompany")
    sales_areas = _results(customer, "to_CustomerSalesArea")
    addresses = _results(partner, "to_BusinessPartnerAddress")

    def defaults_first(rows: list[dict[str, Any]], flag: str) -> list[dict[str, Any]]:
        return sorted(rows, key=lambda row: not row.get(flag))

    rows = {
        "A_Customer": [customer],
        "A_BusinessPartner": [partner] if partner else [],
        "A_CustomerCompany": companies,
        "A_CustomerDunning": [d for c in companies for d in _results(c, "to_CustomerDunning")],
        "A_CustomerSalesArea": sales_areas,
        "A_CustSalesPartnerFunc": [f for s in sales_areas for f in _results(s, "to_PartnerFunction")],
        "A_BusinessPartnerAddress": addresses,
        "A_AddressPhoneNumber": defaults_first([p for a in addresses for p in _results(a, "to_PhoneNumber")], "IsDefaultPhoneNumber"),
        "A_AddressEmailAddress": defaults_first([m for a in addresses for m in _results(a, "to_EmailAddress")], "IsDefaultEmailAddress"),
        "A_BusinessPartnerBank": _results(partner, "to_BusinessPartnerBank"),
        "A_BuPaIdentification": _results(partner, "to_BuPaIdentification"),
        "A_BusinessPartnerTaxNumber": _results(partner, "to_BusinessPartnerTax"),
    }
    return rows.get(entity, [])


def _scoped(rows: list[dict[str, Any]], entity: str, company_code: str, sales_org: str) -> list[dict[str, Any]]:
    """Rows of the chosen Company Code / Sales Organization (if that one exists)."""
    if entity in COMPANY_ENTITIES and company_code:
        chosen = [row for row in rows if clean(row.get("CompanyCode")) == company_code]
        return chosen or rows
    if entity in SALES_AREA_ENTITIES and sales_org:
        chosen = [row for row in rows if clean(row.get("SalesOrganization")) == sales_org]
        return chosen or rows
    return rows


def map_customer(
    raw: dict[str, Any],
    mapping: pd.DataFrame,
    *,
    company_code: str = "",
    sales_org: str = "",
) -> CustomerRecord:
    """The AXIOM customer record ({field_key: value}) from the raw SAP data."""
    record: CustomerRecord = {}

    for row in mapping_rows(mapping):
        key = row["field_key"]
        if clean(record.get(key)):
            continue  # an earlier mapping row already gave a value

        rows = _scoped(entity_rows(raw, row["api_entity"]), row["api_entity"], company_code, sales_org)
        rows = [item for item in rows if _matches(item, _filters(row.get("api_filter", "")))]
        properties = [name.strip() for name in row["api_property"].split("+")]
        value = ""
        if rows:
            value = " ".join(
                part for part in (_format(rows[0].get(name), row.get("value_format", "text")) for name in properties) if part
            )
        record[key] = value

    customer = raw.get("A_Customer") or {}
    record["customer_id"] = clean(customer.get("Customer")) or record.get("customer_id", "")
    record["company_codes"] = ", ".join(
        clean(row.get("CompanyCode")) for row in _results(customer, "to_CustomerCompany") if clean(row.get("CompanyCode"))
    )
    return record


def sap_customer(
    customer_id: str,
    mapping: pd.DataFrame,
    *,
    company_code: str = "",
    sales_org: str = "",
) -> CustomerRecord | None:
    raw = fetch_customer(customer_id, mapping)
    if raw is None:
        return None
    return map_customer(raw, mapping, company_code=clean(company_code), sales_org=clean(sales_org))


# =============================================================================
# SEARCH (sidebar)
# =============================================================================

VAT_PATTERN = re.compile(r"^[A-Za-z]{2}[0-9A-Za-z]{6,14}$")


def _summary(partner: dict[str, Any]) -> dict[str, str]:
    address = next(iter(_results(partner, "to_BusinessPartnerAddress")), {})
    return {
        "customer_id": clean(partner.get("Customer")) or clean(partner.get("BusinessPartner")),
        "name_1": clean(partner.get("OrganizationBPName1")) or clean(partner.get("BusinessPartnerFullName")),
        "city": clean(address.get("CityName")),
        "country": clean(address.get("Country")),
    }


def sap_search(query: str, limit: int = 8) -> list[dict[str, str]]:
    """
    Customers by number (exact), VAT number (exact) or name (contains).
    SAP compares text case-sensitively, so the name is also tried in upper
    case and title case.
    """
    query = clean(query)
    if not query:
        return []

    expand = {"$expand": "to_BusinessPartnerAddress"}

    if query.isdigit():
        params = {"$filter": f"Customer eq '{_quote(query)}'", "$top": "1", **expand}
        return [_summary(p) for p in _get("A_BusinessPartner", params).get("results", [])]

    matches: list[dict[str, str]] = []

    if VAT_PATTERN.match(query) and any(ch.isdigit() for ch in query):
        customers = _get("A_Customer", {"$filter": f"VATRegistration eq '{_quote(query.upper())}'", "$top": str(limit)})
        for customer in customers.get("results", []):
            params = {"$filter": f"Customer eq '{_quote(customer.get('Customer'))}'", "$top": "1", **expand}
            matches += [_summary(p) for p in _get("A_BusinessPartner", params).get("results", [])]
        if matches:
            return matches[:limit]

    variants = list(dict.fromkeys([query, query.upper(), query.title()]))
    name_filter = " or ".join(f"substringof('{_quote(v)}', OrganizationBPName1)" for v in variants)
    params = {"$filter": f"Customer ne '' and ({name_filter})", "$top": str(limit), **expand}
    return [_summary(p) for p in _get("A_BusinessPartner", params).get("results", [])]
