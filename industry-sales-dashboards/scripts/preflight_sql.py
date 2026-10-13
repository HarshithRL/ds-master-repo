import argparse
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGETS = {
    "D": ("DEFAULT", "automation_d", "69ada62b2fb9b9e2"),
    "T": ("DEFAULT", "automation_d", "69ada62b2fb9b9e2"),
    "A": ("ACC", "automation_a", "0ef3e37fbbd5b772"),
    "P": ("PRD", "automation_p", "f500d0d670ae024b"),
}


def prepare_query(query, source_catalog, mapping_rows):
    if not re.fullmatch(r"[a-z][a-z0-9_-]*", source_catalog):
        raise ValueError("Invalid source catalog")
    query = query.replace("`synapse-prd`", f"`{source_catalog}`")
    values = []
    for row in mapping_rows:
        fields = [row[column] for column in ("sales_org_code", "sales_organization", "cs_team")]
        values.append("(" + ", ".join("'" + field.replace("'", "''") + "'" for field in fields) + ")")
    mapping = (
        "(SELECT * FROM VALUES " + ", ".join(values)
        + " AS mapping(sales_org_code, sales_organization, cs_team))"
    )
    query = query.replace(
        "`supply_chain_sandbox_d`.`datamodel`.`cs_team_sales_org_mapping`", mapping
    )
    for parameter in ("segment_filter", "country_filter", "priority_filter", "days_bucket_filter"):
        query = query.replace(f":{parameter}", "CAST(NULL AS ARRAY<STRING>)")
    for parameter in ("cancel_date.min", "cancel_date.max"):
        query = query.replace(f":{parameter}", "CAST(NULL AS DATE)")
    if re.search(r":[a-z_]+(?:\.[a-z_]+)?", query):
        raise ValueError("Unresolved native dashboard parameter")
    return query


def statement(profile, warehouse_id, sql):
    request = {
        "warehouse_id": warehouse_id,
        "statement": sql,
        "wait_timeout": "50s",
        "on_wait_timeout": "CANCEL",
    }
    command = [
        "databricks", "api", "post", "/api/2.0/sql/statements",
        "--profile", profile, "--json", json.dumps(request), "--output", "json",
    ]
    response = json.loads(subprocess.check_output(command, text=True))
    if response["status"]["state"] != "SUCCEEDED":
        raise RuntimeError(json.dumps(response["status"]))
    rows = response.get("result", {}).get("data_array", [])
    plan = "\n".join(str(value) for row in rows for value in row)
    if any(marker in plan for marker in ("Error occurred", "AnalysisException", "ParseException")):
        raise RuntimeError(plan[:5000])
    return response.get("statement_id")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("target", choices=TARGETS)
    parser.add_argument("--profile")
    parser.add_argument("--source-catalog", default="synapse-prd")
    args = parser.parse_args()
    default_profile, catalog, warehouse_id = TARGETS[args.target]
    profile = args.profile or default_profile
    mapping_rows = json.loads((ROOT / "src/config/cs_team_sales_org_mapping.json").read_text())["rows"]
    results = []
    checks = [(f"schema:{layer}", f"DESCRIBE SCHEMA {catalog}.{layer}") for layer in ("bronze", "silver", "gold")]
    for key in ("open_orders", "quotations"):
        metadata = json.loads((ROOT / "source_dashboards" / f"{key}.metadata.json").read_text())
        for dataset in json.loads(metadata["serialized_dashboard"])["datasets"]:
            query = "".join(dataset["queryLines"])
            checks.append((f"{key}:{dataset['name']}", "DESCRIBE QUERY " + prepare_query(query, args.source_catalog, mapping_rows)))
    for name, sql in checks:
        try:
            statement_id = statement(profile, warehouse_id, sql)
            results.append({"check": name, "passed": True, "statement_id": statement_id})
            print(f"PASS {name}", flush=True)
        except (RuntimeError, subprocess.CalledProcessError) as error:
            results.append({"check": name, "passed": False, "error": str(error)})
            print(f"FAIL {name}: {error}", flush=True)
    report = ROOT / "validation" / f"preflight_{args.target}.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({"target": args.target, "profile": profile, "source_catalog": args.source_catalog, "checks": results}, indent=2) + "\n")
    if not all(result["passed"] for result in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()