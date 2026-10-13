import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("industry_config", ROOT / "src" / "industry_config.py")
config = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(config)


class IndustryConfigurationTests(unittest.TestCase):
    def test_original_mapping_is_complete_unique_and_unchanged(self):
        capture = json.loads((ROOT / "source_dashboards" / "mapping_statement.json").read_text())
        rows = [dict(zip(config.MAPPING_COLUMNS, values, strict=True)) for values in capture["result"]["data_array"]]
        self.assertEqual(len(rows), 108)
        self.assertEqual(config.validate_mapping(rows), rows)

    def test_all_targets_match_their_workspace_and_catalog(self):
        for workspace_id, catalog in config.WORKSPACE_CATALOGS.items():
            for target, target_catalog in config.TARGET_CATALOGS.items():
                if catalog == target_catalog:
                    config.validate_environment(catalog, "synapse-prd", target, workspace_id)

    def test_cross_environment_writes_are_rejected(self):
        with self.assertRaises(ValueError):
            config.validate_environment("automation_p", "synapse-prd", "P", "7181820732839861")
        with self.assertRaises(ValueError):
            config.validate_environment("automation_d", "synapse-prd", "A", "7181820732839861")

    def test_invalid_source_identifier_is_rejected(self):
        with self.assertRaises(ValueError):
            config.validate_environment("automation_d", "synapse-prd`; DROP TABLE x", "D", "7181820732839861")

    def test_dev_and_ci_mapping_names_cannot_be_crossed(self):
        base_name = "industry_sales_cs_team_sales_org_mapping"
        config.validate_table_name(base_name + "_dev", "D")
        for target in ("T", "A", "P"):
            config.validate_table_name(base_name, target)
            with self.assertRaises(ValueError):
                config.validate_table_name(base_name + "_dev", target)
        with self.assertRaises(ValueError):
            config.validate_table_name(base_name, "D")
        with self.assertRaises(ValueError):
            config.validate_table_name(base_name + "; DROP TABLE x", "D")

    def test_empty_duplicate_null_and_numeric_mapping_keys_are_rejected(self):
        row = {"sales_org_code": "0012", "sales_organization": "Example", "cs_team": "Europe"}
        for rows in ([], [row, row], [dict(row, sales_org_code=None)], [dict(row, sales_org_code=12)]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                config.validate_mapping(rows)
        self.assertEqual(config.validate_mapping([row])[0]["sales_org_code"], "0012")


if __name__ == "__main__":
    unittest.main()