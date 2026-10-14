import argparse
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from industry_config import MAPPING_COLUMNS, validate_mapping
from source_snapshots import collect_source_columns, replace_source_references


DASHBOARDS = {
    "open_orders": (10, 6, 86),
    "quotations": (9, 4, 49),
}
SOURCE_PREFIXES = (
    "`synapse-prd`.`pbi`.",
    "`synapse-prd`.pbi.",
    "synapse-prd.pbi.",
)
MAPPING_PREFIXES = (
    "`supply_chain_sandbox_d`.`datamodel`.`cs_team_sales_org_mapping`",
    "`supply_chain_sandbox_d`.datamodel.cs_team_sales_org_mapping",
    "supply_chain_sandbox_d.datamodel.cs_team_sales_org_mapping",
)
MANAGERS = {
    "mustafaarda.bicakci@etexgroup.com",
    "pierre.delaguiche@etexgroup.com",
    "sahil.ailsingani@etexgroup.com",
    "harshith.raghunath@etexgroup.com",
    "noel.vranckx@etexgroup.com",
}


def parameterize(value):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key == "queryLines":
                rewritten = replace_source_references("".join(item))
                result[key] = [parameterize(line) for line in rewritten.splitlines(keepends=True)]
            else:
                result[key] = parameterize(item)
        return result
    if isinstance(value, list):
        return [parameterize(item) for item in value]
    if isinstance(value, str):
        for prefix in MAPPING_PREFIXES:
            value = value.replace(
                prefix, "${var.catalog}.gold.${var.mapping_table_name}"
            )
    return value


def prepare_dashboard(original, key):
    dashboard = parameterize(original)
    if key == "open_orders":
        allocation = next(item for item in dashboard["datasets"] if item["name"] == "ds_overview_allocation")
        allocation["queryLines"] = [
            "SELECT scope, cs_team, segment, plant, bucket, value_eur\n",
            "FROM ${var.catalog}.gold.${var.allocation_table_name}\n",
        ]
    return dashboard


def render(key):
    metadata = json.loads(
        (ROOT / "source_dashboards" / f"{key}.metadata.json").read_text()
    )
    original = json.loads(metadata["serialized_dashboard"])
    counts = (
        len(original["datasets"]),
        len(original["pages"]),
        sum(len(page["layout"]) for page in original["pages"]),
    )
    if counts != DASHBOARDS[key]:
        raise ValueError(f"Source dashboard shape changed: {key}: {counts}")
    dashboard = prepare_dashboard(original, key)
    serialized = json.dumps(dashboard, indent=2, ensure_ascii=True)
    if "supply_chain_sandbox_d" in serialized or "synapse-prd" in serialized:
        raise ValueError(f"Unparameterized source reference in {key}")
    resource = f"industry_{key}"
    lines = [
        "resources:",
        "  dashboards:",
        f"    {resource}:",
        f"      display_name: {json.dumps(metadata['display_name'], ensure_ascii=True)}",
        "      warehouse_id: ${var.warehouse_id}",
        "      embed_credentials: false",
    ]
    acl = json.loads((ROOT / "source_dashboards" / f"{key}.permissions.json").read_text())
    permissions = []
    for entry in acl["access_control_list"]:
        user_name = entry.get("user_name")
        if not user_name or user_name in MANAGERS:
            continue
        explicit = [permission for permission in entry["all_permissions"] if not permission["inherited"]]
        if len(explicit) != 1:
            raise ValueError(f"Unexpected original permissions for {user_name}")
        permissions.append((user_name, explicit[0]["permission_level"]))
    if permissions:
        lines.append("      permissions:")
        for user_name, level in sorted(permissions):
            lines.extend([f"        - user_name: {user_name}", f"          level: {level}"])
    lines.append("      serialized_dashboard: |-")
    lines.extend(f"        {line}" for line in serialized.splitlines())
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for key in DASHBOARDS:
        destination = ROOT / "resources" / "dashboards" / f"{key}.dashboard.yml"
        content = render(key)
        if args.check:
            if not destination.exists() or destination.read_text() != content:
                raise ValueError(f"Stale generated resource: {destination}")
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content)
        print(f"{'Checked' if args.check else 'Rendered'} {key}")
    mapping = json.loads((ROOT / "source_dashboards" / "mapping_statement.json").read_text())
    if mapping["status"]["state"] != "SUCCEEDED" or mapping["manifest"]["truncated"]:
        raise ValueError("Mapping source capture was unsuccessful or truncated")
    fields = tuple(column["name"] for column in mapping["manifest"]["schema"]["columns"])
    if fields != MAPPING_COLUMNS:
        raise ValueError(f"Mapping source columns changed: {fields}")
    captured_rows = mapping["result"]["data_array"]
    if len(captured_rows) != mapping["manifest"]["total_row_count"]:
        raise ValueError("Mapping source capture is incomplete")
    rows = validate_mapping([dict(zip(fields, values, strict=True)) for values in captured_rows])
    source_statements = []
    for key in DASHBOARDS:
        metadata = json.loads((ROOT / "source_dashboards" / f"{key}.metadata.json").read_text())
        original = json.loads(metadata["serialized_dashboard"])
        source_statements.extend("".join(dataset["queryLines"]) for dataset in original["datasets"])
    source_schemas = json.loads((ROOT / "src/config/source_column_names.json").read_text())
    snapshot_sources = collect_source_columns(source_statements, source_schemas)
    if not snapshot_sources:
        raise ValueError("No source tables found in native dashboard definitions")
    generated = {
        "cs_team_sales_org_mapping.json": {
            "source": "supply_chain_sandbox_d.datamodel.cs_team_sales_org_mapping",
            "source_statement_id": mapping["statement_id"],
            "rows": rows,
        },
        "source_dependencies.json": {"pbi_tables": [source["source_table"] for source in snapshot_sources]},
        "source_snapshots.json": {"sources": snapshot_sources},
    }
    for filename, value in generated.items():
        destination = ROOT / "src" / "config" / filename
        content = json.dumps(value, indent=2, ensure_ascii=True) + "\n"
        if args.check:
            if not destination.exists() or destination.read_text() != content:
                raise ValueError(f"Stale generated configuration: {destination}")
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content)
        print(f"{'Checked' if args.check else 'Rendered'} {filename}")
    metadata = json.loads((ROOT / "source_dashboards/open_orders.metadata.json").read_text())
    allocation = next(item for item in json.loads(metadata["serialized_dashboard"])["datasets"] if item["name"] == "ds_overview_allocation")
    allocation_sql = "".join(parameterize(allocation)["queryLines"])
    destination = ROOT / "src/config/open_orders_allocation.sql"
    if args.check:
        if not destination.exists() or destination.read_text() != allocation_sql:
            raise ValueError(f"Stale allocation calculation: {destination}")
    else:
        destination.write_text(allocation_sql)
    print(f"{'Checked' if args.check else 'Rendered'} allocation calculation")


if __name__ == "__main__":
    main()