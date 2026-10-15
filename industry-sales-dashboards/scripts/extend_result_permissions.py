import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from dashboard_access import consumer_reader_groups


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    path = ROOT.parent / "permissions/access.json"
    access = json.loads(path.read_text())
    products = [product for product in access["data_products"] if product["data_product"] == "industry-sales-dashboards"]
    if len(products) != 1:
        raise ValueError("Expected one Industry Sales product")
    plans = json.loads((ROOT / "src/config/dashboard_results.json").read_text())["datasets"]
    products[0]["consumer_groups"] = consumer_reader_groups(plans)
    content = json.dumps(access, indent=2, ensure_ascii=False) + "\n"
    if args.check:
        if path.read_text() != content:
            raise ValueError("Permissions are out of sync with prefixed result inventory")
        print("Checked separate read-only dashboard groups; no changes made")
    else:
        path.write_text(content)
        print("Updated two read-only dashboard groups; no live groups, privileges or tables changed")


if __name__ == "__main__":
    main()