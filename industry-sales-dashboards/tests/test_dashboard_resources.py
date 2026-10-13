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


class DashboardPreservationTests(unittest.TestCase):
    def test_all_native_pages_and_widgets_are_unchanged(self):
        for key in renderer.DASHBOARDS:
            with self.subTest(dashboard=key):
                metadata = json.loads(
                    (ROOT / "source_dashboards" / f"{key}.metadata.json").read_text()
                )
                original = json.loads(metadata["serialized_dashboard"])
                transformed = renderer.parameterize(original)
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
                    expected = json.dumps(before)
                    for prefix in renderer.SOURCE_PREFIXES:
                        expected = expected.replace(prefix, "`${var.source_catalog}`.pbi.")
                    for prefix in renderer.MAPPING_PREFIXES:
                        expected = expected.replace(
                            prefix,
                            "${var.catalog}.gold.${var.mapping_table_name}",
                        )
                    self.assertEqual(json.loads(expected), after)

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


if __name__ == "__main__":
    unittest.main()