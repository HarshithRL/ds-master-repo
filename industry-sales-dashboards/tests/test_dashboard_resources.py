import importlib.util
import json
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "dashboard_renderer", ROOT / "scripts" / "render_dashboard_resources.py"
)
renderer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(renderer)
from source_snapshots import replace_source_references
from dataset_results import compile_dataset


class DashboardPreservationTests(unittest.TestCase):
    def test_relationship_alias_references_keep_their_dataset_and_source(self):
        metadata = json.loads((ROOT / "source_dashboards/open_orders.metadata.json").read_text())
        original = json.loads(metadata["serialized_dashboard"])
        transformed = renderer.prepare_dashboard(original, "open_orders")
        datasets = {dataset["name"] for dataset in transformed["datasets"]}
        sources = {source["name"]: source["datasetName"] for graph in transformed["relationshipGraphs"] for source in graph["sources"]}
        self.assertIn("ds_top_late_orders", datasets)
        self.assertEqual(sources["Top_Late_Orders_CM__YTD"], "ds_top_late_orders")
        self.assertNotIn("ds_cancellations_trend", datasets)
        from unittest.mock import patch

        with patch.dict(renderer.RETIRED_DATASETS, {"open_orders": {"ds_top_late_orders"}}):
            with self.assertRaises(ValueError):
                renderer.active_datasets(original, "open_orders")
        for key in renderer.DASHBOARDS:
            captured = json.loads((ROOT / "source_dashboards" / f"{key}.metadata.json").read_text())
            source_dashboard = json.loads(captured["serialized_dashboard"])
            active = {dataset["name"] for dataset in renderer.active_datasets(source_dashboard, key)}
            pages = json.dumps(source_dashboard["pages"])
            for graph in source_dashboard.get("relationshipGraphs", []):
                for source in graph["sources"]:
                    if source["name"] in pages:
                        self.assertIn(source["datasetName"], active, source["name"])

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
                    [dataset["name"] for dataset in renderer.active_datasets(original, key)],
                    [dataset["name"] for dataset in transformed["datasets"]],
                )
                for name in renderer.RETIRED_DATASETS[key]:
                    self.assertNotIn(name, json.dumps(transformed))
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
            self.assertIn(".gold.", resource)
            self.assertNotIn("industry_sales_src_", resource)

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
                    levels = [permission["permission_level"] for permission in entry["all_permissions"] if not permission["inherited"]]
                    if levels == ["CAN_READ"] and user_name.lower() not in renderer.dashboard_members(key):
                        self.assertNotIn(f"user_name: {user_name}", resource)
                    else:
                        self.assertIn(f"user_name: {user_name}", resource)

    def test_acc_prd_readers_are_scoped_to_one_dashboard_with_read_only_acl(self):
        resource = renderer.render_reader_permissions()
        self.assertNotIn("  D:", resource)
        self.assertNotIn("  T:", resource)
        self.assertEqual(resource.count("level: CAN_READ"), 4)
        self.assertNotIn("CAN_EDIT", resource)
        self.assertNotIn("CAN_MANAGE", resource)
        self.assertEqual(resource.count("group_name: AUTOMATION.INDUSTRYSALESDASHBOARDS.CONSUMER.READ\n"), 2)
        self.assertEqual(resource.count("group_name: AUTOMATION.INDUSTRYSALESDASHBOARDS.CONSUMER.WRITE\n"), 2)
        targets = yaml.safe_load(resource)["targets"]
        self.assertEqual(set(targets), {"A", "P"})
        for target in targets.values():
            dashboards = target["resources"]["dashboards"]
            self.assertEqual(set(dashboards), {"industry_open_orders", "industry_quotations"})
            for dashboard, tier in (("industry_open_orders", "READ"), ("industry_quotations", "WRITE")):
                self.assertEqual(dashboards[dashboard]["permissions"], [{"group_name": "AUTOMATION.INDUSTRYSALESDASHBOARDS.CONSUMER." + tier, "level": "CAN_READ"}])

    def test_provisioned_reader_groups_are_explicitly_included_in_deployment(self):
        config = yaml.safe_load((ROOT / "databricks.yml").read_text())
        included = {path.relative_to(ROOT).as_posix() for pattern in config["include"] for path in ROOT.glob(pattern)}
        self.assertIn("resources/dashboards/open_orders.dashboard.yml", included)
        self.assertIn("resources/dashboards/quotations.dashboard.yml", included)
        self.assertIn("resources/jobs/industry_sales_refresh.job.yml", included)
        reader_acl = "resources/dashboards/readers.permissions.yml"
        self.assertIn(reader_acl, config["include"])
        self.assertIn(reader_acl, included)
        self.assertNotIn("resources/dashboards/*.yml", config["include"])
        for relative in included - {reader_acl}:
            self.assertNotIn("AUTOMATION.INDUSTRYSALESDASHBOARDS.CONSUMER.", (ROOT / relative).read_text())

    def test_every_query_uses_its_compiled_result_without_changing_dataset_metadata(self):
        for key in renderer.DASHBOARDS:
            metadata = json.loads((ROOT / "source_dashboards" / f"{key}.metadata.json").read_text())
            original = json.loads(metadata["serialized_dashboard"])
            baseline = original
            transformed = renderer.prepare_dashboard(original, key)
            schemas = json.loads((ROOT / "src/config/source_column_names.json").read_text())
            for before, after in zip(renderer.active_datasets(baseline, key), transformed["datasets"], strict=True):
                plan = compile_dataset(key, before["name"], "".join(before["queryLines"]), schemas)
                self.assertEqual("".join(after["queryLines"]), plan["consumer_sql"] + "\n")
                self.assertEqual(
                    {name: value for name, value in before.items() if name != "queryLines"},
                    {name: value for name, value in after.items() if name != "queryLines"},
                )

    def test_job_calculation_keeps_the_exact_original_business_sql(self):
        metadata = json.loads((ROOT / "source_dashboards/open_orders.metadata.json").read_text())
        dataset = next(item for item in json.loads(metadata["serialized_dashboard"])["datasets"] if item["name"] == "ds_overview_allocation")
        expected = "".join(renderer.parameterize(dataset)["queryLines"])
        self.assertEqual((ROOT / "src/config/open_orders_allocation.sql").read_text(), expected)


if __name__ == "__main__":
    unittest.main()