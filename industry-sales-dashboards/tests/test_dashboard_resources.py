import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "dashboard_renderer", ROOT / "scripts" / "render_dashboard_resources.py"
)
renderer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(renderer)
from source_snapshots import replace_source_references


class DashboardPreservationTests(unittest.TestCase):
    def test_all_native_pages_and_widgets_are_unchanged(self):
        for key in renderer.DASHBOARDS:
            with self.subTest(dashboard=key):
                metadata = json.loads(
                    (ROOT / "source_dashboards" / f"{key}.metadata.json").read_text()
                )
                original = json.loads(metadata["serialized_dashboard"])
                transformed = renderer.prepare_dashboard(original, key)
                self.assertEqual(original["pages"], transformed["pages"])
                self.assertEqual(original.keys(), transformed.keys())
                self.assertEqual(
                    [dataset["name"] for dataset in original["datasets"]],
                    [dataset["name"] for dataset in transformed["datasets"]],
                )
                renderer.render(key)

    def test_business_sql_changes_only_at_source_references(self):
        for key in renderer.DASHBOARDS:
            with self.subTest(dashboard=key):
                metadata = json.loads(
                    (ROOT / "source_dashboards" / f"{key}.metadata.json").read_text()
                )
                original = json.loads(metadata["serialized_dashboard"])
                transformed = renderer.parameterize(original)
                for before, after in zip(
                    original["datasets"], transformed["datasets"], strict=True
                ):
                    expected_dataset = dict(before)
                    query = replace_source_references("".join(before["queryLines"]))
                    expected_dataset["queryLines"] = query.splitlines(keepends=True)
                    expected = json.dumps(expected_dataset)
                    for prefix in renderer.MAPPING_PREFIXES:
                        expected = expected.replace(
                            prefix,
                            "${var.catalog}.gold.${var.mapping_table_name}",
                        )
                    self.assertEqual(json.loads(expected), after)

    def test_consumer_dashboard_definitions_have_no_foreign_source_references(self):
        for key in renderer.DASHBOARDS:
            resource = renderer.render(key)
            self.assertNotIn("synapse-prd", resource)
            self.assertNotIn("${var.source_catalog}", resource)
            self.assertNotIn("supply_chain_sandbox", resource)
            self.assertIn("${var.catalog}", resource)
            self.assertIn(".silver.", resource)

    def test_unknown_source_shape_is_rejected(self):
        from unittest.mock import patch

        with patch.dict(renderer.DASHBOARDS, {"open_orders": (0, 0, 0)}):
            with self.assertRaises(ValueError):
                renderer.render("open_orders")

    def test_original_explicit_readers_and_editors_are_preserved(self):
        for key in renderer.DASHBOARDS:
            acl = json.loads((ROOT / "source_dashboards" / f"{key}.permissions.json").read_text())
            resource = renderer.render(key)
            for entry in acl["access_control_list"]:
                user_name = entry.get("user_name")
                if user_name and user_name not in renderer.MANAGERS:
                    self.assertIn(f"user_name: {user_name}", resource)

    def test_only_allocation_query_changes_to_gold_snapshot(self):
        for key in renderer.DASHBOARDS:
            metadata = json.loads((ROOT / "source_dashboards" / f"{key}.metadata.json").read_text())
            original = json.loads(metadata["serialized_dashboard"])
            baseline = renderer.parameterize(original)
            transformed = renderer.prepare_dashboard(original, key)
            for before, after in zip(baseline["datasets"], transformed["datasets"], strict=True):
                if key == "open_orders" and before["name"] == "ds_overview_allocation":
                    self.assertEqual(after["queryLines"], [
                        "SELECT scope, cs_team, segment, plant, bucket, value_eur\n",
                        "FROM ${var.catalog}.gold.${var.allocation_table_name}\n",
                    ])
                    self.assertEqual(
                        {name: value for name, value in before.items() if name != "queryLines"},
                        {name: value for name, value in after.items() if name != "queryLines"},
                    )
                else:
                    self.assertEqual(before, after)

    def test_job_calculation_keeps_the_exact_original_business_sql(self):
        metadata = json.loads((ROOT / "source_dashboards/open_orders.metadata.json").read_text())
        dataset = next(item for item in json.loads(metadata["serialized_dashboard"])["datasets"] if item["name"] == "ds_overview_allocation")
        expected = "".join(renderer.parameterize(dataset)["queryLines"])
        self.assertEqual((ROOT / "src/config/open_orders_allocation.sql").read_text(), expected)


if __name__ == "__main__":
    unittest.main()