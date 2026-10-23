import os
import sys
import unittest
from pathlib import Path

import pandas as pd

SOURCE_DIR = Path(__file__).resolve().parents[1] / "src"
os.environ.setdefault("MASTER_DATA_CATALOG", "automation_d")
sys.path.insert(0, str(SOURCE_DIR))

from portal.integrations.sap_business_partner import (  # noqa: E402
    CUSTOMER_EXPANDS,
    PARTNER_EXPANDS,
    map_customer,
    mapping_rows,
)

MAPPING = pd.DataFrame(
    # Field_Mapping is configuration: it lives in the Volume and reaches the app
    # through the seeded snapshot table, so the tests use their own rows here.
    [
        {"field_key": "customer_id", "api_entity": "A_Customer", "api_property": "Customer"},
        {"field_key": "name_1", "api_entity": "A_BusinessPartner", "api_property": "OrganizationBPName1"},
        {"field_key": "name_1", "api_entity": "A_Customer", "api_property": "CustomerName"},
        {"field_key": "vat_number", "api_entity": "A_Customer", "api_property": "VATRegistration"},
        {"field_key": "created_on", "api_entity": "A_Customer", "api_property": "CreationDate", "value_format": "date"},
        {"field_key": "street", "api_entity": "A_BusinessPartnerAddress", "api_property": "StreetName + HouseNumber"},
        {"field_key": "city", "api_entity": "A_BusinessPartnerAddress", "api_property": "CityName"},
        {"field_key": "postal_code", "api_entity": "A_BusinessPartnerAddress", "api_property": "PostalCode"},
        {"field_key": "country", "api_entity": "A_BusinessPartnerAddress", "api_property": "Country"},
        {"field_key": "telephone", "api_entity": "A_AddressPhoneNumber", "api_property": "PhoneNumber"},
        {"field_key": "company_code", "api_entity": "A_CustomerCompany", "api_property": "CompanyCode"},
        {"field_key": "reconciliation_account", "api_entity": "A_CustomerCompany", "api_property": "ReconciliationAccount"},
        {
            "field_key": "payment_history_record",
            "api_entity": "A_CustomerCompany",
            "api_property": "RecordPaymentHistoryIndicator",
            "value_format": "flag",
        },
        {"field_key": "dunning_procedure", "api_entity": "A_CustomerDunning", "api_property": "DunningProcedure"},
        {"field_key": "incoterm_location", "api_entity": "A_CustomerSalesArea", "api_property": "IncotermsLocation1"},
        {
            "field_key": "ship_to_party_id",
            "api_entity": "A_CustSalesPartnerFunc",
            "api_property": "BPCustomerNumber",
            "api_filter": "PartnerFunction=WE",
        },
        {"field_key": "retired", "api_entity": "A_NotSupported", "api_property": "Whatever", "active": "no"},
    ],
    columns=["field_key", "api_entity", "api_property", "api_filter", "value_format", "active"],
).fillna("")
MAPPING["active"] = MAPPING["active"].replace("", "yes")

# Shape of the API_BUSINESS_PARTNER responses (OData v2, expanded lists in "results")
RAW = {
    "A_Customer": {
        "Customer": "200",
        "CustomerName": "Eternit SAS Vernouillet",
        "VATRegistration": "FR39712018324",
        "TaxNumber1": "71201832400244",
        "CustomerClassification": "20",
        "CreationDate": "/Date(1051660800000)/",
        "to_CustomerCompany": {"results": [
            {"CompanyCode": "1320", "ReconciliationAccount": "4000000002", "RecordPaymentHistoryIndicator": False,
             "to_CustomerDunning": {"results": [{"CompanyCode": "1320", "DunningProcedure": "DE01"}]}},
            {"CompanyCode": "9320", "ReconciliationAccount": "4000000000", "RecordPaymentHistoryIndicator": True,
             "to_CustomerDunning": {"results": [{"CompanyCode": "9320", "DunningProcedure": "ET02"}]}},
        ]},
        "to_CustomerSalesArea": {"results": [
            {"SalesOrganization": "1004", "IncotermsLocation1": "Cost, Insurance and",
             "to_PartnerFunction": {"results": [{"SalesOrganization": "1004", "PartnerFunction": "RE", "BPCustomerNumber": "200"}]}},
            {"SalesOrganization": "9321", "IncotermsLocation1": "Paris",
             "to_PartnerFunction": {"results": [
                 {"SalesOrganization": "9321", "PartnerFunction": "RE", "BPCustomerNumber": "200"},
                 {"SalesOrganization": "9321", "PartnerFunction": "WE", "BPCustomerNumber": "201"},
             ]}},
        ]},
    },
    "A_BusinessPartner": {
        "BusinessPartner": "200",
        "OrganizationBPName1": "",
        "CorrespondenceLanguage": "FR",
        "to_BusinessPartnerAddress": {"results": [{
            "StreetName": "Rue de la Gare", "HouseNumber": "12", "CityName": "Vernouillet", "PostalCode": "78540", "Country": "FR",
            "to_PhoneNumber": {"results": [
                {"PhoneNumber": "0100000000", "IsDefaultPhoneNumber": False},
                {"PhoneNumber": "0139701234", "IsDefaultPhoneNumber": True},
            ]},
        }]},
    },
}


class SapMappingTests(unittest.TestCase):
    def test_every_active_row_uses_a_supported_entity(self):
        supported = {"A_Customer", "A_BusinessPartner"} | set(CUSTOMER_EXPANDS) | set(PARTNER_EXPANDS)
        for row in mapping_rows(MAPPING):
            with self.subTest(field=row["field_key"]):
                self.assertIn(row["api_entity"], supported)

    def test_maps_general_data_with_fallbacks_and_formats(self):
        record = map_customer(RAW, MAPPING)
        self.assertEqual(record["customer_id"], "200")
        self.assertEqual(record["name_1"], "Eternit SAS Vernouillet")  # BP name empty -> A_Customer fallback
        self.assertEqual(record["street"], "Rue de la Gare 12")  # StreetName+HouseNumber
        self.assertEqual(record["telephone"], "0139701234")  # standard number first
        self.assertEqual(record["created_on"], "2003-04-30")  # /Date()/ -> date
        self.assertEqual(record["country"], "FR")
        self.assertEqual(record["company_codes"], "1320, 9320")

    def test_company_and_sales_area_follow_the_chosen_scope(self):
        first = map_customer(RAW, MAPPING)
        self.assertEqual(first["company_code"], "1320")
        self.assertEqual(first["incoterm_location"], "Cost, Insurance and")

        chosen = map_customer(RAW, MAPPING, company_code="9320", sales_org="9321")
        self.assertEqual(chosen["company_code"], "9320")
        self.assertEqual(chosen["reconciliation_account"], "4000000000")
        self.assertEqual(chosen["payment_history_record"], "X")  # flag
        self.assertEqual(chosen["dunning_procedure"], "ET02")
        self.assertEqual(chosen["incoterm_location"], "Paris")
        self.assertEqual(chosen["ship_to_party_id"], "201")  # api_filter PartnerFunction=WE


if __name__ == "__main__":
    unittest.main()
