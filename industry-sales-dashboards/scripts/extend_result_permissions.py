import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from dataset_results import SHARED_CONVERSION_DATASETS, result_name, result_storage_name, unique_result_producers
from industry_config import OWNED_TABLE_PREFIX, RESULT_STATE_TABLE_NAME


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    path = ROOT.parent / "permissions/access.json"
    access = json.loads(path.read_text())
    products = [product for product in access["data_products"] if product["data_product"] == "industry-sales-dashboards"]
    if len(products) != 1:
        raise ValueError("Expected one Industry Sales product")
    groups = [group for group in products[0]["consumer_groups"] if group["tier"] == "READ"]
    if len(groups) != 1:
        raise ValueError("Expected one Industry Sales READ group")
    original_grants = groups[0]["grants"]
    renamed_grants = [dict(grant) for grant in original_grants]
    for grant in renamed_grants:
        if grant.get("catalog") == "automation" and grant.get("table", "").startswith("industry_sales_"):
            grant["table"] = OWNED_TABLE_PREFIX + grant["table"]
    legacy_gold = {"industry_sales_source_snapshot_state", "industry_sales_open_orders_allocation"}
    retired_results = {result_name("open_orders", name) for name in ("ds_top_late_orders", "ds_cancellations_trend")}
    retired_results.update(result_name("quotations", name, "converted") for name in SHARED_CONVERSION_DATASETS)
    retired_storage = {result_storage_name(name) for name in retired_results}
    grants = [
        grant for grant in renamed_grants
        if not (
            grant.get("catalog") == "automation"
            and (
                (grant.get("schema") == "bronze" and grant.get("table", "").removeprefix(OWNED_TABLE_PREFIX).startswith("industry_sales_raw_"))
                or (grant.get("schema") == "silver" and grant.get("table", "").removeprefix(OWNED_TABLE_PREFIX).startswith("industry_sales_src_"))
                or (grant.get("schema") == "gold" and grant.get("table", "").removeprefix(OWNED_TABLE_PREFIX) in legacy_gold)
                or (grant.get("schema") == "gold" and grant.get("table") in retired_results)
                or (grant.get("schema") == "silver" and grant.get("table") in retired_storage)
            )
        )
    ]
    groups[0]["grants"] = grants
    existing = {(grant["catalog"], grant.get("schema"), grant.get("table")): grant for grant in grants}
    plans = json.loads((ROOT / "src/config/dashboard_results.json").read_text())["datasets"]
    relations = [("gold", RESULT_STATE_TABLE_NAME)]
    for table in unique_result_producers(plans):
        relations.extend([("gold", table), ("silver", result_storage_name(table))])
    additions = []
    for schema, table in sorted(set(relations)):
        key = ("automation", schema, table)
        if key not in existing:
            additions.append({"catalog": "automation", "schema": schema, "table": table, "privileges": ["SELECT"]})
        elif "SELECT" not in existing[key]["privileges"]:
            raise ValueError(f"Existing result grant missing SELECT: {key}")
    grants.extend(additions)
    content = json.dumps(access, indent=2, ensure_ascii=False) + "\n"
    if args.check:
        if path.read_text() != content:
            raise ValueError("Permissions are out of sync with prefixed result inventory")
        print("Checked prefixed result permissions; no changes made")
    else:
        path.write_text(content)
        print(f"Updated prefixed result permissions; added {len(additions)} SELECT grants; no live privileges applied or tables renamed")


if __name__ == "__main__":
    main()