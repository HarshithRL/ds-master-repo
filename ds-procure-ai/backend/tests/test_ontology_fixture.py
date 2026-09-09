"""Process catalogs load without invented prices. SWIFT is one services example."""

from __future__ import annotations

import pytest

from ai_brain.core.procurement_ai.fixture_loader import load_catalog, load_swift_csp_bafo
from ai_brain.core.procurement_ai.ontology import VendorProfile


def test_swift_fixture_has_vendors_and_r01_r40():
    matrix = load_swift_csp_bafo()
    assert matrix.process_type == "indirect_it_services"
    assert len(matrix.vendors) == 5
    ids = [row.id for row in matrix.requirements]
    assert ids[0] == "R01"
    assert ids[-1] == "R40"
    assert len(ids) == 40
    assert "ecovadis" in VendorProfile.model_fields
    assert "creditsafe" in VendorProfile.model_fields
    for vendor in matrix.vendors:
        assert vendor.locators.get("ecovadis") != vendor.locators.get("creditsafe")
    assert all(line.amount_eur is None for line in matrix.tco)
    assert matrix.scorecard_owner == "Etex evaluation team"
    assert any("EcoVadis" in row for row in matrix.bafo_rows)
    assert any("CreditScore" in row for row in matrix.bafo_rows)


def test_each_process_type_has_its_own_catalog():
    direct = load_catalog("direct_tg")
    software = load_catalog("indirect_it_software")
    services = load_catalog("indirect_it_services")
    assert direct.process_type == "direct_tg"
    assert software.process_type == "indirect_it_software"
    assert services.process_type == "indirect_it_services"
    assert direct.bafo_rows != software.bafo_rows
    assert direct.bafo_rows != services.bafo_rows
    assert direct.vendors == []
    assert software.vendors == []
    assert all(line.amount_eur is None for line in direct.tco + software.tco)


def test_unknown_process_type_fails_closed():
    with pytest.raises(ValueError, match="unknown process_type"):
        load_catalog("swift")
    with pytest.raises(ValueError, match="unknown process_type"):
        load_catalog("")
