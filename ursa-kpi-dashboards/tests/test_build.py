import copy
import importlib.util
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ursa_build_bundle", ROOT / "scripts" / "build_bundle.py")
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class ArtifactTests(unittest.TestCase):
    def test_generated_dashboard_preserves_every_non_query_source_property(self):
        artifacts = builder.generated_artifacts(ROOT)
        resource = yaml.safe_load(artifacts[ROOT / "resources" / "dashboards" / "ursa_ps4.dashboard.yml"])
        dashboard = resource["resources"]["dashboards"]["ursa_ps4_daily_kpi_tracker"]
        self.assertFalse(dashboard["embed_credentials"])
        self.assertEqual(dashboard["warehouse_id"], "${var.warehouse_id}")
        compiled = json.loads(dashboard["serialized_dashboard"])
        original = json.loads((ROOT / "source_dashboards" / "ursa_ps4_daily_kpi_tracker.lvdash.json").read_text())
        expected = copy.deepcopy(original)
        actual = copy.deepcopy(compiled)
        for definition in (expected, actual):
            for dataset in definition["datasets"]:
                dataset.pop("queryLines", None)
                dataset.pop("query", None)
        self.assertEqual(actual, expected)

    def test_generated_artifacts_are_deterministic(self):
        self.assertEqual(builder.generated_artifacts(ROOT), builder.generated_artifacts(ROOT))

    def test_check_mode_detects_a_missing_or_edited_artifact(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "source_dashboards").mkdir()
            source = ROOT / "source_dashboards" / "ursa_ps4_daily_kpi_tracker.lvdash.json"
            (root / "source_dashboards" / source.name).write_bytes(source.read_bytes())
            with self.assertRaises(ValueError):
                builder.build(root, check=True)
            summary = builder.build(root)
            self.assertEqual(summary["datasets"], 7)
            self.assertGreater(summary["projected_source_columns"], 0)
            builder.build(root, check=True)
            plan = root / "src" / "config" / "dashboard_plan.json"
            plan.write_text("{}")
            with self.assertRaises(ValueError):
                builder.build(root, check=True)


if __name__ == "__main__":
    unittest.main()