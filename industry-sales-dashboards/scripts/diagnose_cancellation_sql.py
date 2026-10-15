import json
import sys
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import ExecuteStatementRequestOnWaitTimeout

from preflight_sql import prepare_query


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from warehouse_results import validate_quoted_order_scan, warehouse_stage_sql


def main():
    workspace = WorkspaceClient(profile="DEFAULT")
    if workspace.config.host.rstrip("/") != "https://adb-7181820732839861.1.azuredatabricks.net":
        raise ValueError("Cancellation SQL diagnostics are DEV-only")
    plans = json.loads((ROOT / "src/config/dashboard_results.json").read_text())["datasets"]
    plan = next(item for item in plans if item["dataset"] == "ds_cancellations_detail_7d")
    mapping = json.loads((ROOT / "src/config/cs_team_sales_org_mapping.json").read_text())["rows"]
    original = prepare_query(plan["source_sql"], "synapse-prd", mapping)
    producer = plan["producers"][0]["sql"].replace("${var.source_catalog}", "synapse-prd")
    producer = producer.replace("`${var.catalog}`.gold.`${var.mapping_table_name}`", "`supply_chain_sandbox_d`.`datamodel`.`cs_team_sales_org_mapping`")
    producer = prepare_query(producer, "synapse-prd", mapping)
    columns = ["Order Number", "Order Item Number", "Net Value Euro", "Rejection Status", "Rejection Reason", "Date - Item Creation", "Date - Item Changed", "Document Type", "FK Sold to Party", "FK Material", "FK Sales Organization"]
    source_read = "SELECT " + ", ".join("`" + name + "`" for name in columns) + " FROM `synapse-prd`.pbi.`dbx_fact_o2c_-_self_service_-_sales_orders` WHERE `Document Type` IN ('YOR','YSO','YKE','YKB') AND `Rejection Status`='C' AND `FK Sales Organization` IS NOT NULL LIMIT 1"
    path = "/Volumes/automation_d/bronze/bronze_volume/SC_BI_industry_sales_result_scratch/D/" + "0" * 32 + "/open_orders/ds_cancellations_detail_7d/0"
    checks = [("warehouse_select_explain", "EXPLAIN FORMATTED " + producer), ("warehouse_write_explain", "EXPLAIN FORMATTED " + warehouse_stage_sql(producer, path)), ("exact_source_projection_read", source_read)]
    receipts = []
    for name, query in checks:
        result = workspace.statement_execution.execute_statement(
            warehouse_id="69ada62b2fb9b9e2", statement=query, wait_timeout="50s",
            on_wait_timeout=ExecuteStatementRequestOnWaitTimeout.CANCEL,
        )
        status = result.status.as_dict()
        receipt = {"check": name, "statement_id": result.statement_id, "status": status}
        if name.endswith("_explain") and result.result:
            receipt["plan"] = "\n".join(str(value) for row in result.result.data_array or [] for value in row)
            if name == "warehouse_select_explain":
                validate_quoted_order_scan(receipt["plan"])
            elif "InsertIntoDataSourceDirCommand" not in receipt["plan"]:
                raise ValueError("Warehouse-to-volume write command did not compile")
        receipts.append(receipt)
        destination = ROOT / "validation/cancellation_sql_diagnostics.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(receipts, indent=2) + "\n")
        print(json.dumps({"check": name, "statement_id": result.statement_id, "status": status}), flush=True)


if __name__ == "__main__":
    main()