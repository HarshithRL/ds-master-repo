import argparse
import json
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ursa_plan import compile_dashboard


class LiteralString(str):
    pass


class BundleDumper(yaml.SafeDumper):
    pass


def represent_literal(dumper, value):
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style="|")


BundleDumper.add_representer(LiteralString, represent_literal)


def generated_artifacts(root):
    source = json.loads((root / "source_dashboards" / "ursa_ps4_daily_kpi_tracker.lvdash.json").read_text())
    compiled, plan = compile_dashboard(source)
    resource = {
        "resources": {
            "dashboards": {
                "ursa_ps4_daily_kpi_tracker": {
                    "display_name": "URSA PS4 Daily KPI Tracker",
                    "warehouse_id": "${var.warehouse_id}",
                    "embed_credentials": False,
                    "serialized_dashboard": LiteralString(json.dumps(compiled, indent=2, ensure_ascii=True) + "\n"),
                },
            },
        },
    }
    return {
        root / "src" / "config" / "dashboard_plan.json": json.dumps(plan, indent=2, ensure_ascii=True) + "\n",
        root / "resources" / "dashboards" / "ursa_ps4.dashboard.yml": yaml.dump(resource, Dumper=BundleDumper, sort_keys=False, allow_unicode=False, width=120),
    }


def build(root, check=False):
    artifacts = generated_artifacts(root)
    mismatches = []
    for path, expected in artifacts.items():
        if check:
            if not path.is_file() or path.read_text() != expected:
                mismatches.append(str(path.relative_to(root)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(expected)
    if mismatches:
        raise ValueError("Generated bundle artifacts are stale: " + ", ".join(mismatches))
    plan = json.loads(artifacts[root / "src" / "config" / "dashboard_plan.json"])
    return {
        **plan["source_inventory"],
        "source_relations": len(plan["sources"]),
        "projected_source_columns": sum(len(source["columns"]) for source in plan["sources"]),
        "source_sha256": plan["source_sha256"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    print(json.dumps(build(ROOT, args.check), indent=2))