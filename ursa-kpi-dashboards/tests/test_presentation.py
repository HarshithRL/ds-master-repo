import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from dashboard_presentation import merge_presentation, validate_expression, validate_result_fields
from ursa_plan import compile_dashboard

SPEC = importlib.util.spec_from_file_location("ursa_presentation_builder", ROOT / "scripts" / "build_bundle.py")
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class PresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = json.loads((ROOT / "source_dashboards" / "ursa_ps4_daily_kpi_tracker.lvdash.json").read_text())
        cls.compiled, cls.plan = compile_dashboard(cls.source)

    def live_copy(self):
        serialized = json.dumps(self.compiled).replace("${var.catalog}", "automation_d").replace("${var.result_suffix}", "_dev")
        return json.loads(serialized)

    def test_layout_changes_survive_rebuild_without_changing_the_data_plan(self):
        presentation = self.live_copy()
        presentation["pages"][0]["displayName"] = "Updated DEV visual"
        presentation["pages"][0]["layout"][0]["widget"]["spec"]["frame"]["title"] = "Updated KPI"
        presentation["pages"][0]["layout"][0]["position"]["height"] += 1
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "source_dashboards").mkdir()
            (root / "source_dashboards" / "ursa_ps4_daily_kpi_tracker.lvdash.json").write_text(json.dumps(self.source))
            original = builder.generated_artifacts(root)
            (root / "source_dashboards" / "dashboard_presentation.json").write_text(json.dumps(presentation))
            updated = builder.generated_artifacts(root)
            plan_path = root / "src" / "config" / "dashboard_plan.json"
            self.assertEqual(updated[plan_path], original[plan_path])
            resource = yaml.safe_load(updated[root / "resources" / "dashboards" / "ursa_ps4.dashboard.yml"])
            actual = json.loads(resource["resources"]["dashboards"]["ursa_ps4_daily_kpi_tracker"]["serialized_dashboard"])
            self.assertEqual(actual["pages"], presentation["pages"])
            self.assertEqual(actual["datasets"], self.compiled["datasets"])
            builder.build(root)
            builder.build(root, check=True)
            test_spec = importlib.util.spec_from_file_location("ursa_captured_build_tests", ROOT / "tests" / "test_build.py")
            build_tests = importlib.util.module_from_spec(test_spec)
            test_spec.loader.exec_module(build_tests)
            result = unittest.TestResult()
            with patch.object(build_tests, "ROOT", root):
                build_tests.ArtifactTests("test_generated_dashboard_preserves_every_non_query_source_property").run(result)
            self.assertEqual(result.errors + result.failures, [])

    def test_native_dev_values_are_replaced_with_existing_target_placeholders(self):
        actual = merge_presentation(self.compiled, self.live_copy(), self.plan)
        self.assertEqual(actual, self.compiled)
        self.assertNotIn("automation_d", json.dumps(actual))
        self.assertNotIn("_dev`", json.dumps(actual))

    def test_original_authoring_dashboard_can_supply_visuals_without_changing_producer_sql(self):
        source = copy.deepcopy(self.source)
        source["pages"][0]["displayName"] = "Authoring visual"
        result = merge_presentation(self.compiled, source, self.plan)
        self.assertEqual(result["pages"], source["pages"])
        self.assertEqual(result["datasets"], self.compiled["datasets"])

    def test_new_pages_and_widgets_do_not_change_the_materialization_inventory(self):
        presentation = self.live_copy()
        page = copy.deepcopy(presentation["pages"][0])
        page["name"] = "extra_visual_page"
        presentation["pages"].append(page)
        merged = merge_presentation(self.compiled, presentation, self.plan)
        self.assertEqual(len(merged["pages"]), 15)
        self.assertEqual(self.plan["source_inventory"]["pages"], 14)

    def test_query_changes_new_sources_and_wrong_environment_are_rejected(self):
        for statement in (
            "SELECT * FROM `synapse-prd`.pbi.company",
            "SELECT * FROM automation_p.gold.URSA_KPI_result_ursa_kpi_data",
            "SELECT * FROM automation_d.gold.URSA_KPI_result_ursa_kpi_data_dev WHERE daily_value > 1",
            "DROP TABLE automation_d.gold.URSA_KPI_result_ursa_kpi_data_dev",
        ):
            with self.subTest(statement=statement):
                presentation = self.live_copy()
                presentation["datasets"][0]["queryLines"] = [statement]
                with self.assertRaises(ValueError):
                    merge_presentation(self.compiled, presentation, self.plan)

    def test_dataset_inventory_graph_and_empty_dashboard_changes_are_rejected(self):
        missing = self.live_copy()
        missing["datasets"].pop()
        duplicate = self.live_copy()
        duplicate["datasets"].append(copy.deepcopy(duplicate["datasets"][0]))
        graph = self.live_copy()
        graph["relationshipGraphs"] = [{"sources": []}]
        empty = self.live_copy()
        empty["pages"] = []
        for presentation in (missing, duplicate, graph, empty):
            with self.assertRaises(ValueError):
                merge_presentation(self.compiled, presentation, self.plan)

    def test_widget_and_calculated_fields_must_use_native_result_columns(self):
        presentation = {
            "datasets": [{"name": "summary", "columns": [{"displayName": "Total", "expression": "SUM(`value`)"}]}],
            "pages": [{"name": "overview", "layout": [{"widget": {"queries": [{"query": {"datasetName": "summary", "fields": [{"name": "total", "expression": "SUM(`value`)"}]}}]}}]}],
        }
        validate_result_fields(presentation, {"summary": ["value"]})
        with self.assertRaises(ValueError):
            validate_result_fields(presentation, {"summary": ["unrelated"]})
        presentation["datasets"][0]["columns"][0]["expression"] = "(SELECT secret FROM external_table)"
        with self.assertRaises(ValueError):
            validate_result_fields(presentation, {"summary": ["value"]})

    def test_native_associativity_is_allowed_only_as_the_exact_widget_expression(self):
        validate_expression("COUNT_IF(`associative_filter_predicate_group`)", {"value"}, "widget", associative=True)
        for expression, associative in (
            ("COUNT_IF(`associative_filter_predicate_group`)", False),
            ("SUM(`associative_filter_predicate_group`)", True),
            ("COUNT_IF(`associative_filter_predicate_group`) + missing", True),
        ):
            with self.subTest(expression=expression, associative=associative):
                with self.assertRaises(ValueError):
                    validate_expression(expression, {"value"}, "field", associative=associative)


if __name__ == "__main__":
    unittest.main()