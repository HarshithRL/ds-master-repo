import argparse
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from industry_config import MAPPING_COLUMNS, validate_mapping
from source_snapshots import collect_source_columns, replace_source_references
from dataset_results import compile_dataset, table_edits, unique_result_producers
from dashboard_access import dashboard_members, reader_config
from sqlglot import exp, parse_one


DASHBOARDS = {
    "open_orders": (10, 6, 86),
    "quotations": (9, 4, 49),
}
RETIRED_DATASETS = {"open_orders": {"ds_cancellations_trend"}, "quotations": set()}
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


def active_datasets(original, key):
    retired = RETIRED_DATASETS[key]
    retired_sources = {source["name"] for graph in original.get("relationshipGraphs", []) for source in graph["sources"] if source["datasetName"] in retired}
    if any(name in json.dumps(original["pages"]) for name in retired | retired_sources):
        raise ValueError("Cannot retire a dataset referenced by a page")
    return [dataset for dataset in original["datasets"] if dataset["name"] not in retired]


def prepare_dashboard(original, key):
    dashboard = json.loads(json.dumps(original))
    dashboard["datasets"] = active_datasets(dashboard, key)
    for graph in dashboard.get("relationshipGraphs", []):
        graph["sources"] = [source for source in graph["sources"] if source["datasetName"] not in RETIRED_DATASETS[key]]
    schemas = json.loads((ROOT / "src/config/source_column_names.json").read_text())
    for dataset in dashboard["datasets"]:
        source = "".join(dataset["queryLines"])
        plan = compile_dataset(key, dataset["name"], source, schemas)
        dataset["queryLines"] = (plan["consumer_sql"] + "\n").splitlines(keepends=True)
    return dashboard


def prepare_result_plans():
    schemas = json.loads((ROOT / "src/config/source_column_names.json").read_text())
    plans = []
    for key in DASHBOARDS:
        metadata = json.loads((ROOT / "source_dashboards" / f"{key}.metadata.json").read_text())
        for dataset in active_datasets(json.loads(metadata["serialized_dashboard"]), key):
            plan = compile_dataset(key, dataset["name"], "".join(dataset["queryLines"]), schemas)
            for producer in plan["producers"]:
                statement = producer["sql"]
                replacements = {"supply_chain_sandbox_d.datamodel.cs_team_sales_org_mapping": "`${var.catalog}`.gold.`${var.mapping_table_name}`"}
                for table in parse_one(statement, read="databricks").find_all(exp.Table):
                    if table.catalog == "synapse-prd" and table.db == "pbi":
                        replacements[".".join((table.catalog, table.db, table.name))] = f"`${{var.source_catalog}}`.pbi.`{table.name}`"
                producer["sql"] = table_edits(statement, replacements)
            plans.append(plan)
            unique_result_producers(plans)
    return plans


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
        if explicit[0]["permission_level"] == "CAN_READ" and user_name.lower() not in dashboard_members(key):
            continue
        permissions.append((user_name, explicit[0]["permission_level"]))
    if permissions:
        lines.append("      permissions:")
        for user_name, level in sorted(permissions):
            lines.extend([f"        - user_name: {user_name}", f"          level: {level}"])
    lines.append("      serialized_dashboard: |-")
    lines.extend(f"        {line}" for line in serialized.splitlines())
    return "\n".join(lines) + "\n"


def render_reader_permissions():
    config = reader_config()
    lines = ["targets:"]
    for target in ("A", "P"):
        lines.extend([f"  {target}:", "    resources:", "      dashboards:"])
        for key in DASHBOARDS:
            lines.extend([f"        industry_{key}:", "          permissions:", f"            - group_name: {config['dashboards'][key]['group_name']}", "              level: CAN_READ"])
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
    destination = ROOT / "resources/dashboards/readers.permissions.yml"
    content = render_reader_permissions()
    if args.check:
        if not destination.exists() or destination.read_text() != content:
            raise ValueError("Stale generated dashboard reader ACLs")
    else:
        destination.write_text(content)
    print(f"{'Checked' if args.check else 'Rendered'} dashboard reader ACLs")
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
        "dashboard_results.json": {"datasets": prepare_result_plans()},
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